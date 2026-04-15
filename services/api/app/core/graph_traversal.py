"""Layer 3.3 — Graph expansion around ranked candidates.

This module used to be the *primary* retrieval layer — a 2-hop traversal
from vector-search seeds that dumped a flat subgraph for the LLM.
In the Tier 2 rewrite, retrieval.py does the structural work (phenotype
intersection + rule fusion) and this module's only job is to enrich
the top candidates with 1-hop context so the LLM has something to say
beyond the immediate symptom edges.

Two public entry points:

    expand_candidates(candidates, driver, per_candidate_edges=15)
        New Tier 2 helper. Takes a list of retrieval.Candidate objects
        and fans out 1 hop from each, returning nodes + relationships
        ready for the context builder.

    traverse_graph(seed_ids, driver, min_nodes=3)
        Legacy 2-hop traversal. Kept for graph_rag_stream.py and the
        old pipeline path. Marked for removal once the streaming
        endpoint is migrated.

Both functions use bounded, LIMIT-per-hop Cypher that will never
reproduce the OOM blow-up the old 3-hop query had.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from app.observability.metrics import NEO4J_LATENCY

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from app.core.retrieval import Candidate

logger = structlog.get_logger()


# =============================================================================
# Shared constants
# =============================================================================

# Edge types considered clinically meaningful. Must be a subset of what
# the ingestion script loads (services/ingestion/primekg_loader.py).
ALLOWED_EDGE_TYPES = [
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "disease_protein",
    "drug_protein",
    "disease_disease",
    "phenotype_phenotype",
]


class GraphTraversalError(Exception):
    """Raised when a traversal fails or returns insufficient data."""


# =============================================================================
# New Tier 2 helper — expand around retrieval candidates
# =============================================================================

# Pull a bounded 1-hop neighbourhood around each candidate disease.
#
# Notes:
#   * `$candidate_ids` is the list of Candidate.disease_id strings.
#   * `$per_candidate` caps how many out-edges per disease — without this
#     a well-connected Disease like Diabetes Mellitus can have thousands
#     of phenotype edges and the query explodes.
#   * We return rows of (disease, phenotype, edge) so the context
#     builder can attribute edges back to specific candidates.
#
# This query is executed once per retrieval call (batched over all
# candidates), not once per candidate.
EXPAND_CANDIDATES_QUERY = """
UNWIND $candidate_ids AS cid
MATCH (d:Disease)
WHERE elementId(d) = cid
CALL (d) {
  MATCH (d)-[r]->(n)
  WHERE type(r) IN $allowed_types
    AND (n:Disease OR n:Phenotype OR n:Gene OR n:Drug)
  RETURN n, r
  ORDER BY type(r)
  LIMIT $per_candidate
}
RETURN
  elementId(d)          AS disease_id,
  d.name                AS disease_name,
  elementId(n)          AS neighbor_id,
  n.name                AS neighbor_name,
  labels(n)[0]          AS neighbor_label,
  type(r)               AS rel_type,
  elementId(r)          AS rel_id
"""


async def expand_candidates(
    candidates: list["Candidate"],
    neo4j_driver: "AsyncDriver",
    per_candidate: int = 15,
) -> tuple[list[dict], list[dict]]:
    """Expand 1 hop out from each candidate disease.

    The result is two flat lists (nodes, relationships) ready for the
    context builder. Nodes are de-duplicated by element_id. The
    candidates themselves are included in `nodes` so the LLM sees the
    full set.

    Args:
        candidates: Ranked retrieval candidates (from retrieval.py).
        neo4j_driver: Async Neo4j driver.
        per_candidate: Max out-edges per disease.

    Returns:
        Tuple of (nodes, relationships) as serializable dicts:
            node = {"id", "name", "type"}
            rel  = {"id", "source", "target", "type"}

    Empty candidates returns empty lists (not an error — retrieval.py
    is responsible for guaranteeing a non-empty set).
    """
    if not candidates:
        return [], []

    start = time.monotonic()
    nodes_by_id: dict[str, dict] = {}
    rels_by_id: dict[str, dict] = {}

    # Always include the candidate diseases themselves.
    for c in candidates:
        nodes_by_id[c.disease_id] = {
            "id": c.disease_id,
            "name": c.disease_name,
            "type": "Disease",
        }
        # Also include the phenotypes that matched via the retrieval
        # layer — they're the grounding evidence and must be visible
        # in the final graph the LLM sees.
        for e in c.matched_edges:
            nodes_by_id.setdefault(
                e.phenotype_id,
                {
                    "id": e.phenotype_id,
                    "name": e.phenotype_name,
                    "type": "Phenotype",
                },
            )
            # Synthetic edge key — we don't have Neo4j element IDs for
            # retrieval-matched edges, so use a deterministic composite.
            key = f"retrieval::{c.disease_id}::{e.phenotype_id}::{e.rel_type}"
            rels_by_id.setdefault(
                key,
                {
                    "id": key,
                    "source": c.disease_id,
                    "target": e.phenotype_id,
                    "type": e.rel_type,
                },
            )

    # Only graph-sourced candidates have element_ids we can query on.
    # Rule-only candidates may have element_ids too (from disease_index
    # lookup), so include them all.
    candidate_ids = [c.disease_id for c in candidates]

    async with neo4j_driver.session() as session:
        result = await session.run(
            EXPAND_CANDIDATES_QUERY,
            candidate_ids=candidate_ids,
            allowed_types=ALLOWED_EDGE_TYPES,
            per_candidate=per_candidate,
        )
        async for record in result:
            disease_id = record["disease_id"]
            disease_name = record["disease_name"]
            neighbor_id = record["neighbor_id"]
            neighbor_name = record["neighbor_name"]
            neighbor_label = record["neighbor_label"]
            rel_type = record["rel_type"]
            rel_id = record["rel_id"]

            nodes_by_id.setdefault(
                disease_id,
                {"id": disease_id, "name": disease_name, "type": "Disease"},
            )
            nodes_by_id.setdefault(
                neighbor_id,
                {
                    "id": neighbor_id,
                    "name": neighbor_name,
                    "type": neighbor_label or "Unknown",
                },
            )
            rels_by_id.setdefault(
                rel_id,
                {
                    "id": rel_id,
                    "source": disease_id,
                    "target": neighbor_id,
                    "type": rel_type,
                },
            )

    elapsed = time.monotonic() - start
    NEO4J_LATENCY.observe(elapsed)

    nodes = list(nodes_by_id.values())
    relationships = list(rels_by_id.values())

    logger.info(
        "subgraph_expand_complete",
        candidates=len(candidates),
        nodes=len(nodes),
        relationships=len(relationships),
        elapsed_ms=round(elapsed * 1000),
    )
    return nodes, relationships


# =============================================================================
# Legacy path — used by graph_rag_stream.py until it's migrated
# =============================================================================

# The production Cypher query.
#
# DESIGN NOTES:
#   * 2-hop traversal, not 3. The third hop produced mostly noise for
#     differential diagnosis and made the intermediate row count
#     explode into the tens of millions on the full PrimeKG subset
#     (48k nodes / 617k edges), blowing Neo4j's per-transaction
#     memory limit of ~2.8 GiB.
#
#   * LIMIT at each hop — the previous version only capped at the
#     very end of the query, so the cartesian product was fully
#     materialised in memory before being trimmed. Now we cap
#     (seed, r1, h1) at 120 rows and (..., r2, h2) at 400 rows, which
#     keeps per-query memory bounded regardless of graph fan-out.
#
#   * Directed edges only, parenthesised label OR, NULL filtering on
#     the OPTIONAL MATCH second hop. Pure Cypher, no APOC.
TRAVERSAL_QUERY = """
MATCH (seed)-[r1]->(h1)
WHERE elementId(seed) IN $seed_ids
  AND type(r1) IN $allowed_types
  AND (h1:Disease OR h1:Phenotype OR h1:Gene OR h1:Drug)
WITH seed, r1, h1
LIMIT 120

OPTIONAL MATCH (h1)-[r2]->(h2)
WHERE type(r2) IN $allowed_types
  AND (h2:Disease OR h2:Phenotype OR h2:Gene OR h2:Drug)
  AND h2 <> seed
WITH seed, r1, h1, r2, h2
LIMIT 400

WITH
  collect(DISTINCT seed) + collect(DISTINCT h1)
  + [x IN collect(DISTINCT h2) WHERE x IS NOT NULL] AS all_nodes,
  collect(DISTINCT r1)
  + [x IN collect(DISTINCT r2) WHERE x IS NOT NULL] AS all_rels

UNWIND all_nodes AS n
WITH DISTINCT n, all_rels
RETURN
  collect(DISTINCT {
    id: elementId(n),
    name: n.name,
    type: labels(n)[0]
  })[..50] AS nodes,
  [r IN all_rels[..200] | {
    source: elementId(startNode(r)),
    target: elementId(endNode(r)),
    type: type(r)
  }] AS relationships
"""


async def traverse_graph(
    seed_ids: list[str],
    neo4j_driver: "AsyncDriver",
    min_nodes: int = 3,
) -> tuple[list[dict], list[dict]]:
    """Legacy 2-hop traversal from vector-search seeds.

    Used by graph_rag_stream.py until that path is migrated to the
    new retrieval pipeline. New code should use `expand_candidates`.
    """
    start = time.monotonic()

    async with neo4j_driver.session() as session:
        result = await session.run(
            TRAVERSAL_QUERY,
            seed_ids=seed_ids,
            allowed_types=ALLOWED_EDGE_TYPES,
        )
        record = await result.single()

    elapsed = time.monotonic() - start
    NEO4J_LATENCY.observe(elapsed)

    if record is None:
        logger.warning("graph_traversal_empty", seed_count=len(seed_ids))
        raise GraphTraversalError("Graph traversal returned no results.")

    nodes: list[dict] = record["nodes"]
    relationships: list[dict] = record["relationships"]

    logger.info(
        "graph_traversal_complete",
        nodes=len(nodes),
        relationships=len(relationships),
        elapsed_ms=round(elapsed * 1000),
    )

    if len(nodes) < min_nodes:
        logger.warning(
            "graph_traversal_low_context",
            nodes=len(nodes),
            min_required=min_nodes,
        )

    return nodes, relationships


async def verify_disease_exists(
    disease_name: str,
    neo4j_driver: "AsyncDriver",
) -> bool:
    """Check if a disease name exists in Neo4j (case-insensitive)."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (d:Disease)
            WHERE toLower(d.name) = toLower($name)
            RETURN count(d) > 0 AS found
            """,
            name=disease_name,
        )
        record = await result.single()
        return record["found"] if record else False
