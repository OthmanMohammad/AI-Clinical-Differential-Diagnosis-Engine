"""Layer 3.1 — Vector Search via Qdrant + fastembed.

Embeds user input and finds matching medical entities in Qdrant.
Production: fastembed in-process (BAAI/bge-micro-v2, ~30MB).
Local dev: fastembed in-process (BAAI/bge-small-en-v1.5, ~130MB).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.observability.metrics import QDRANT_LATENCY

if TYPE_CHECKING:
    from app.models.patient import PatientIntake

logger = structlog.get_logger()

# Lazy-loaded embedding model singleton
_embedder: TextEmbedding | None = None


def get_embedder() -> TextEmbedding:
    """Get or initialize the fastembed model (lazy singleton)."""
    global _embedder
    if _embedder is None:
        settings = get_settings()
        model_name = settings.embedding_model
        logger.info("loading_embedding_model", model=model_name)
        _embedder = TextEmbedding(model_name=model_name)
        logger.info("embedding_model_loaded", model=model_name)
    return _embedder


def embed_text(text: str) -> list[float]:
    """Embed a single text string using fastembed."""
    embedder = get_embedder()
    embeddings = list(embedder.embed([text]))
    return embeddings[0].tolist()


class NoSeedNodesError(Exception):
    """No matching medical concepts found in vector search."""


async def get_seed_nodes(
    intake: PatientIntake,
    qdrant: AsyncQdrantClient,
    top_k: int = 5,
    score_threshold: float = 0.65,
) -> tuple[list[str], list]:
    """Embed patient input, search Qdrant, return seed node IDs for graph traversal.

    Returns:
        Tuple of (neo4j_node_ids, scored_points) for downstream use.
    """
    settings = get_settings()
    query_text = " ".join(intake.symptoms) + " " + intake.free_text

    # Embed
    embedding = embed_text(query_text)

    # Search Qdrant — query_points() is the current API (search() removed in 1.17+)
    start = time.monotonic()
    response = await qdrant.query_points(
        collection_name=settings.qdrant_collection,
        query=embedding,
        limit=top_k,
        score_threshold=score_threshold,
    )
    results = response.points
    elapsed = time.monotonic() - start
    QDRANT_LATENCY.observe(elapsed)

    logger.info(
        "vector_search_complete",
        results=len(results),
        top_score=results[0].score if results else 0,
        elapsed_ms=round(elapsed * 1000),
    )

    if not results:
        raise NoSeedNodesError(
            "No matching medical concepts found above similarity threshold. "
            "Try rephrasing your symptoms or adding more detail."
        )

    neo4j_ids = [r.payload["neo4j_id"] for r in results]
    return neo4j_ids, results
