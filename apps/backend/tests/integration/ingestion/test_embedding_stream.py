"""Integration tests for streaming embedding generation with real SentenceTransformer model"""

import asyncio
from datetime import UTC, datetime

import pytest

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from gim_backend.ingestion.embeddings import (
    EmbeddedIssue,
    embed_issue_stream,
)
from gim_backend.ingestion.gatherer import IssueData

# Skip entire module if sentence-transformers not installed
pytestmark = pytest.mark.skipif(not SENTENCE_TRANSFORMERS_AVAILABLE, reason="sentence-transformers not installed")


# Test model dimensions (all-MiniLM-L6-v2 produces 384-dim vectors)
TEST_MODEL_NAME = "all-MiniLM-L6-v2"
TEST_EMBEDDING_DIM = 384


class IntegrationEmbedder:
    """
    Integration test embedder using all-MiniLM-L6-v2 (384-dim).
    Conforms to EmbeddingProvider protocol for use with embed_issue_stream.
    Faster than production nomic model; validates pipeline behavior.
    Note: Named IntegrationEmbedder to avoid pytest collection (Test prefix).
    """

    MODEL_NAME: str = TEST_MODEL_NAME
    BATCH_SIZE: int = 25

    def __init__(self):
        self._model = None

    def _load_model(self):
        if self._model is None:
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._load_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(texts, convert_to_numpy=True, normalize_embeddings=True),
        )
        return embeddings.tolist()


@pytest.fixture
def make_issue(sample_q_components):
    def _make(node_id: str = "I_123", title: str = "Bug report", body: str = "Description"):
        return IssueData(
            node_id=node_id,
            repo_id="R_456",
            title=title,
            body_text=body,
            labels=["bug"],
            github_created_at=datetime.now(UTC),
            q_score=0.75,
            q_components=sample_q_components,
            state="open",
        )

    return _make


@pytest.fixture(scope="module")
def test_embedder():
    """Module-scoped embedder to avoid reloading model per test"""
    return IntegrationEmbedder()


class TestEmbedderModelLoading:
    """Verify model lazy loading and basic embedding behavior"""

    @pytest.mark.asyncio
    async def test_model_loads_lazily(self):
        """Model should not load until first embed call"""
        embedder = IntegrationEmbedder()

        assert embedder._model is None

        await embedder.embed_batch(["test text"])

        assert embedder._model is not None

    @pytest.mark.asyncio
    async def test_embedding_dimension_is_384(self, test_embedder):
        """all-MiniLM-L6-v2 produces 384-dimensional vectors"""
        embeddings = await test_embedder.embed_batch(["Hello world"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) == TEST_EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_embeddings_are_normalized(self, test_embedder):
        """Embeddings should be L2 normalized (unit vectors)"""
        import math

        embeddings = await test_embedder.embed_batch(["Test sentence"])

        magnitude = math.sqrt(sum(x * x for x in embeddings[0]))
        assert abs(magnitude - 1.0) < 0.001, f"Expected unit vector, got magnitude {magnitude}"


class TestEmbedStream100Issues:
    """Integration test: stream 100 issues through the embedding pipeline"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_stream_100_issues(self, test_embedder, make_issue):
        """Verify 100 issues stream correctly with proper batching"""
        issue_count = 100
        batch_size = 25

        async def issue_generator():
            for i in range(issue_count):
                yield make_issue(
                    node_id=f"I_{i}",
                    title=f"Issue {i}: Test bug",
                    body=f"This is the body of issue {i} with some technical content.",
                )

        results = []
        async for embedded in embed_issue_stream(
            issue_generator(),
            test_embedder,
            batch_size=batch_size,
        ):
            results.append(embedded)

        # Verify count
        assert len(results) == issue_count, f"Expected {issue_count} results, got {len(results)}"

        # Verify all have embeddings of correct dimension
        for i, result in enumerate(results):
            assert isinstance(result, EmbeddedIssue)
            assert len(result.embedding) == TEST_EMBEDDING_DIM, (
                f"Issue {i} has wrong embedding dimension: {len(result.embedding)}"
            )
            assert result.issue.node_id == f"I_{i}"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_stream_maintains_order(self, test_embedder, make_issue):
        """Issues should be yielded in the same order as input"""
        issue_count = 50

        async def ordered_issues():
            for i in range(issue_count):
                yield make_issue(node_id=f"ORDER_{i}")

        results = [
            item
            async for item in embed_issue_stream(
                ordered_issues(),
                test_embedder,
                batch_size=25,
            )
        ]

        for i, result in enumerate(results):
            assert result.issue.node_id == f"ORDER_{i}", (
                f"Order mismatch at index {i}: expected ORDER_{i}, got {result.issue.node_id}"
            )

    @pytest.mark.asyncio
    async def test_partial_batch_handled(self, test_embedder, make_issue):
        """Verify final partial batch is flushed correctly"""
        issue_count = 37  # 25 + 12 partial

        async def issue_generator():
            for i in range(issue_count):
                yield make_issue(node_id=f"I_{i}")

        results = [
            item
            async for item in embed_issue_stream(
                issue_generator(),
                test_embedder,
                batch_size=25,
            )
        ]

        assert len(results) == issue_count


class TestEmbeddingQuality:
    """Verify embedding quality and semantic properties"""

    @pytest.mark.asyncio
    async def test_similar_texts_have_similar_embeddings(self, test_embedder, make_issue):
        """Semantically similar issues should have high cosine similarity"""
        import math

        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(x * x for x in b))
            return dot / (mag_a * mag_b)

        # Similar issues
        issue1 = make_issue(
            node_id="I_1",
            title="TypeError when calling async function",
            body="Getting TypeError: object is not callable when invoking async method",
        )
        issue2 = make_issue(
            node_id="I_2",
            title="TypeError on async method invocation",
            body="Error: TypeError thrown when calling an asynchronous function",
        )
        # Different issue
        issue3 = make_issue(
            node_id="I_3",
            title="Memory leak in cache implementation",
            body="The LRU cache is not releasing memory when items expire",
        )

        async def issue_stream():
            yield issue1
            yield issue2
            yield issue3

        results = [
            item
            async for item in embed_issue_stream(
                issue_stream(),
                test_embedder,
                batch_size=25,
            )
        ]

        emb1, emb2, emb3 = [r.embedding for r in results]

        sim_1_2 = cosine_similarity(emb1, emb2)
        sim_1_3 = cosine_similarity(emb1, emb3)

        # Similar issues should have higher similarity than different ones
        assert sim_1_2 > sim_1_3, f"Similar issues should have higher similarity: {sim_1_2:.3f} vs {sim_1_3:.3f}"
        # Similar issues should have cosine > 0.7
        assert sim_1_2 > 0.7, f"Similar issues have low similarity: {sim_1_2:.3f}"

    @pytest.mark.asyncio
    async def test_empty_stream_yields_nothing(self, test_embedder):
        """Empty input stream should yield empty output"""

        async def empty_stream():
            return
            yield  # Makes this an async generator

        results = [
            item
            async for item in embed_issue_stream(
                empty_stream(),
                test_embedder,
                batch_size=25,
            )
        ]

        assert len(results) == 0


class TestTextFormatting:
    """Verify text sent to model is formatted correctly"""

    @pytest.mark.asyncio
    async def test_title_body_concatenation(self, test_embedder, make_issue):
        """Embedding text should be title + newline + body"""
        issue = make_issue(
            title="Specific Title Here",
            body="Specific body content here",
        )

        async def single_issue():
            yield issue

        # Track what text gets embedded
        original_embed = test_embedder.embed_batch
        captured_texts = []

        async def capturing_embed(texts):
            captured_texts.extend(texts)
            return await original_embed(texts)

        test_embedder.embed_batch = capturing_embed

        try:
            _ = [
                item
                async for item in embed_issue_stream(
                    single_issue(),
                    test_embedder,
                    batch_size=25,
                )
            ]

            assert len(captured_texts) == 1
            assert captured_texts[0] == "Specific Title Here\nSpecific body content here"
        finally:
            test_embedder.embed_batch = original_embed
