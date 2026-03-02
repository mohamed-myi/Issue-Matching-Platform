"""
Application-scoped embedding service for query vectorization.
Wraps NomicMoEEmbedder as a singleton to avoid reloading the model per request.
Uses asyncio.Lock with double-check pattern for thread safety in multi-worker environments.
"""

import asyncio
import logging
from typing import Literal

from gim_backend.ingestion.nomic_moe_embedder import EMBEDDING_DIM, NomicMoEEmbedder

logger = logging.getLogger(__name__)

_embedder: NomicMoEEmbedder | None = None
_embedder_lock: asyncio.Lock = asyncio.Lock()


def _is_valid_embedding(vector: list[float] | None) -> bool:
    return vector is not None and len(vector) == EMBEDDING_DIM


async def _embed_texts(
    texts: list[str],
    *,
    embed_kind: Literal["query", "document"],
    single: bool,
) -> list[list[float] | None]:
    if not texts:
        return []

    try:
        embedder = await get_embedder()
        if embed_kind == "query":
            embeddings = await embedder.embed_queries(texts)
        else:
            embeddings = await embedder.embed_documents(texts)

        if single:
            if embeddings and len(embeddings) > 0:
                vector = embeddings[0]
                if not _is_valid_embedding(vector):
                    logger.warning(
                        "Embedding %s returned invalid dimension: expected %s, got %s",
                        embed_kind,
                        EMBEDDING_DIM,
                        len(vector) if vector is not None else None,
                    )
                    return [None]
                return [vector]
            return []

        return [vector if _is_valid_embedding(vector) else None for vector in embeddings]
    except Exception as e:
        if single:
            logger.warning(f"Embedding {embed_kind} failed: {e}")
        else:
            logger.warning(f"Batch {embed_kind} embedding failed: {e}")
        return [None] * len(texts)


def assert_vector_dim(vector: list[float] | None, *, context: str) -> None:
    if vector is None:
        return
    if len(vector) != EMBEDDING_DIM:
        raise ValueError(f"{context} embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vector)}")


async def get_embedder() -> NomicMoEEmbedder:
    """
    Returns the singleton NomicMoEEmbedder instance.
    Uses double-check locking to prevent race conditions in multi-worker environments.
    Model loads lazily on first embed call.
    """
    global _embedder

    if _embedder is not None:
        return _embedder

    async with _embedder_lock:
        if _embedder is None:
            logger.info("Initializing embedding service singleton")
            _embedder = NomicMoEEmbedder()

    return _embedder


async def embed_query(text: str) -> list[float] | None:
    """
    Embeds a single query-like text into a 256-dim vector.
    Uses the singleton embedder to avoid model reload overhead.

    Args:
        text: The search query to embed

    Returns:
        256-dimensional normalized embedding vector, or None if embedding fails
    """
    vectors = await _embed_texts([text], embed_kind="query", single=True)
    return vectors[0] if vectors else None


async def embed_document(text: str) -> list[float] | None:
    """Embeds a single document/content text into a 256-dim vector."""
    vectors = await _embed_texts([text], embed_kind="document", single=True)
    return vectors[0] if vectors else None


async def embed_queries(texts: list[str]) -> list[list[float] | None]:
    """
    Embeds multiple query-like texts in a single batch.
    More efficient than calling embed_query repeatedly.

    Args:
        texts: List of search queries to embed

    Returns:
        List of 256-dimensional normalized embedding vectors (None for failed embeddings)
    """
    return await _embed_texts(texts, embed_kind="query", single=False)


async def embed_documents(texts: list[str]) -> list[list[float] | None]:
    """Embeds multiple document/content texts in a single batch."""
    return await _embed_texts(texts, embed_kind="document", single=False)


async def close_embedder() -> None:
    """
    Cleanup embedder resources. Called on application shutdown.
    Acquires lock to prevent race with initialization.
    """
    global _embedder

    async with _embedder_lock:
        if _embedder is not None:
            logger.info("Closing embedding service")
            _embedder.close()
            _embedder = None


def reset_embedder_for_testing() -> None:
    """For testing only; resets singleton state without lock (not async-safe)."""
    global _embedder
    _embedder = None


__all__ = [
    "EMBEDDING_DIM",
    "assert_vector_dim",
    "get_embedder",
    "embed_query",
    "embed_document",
    "embed_queries",
    "embed_documents",
    "close_embedder",
    "reset_embedder_for_testing",
]
