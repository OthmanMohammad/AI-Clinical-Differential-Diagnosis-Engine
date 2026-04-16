"""Layer 3.1 — Vector Search via Qdrant + fastembed.

Embeds user input and finds matching medical entities in Qdrant.
Both dev and production use fastembed in-process with
BAAI/bge-small-en-v1.5 (~130MB). The same model must be used to
build the Qdrant collection (see services/ingestion/qdrant_indexer.py)
or query-time and index-time vectors will live in different embedding
spaces and similarity becomes meaningless.
"""

from __future__ import annotations

import os
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
    """Get or initialize the fastembed model (lazy singleton).

    Reads FASTEMBED_CACHE_PATH from the environment and passes it as
    cache_dir so the runtime picks up the model that was baked into
    the Docker image at build time (see services/api/Dockerfile).
    Falling back to fastembed's default cache dir in dev environments
    where the model is downloaded on first use.
    """
    global _embedder
    if _embedder is None:
        settings = get_settings()
        model_name = settings.embedding_model
        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH")
        logger.info("loading_embedding_model", model=model_name, cache_dir=cache_dir)
        kwargs = {"model_name": model_name}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        _embedder = TextEmbedding(**kwargs)
        logger.info("embedding_model_loaded", model=model_name)
    return _embedder


def preload_embedder() -> None:
    """Eagerly load the embedding model + warm it up with a dummy query.
    Call this at app startup so the first request doesn't pay the cold
    model load cost (~3 seconds for bge-small)."""
    if _embedder is None:
        logger.info("preloading_embedding_model")
        embedder = get_embedder()
        # Warm up the model — first inference is slower than subsequent ones
        list(embedder.embed(["warmup query"]))
        logger.info("embedding_model_preloaded")


def embed_text(text: str) -> list[float]:
    """Embed a single text string using fastembed."""
    embedder = get_embedder()
    embeddings = list(embedder.embed([text]))
    return embeddings[0].tolist()


class NoSeedNodesError(Exception):
    """No matching medical concepts found in vector search."""


async def _embed_and_query(
    intake: PatientIntake,
    qdrant: AsyncQdrantClient,
    top_k: int,
    score_threshold: float,
) -> list:
    """Embed the intake's symptoms + free text and run a single Qdrant
    similarity search. Returns the raw scored points.

    Factored out of get_seed_nodes/get_phenotype_seeds so both entry
    points share the same embedding and Qdrant call without the caller
    having to know which downstream path they're feeding.
    """
    settings = get_settings()
    query_text = " ".join(intake.symptoms) + " " + intake.free_text

    embedding = embed_text(query_text)

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
    return results


async def get_seed_nodes(
    intake: PatientIntake,
    qdrant: AsyncQdrantClient,
    top_k: int = 5,
    score_threshold: float = 0.65,
) -> tuple[list[str], list]:
    """Legacy entry point — embed, search, return ALL matching neo4j IDs.

    Used by graph_rag_stream.py for the old streaming pipeline. The new
    Tier 2 pipeline should call `get_phenotype_seeds` instead.

    Returns:
        Tuple of (neo4j_node_ids, scored_points).
    """
    results = await _embed_and_query(intake, qdrant, top_k, score_threshold)
    if not results:
        raise NoSeedNodesError(
            "No matching medical concepts found above similarity threshold. "
            "Try rephrasing your symptoms or adding more detail."
        )
    neo4j_ids = [r.payload["neo4j_id"] for r in results]
    return neo4j_ids, results


async def get_phenotype_seeds(
    intake: PatientIntake,
    qdrant: AsyncQdrantClient,
    top_k: int = 12,
    score_threshold: float = 0.55,
) -> tuple[list[str], list]:
    """Return Neo4j element IDs for PHENOTYPE nodes that match the
    patient's symptoms.

    Used by the Tier 2 retrieval pipeline. Filters Qdrant results by
    the `label=Phenotype` payload field, dropping disease matches —
    those aren't useful as inputs to the phenotype-intersection query
    because the query's whole point is to INFER diseases FROM
    phenotypes.

    A broader top_k (12 vs 5) and lower threshold (0.55 vs 0.65)
    compared to get_seed_nodes, because:
      - Phenotype matches are noisier (many patient symptoms
        correspond to closely-related phenotype nodes) and we want
        to capture several even if some are borderline.
      - The phenotype-intersection query has a min_overlap safeguard
        downstream that filters out spurious singletons.

    Returns:
        Tuple of (phenotype_neo4j_ids, all_scored_points). The second
        element is the full result set including any non-phenotype
        matches, kept for logging / observability — the caller only
        uses the phenotype_ids list for retrieval.
    """
    results = await _embed_and_query(intake, qdrant, top_k, score_threshold)
    if not results:
        raise NoSeedNodesError(
            "No matching medical concepts found above similarity threshold. "
            "Try rephrasing your symptoms or adding more detail."
        )

    phenotype_ids: list[str] = []
    for r in results:
        label = (r.payload or {}).get("label")
        if label == "Phenotype":
            phenotype_ids.append(r.payload["neo4j_id"])

    logger.info(
        "phenotype_seeds_extracted",
        total_results=len(results),
        phenotypes=len(phenotype_ids),
    )

    if not phenotype_ids:
        raise NoSeedNodesError(
            "Vector search returned no phenotype matches for the patient's "
            "symptoms. The phenotype index may be empty or the user's input "
            "doesn't match any phenotype name closely enough."
        )

    return phenotype_ids, results
