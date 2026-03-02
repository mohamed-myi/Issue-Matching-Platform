"""Integration tests for Cloud SQL pgvector and Pub/Sub infrastructure validation"""

import pytest

try:
    from testcontainers.postgres import PostgresContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

# Skip entire module if testcontainers not installed
pytestmark = pytest.mark.skipif(
    not TESTCONTAINERS_AVAILABLE, reason="testcontainers[postgres] not installed; requires Docker"
)

# Schema with 256-dim vectors for Cloud SQL migration validation
SETUP_SQL_256 = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS ingestion;

CREATE TABLE ingestion.issue_256 (
    node_id VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    body_text VARCHAR NOT NULL,
    embedding vector(256),
    content_hash VARCHAR(64)
);

CREATE INDEX ix_issue_256_embedding_hnsw ON ingestion.issue_256
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX ix_issue_256_content_hash ON ingestion.issue_256(content_hash);
"""


@pytest.fixture(scope="module")
def postgres_container():
    """Ephemeral PostgreSQL 16 with pgvector via testcontainers"""
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="testdb",
    ) as pg:
        yield pg


@pytest.fixture(scope="module")
def sync_connection_url(postgres_container):
    """Synchronous connection URL for schema setup"""
    url = postgres_container.get_connection_url()
    return url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture(scope="module")
def async_connection_url(postgres_container):
    """Async connection URL for test sessions"""
    url = postgres_container.get_connection_url()
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(scope="module")
def setup_schema_256(sync_connection_url):
    """Create schema with 256-dim vector table once per module"""
    import psycopg2

    parts = sync_connection_url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    conn = psycopg2.connect(
        user=user_pass[0],
        password=user_pass[1],
        host=host_port[0],
        port=host_port[1],
        dbname=host_port_db[1],
    )
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute(SETUP_SQL_256)

    conn.close()
    return True


@pytest.fixture
async def db_session(async_connection_url, setup_schema_256):
    """Yield async session, clean tables after each test"""
    engine = create_async_engine(
        async_connection_url,
        echo=False,
        pool_pre_ping=True,
    )

    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session

        # Cleanup: delete all rows after test
        await session.exec(text("DELETE FROM ingestion.issue_256"))
        await session.commit()

    await engine.dispose()


class TestCloudSQLPgvectorExtension:
    """Verify pgvector 0.7.0+ is available and functioning"""

    @pytest.mark.asyncio
    async def test_pgvector_extension_installed(self, db_session):
        """Verify pgvector extension is installed"""
        result = await db_session.exec(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        version = result.scalar()

        assert version is not None, "pgvector extension not installed"

    @pytest.mark.asyncio
    async def test_pgvector_version_supports_hnsw(self, db_session):
        """Verify pgvector version supports HNSW indexes (requires 0.5.0+)"""
        result = await db_session.exec(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        version = result.scalar()

        # Parse version (e.g., "0.7.0" -> [0, 7, 0])
        major, minor, patch = [int(x) for x in version.split(".")]

        # HNSW support added in 0.5.0
        assert (major, minor) >= (0, 5), f"pgvector {version} does not support HNSW"


class TestCloudSQLVectorOperations:
    """Test INSERT, UPDATE, and HNSW operations on vector(256)"""

    @pytest.mark.asyncio
    async def test_insert_256_dim_vector(self, db_session):
        """Verify 256-dim vector can be inserted"""
        embedding = [0.1] * 256

        await db_session.exec(
            text("""
                INSERT INTO ingestion.issue_256 (node_id, title, body_text, embedding)
                VALUES (:node_id, :title, :body_text, :embedding)
            """),
            params={
                "node_id": "I_test_insert",
                "title": "Test issue",
                "body_text": "Test body",
                "embedding": str(embedding),
            },
        )
        await db_session.commit()

        # Verify insertion
        result = await db_session.exec(
            text("SELECT vector_dims(embedding) FROM ingestion.issue_256 WHERE node_id = :id"),
            params={"id": "I_test_insert"},
        )
        dim = result.scalar()

        assert dim == 256

    @pytest.mark.asyncio
    async def test_update_256_dim_vector(self, db_session):
        """Verify 256-dim vector can be updated"""
        initial_embedding = [0.1] * 256
        updated_embedding = [0.9] * 256

        # Insert initial
        await db_session.exec(
            text("""
                INSERT INTO ingestion.issue_256 (node_id, title, body_text, embedding)
                VALUES (:node_id, :title, :body_text, :embedding)
            """),
            params={
                "node_id": "I_test_update",
                "title": "Test issue",
                "body_text": "Test body",
                "embedding": str(initial_embedding),
            },
        )
        await db_session.commit()

        # Update embedding
        await db_session.exec(
            text("""
                UPDATE ingestion.issue_256
                SET embedding = :embedding
                WHERE node_id = :node_id
            """),
            params={
                "node_id": "I_test_update",
                "embedding": str(updated_embedding),
            },
        )
        await db_session.commit()

        # Verify update by checking distance to the updated vector is ~0
        result = await db_session.exec(
            text("""
                SELECT embedding <-> :embedding AS dist
                FROM ingestion.issue_256
                WHERE node_id = :id
            """),
            params={"id": "I_test_update", "embedding": str(updated_embedding)},
        )
        dist = result.scalar()

        assert dist is not None
        assert dist < 1e-6

    @pytest.mark.asyncio
    async def test_hnsw_index_cosine_similarity(self, db_session):
        """Verify HNSW index enables cosine similarity search"""
        # Insert test vectors
        vectors = [
            ("I_sim_1", [1.0] + [0.0] * 255),  # Unit vector in dim 1
            ("I_sim_2", [0.0, 1.0] + [0.0] * 254),  # Unit vector in dim 2
            ("I_sim_3", [0.707, 0.707] + [0.0] * 254),  # 45-degree vector
        ]

        for node_id, emb in vectors:
            await db_session.exec(
                text("""
                    INSERT INTO ingestion.issue_256 (node_id, title, body_text, embedding)
                    VALUES (:node_id, :title, :body_text, :embedding)
                """),
                params={
                    "node_id": node_id,
                    "title": f"Issue {node_id}",
                    "body_text": "Test body",
                    "embedding": str(emb),
                },
            )
        await db_session.commit()

        # Query for nearest neighbors to [1, 0, 0, ...]
        query_vector = [1.0] + [0.0] * 255

        result = await db_session.exec(
            text("""
                SELECT node_id, 1 - (embedding <=> :query) as similarity
                FROM ingestion.issue_256
                ORDER BY embedding <=> :query
                LIMIT 2
            """),
            params={"query": str(query_vector)},
        )
        rows = result.all()

        # First result should be I_sim_1 (exact match)
        assert rows[0][0] == "I_sim_1"
        assert rows[0][1] > 0.99  # Nearly 1.0 similarity

    @pytest.mark.asyncio
    async def test_content_hash_idempotency_column(self, db_session):
        """Verify content_hash column exists for idempotency checks"""
        await db_session.exec(
            text("""
                INSERT INTO ingestion.issue_256 (node_id, title, body_text, content_hash)
                VALUES (:node_id, :title, :body_text, :content_hash)
            """),
            params={
                "node_id": "I_hash_test",
                "title": "Test issue",
                "body_text": "Test body",
                "content_hash": "abc123def456",
            },
        )
        await db_session.commit()

        result = await db_session.exec(
            text("SELECT content_hash FROM ingestion.issue_256 WHERE node_id = :id"),
            params={"id": "I_hash_test"},
        )
        stored_hash = result.scalar()

        assert stored_hash == "abc123def456"


class TestPubSubIdempotency:
    """Test idempotency handling for duplicate messages"""

    @pytest.mark.asyncio
    async def test_duplicate_detection_by_content_hash(self, db_session):
        """Verify duplicate messages can be detected by content_hash"""
        content_hash = "sha256_duplicate_test"

        # Insert first message
        await db_session.exec(
            text("""
                INSERT INTO ingestion.issue_256 (node_id, title, body_text, content_hash)
                VALUES (:node_id, :title, :body_text, :content_hash)
            """),
            params={
                "node_id": "I_dup_1",
                "title": "Original issue",
                "body_text": "Original body",
                "content_hash": content_hash,
            },
        )
        await db_session.commit()

        # Check if duplicate exists
        result = await db_session.exec(
            text("""
                SELECT 1 FROM ingestion.issue_256
                WHERE content_hash = :content_hash
            """),
            params={"content_hash": content_hash},
        )
        exists = result.scalar() is not None

        assert exists is True, "Should detect existing content_hash"

    @pytest.mark.asyncio
    async def test_different_content_hash_not_duplicate(self, db_session):
        """Verify different content_hash is not detected as duplicate"""
        # Insert with one hash
        await db_session.exec(
            text("""
                INSERT INTO ingestion.issue_256 (node_id, title, body_text, content_hash)
                VALUES (:node_id, :title, :body_text, :content_hash)
            """),
            params={
                "node_id": "I_unique_1",
                "title": "First issue",
                "body_text": "First body",
                "content_hash": "sha256_first",
            },
        )
        await db_session.commit()

        # Check for different hash
        result = await db_session.exec(
            text("""
                SELECT 1 FROM ingestion.issue_256
                WHERE content_hash = :content_hash
            """),
            params={"content_hash": "sha256_second"},
        )
        exists = result.scalar() is not None

        assert exists is False, "Different content_hash should not match"
