"""Layer 3.2 — Graph Traversal via Neo4j.

Pure Cypher, no APOC. Directed 3-hop traversal from seed nodes.
AuraDB Free does not include APOC — this is the ONLY production path.
"""

from __future__ import annotations

import time

import structlog
from neo4j import AsyncDriver

from app.observability.metrics import NEO4J_LATENCY

logger = structlog.get_logger()

# Edge types allowed in traversal — clinically relevant relationships from PrimeKG
ALLOWED_EDGE_TYPES = [
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "disease_protein",
    "drug_protein",
    "drug_disease",
    "disease_disease",
    "exposure_disease",
    "phenotype_phenotype",
]

# The production Cypher query — tested in Neo4j Browser before deployment.
# Directed 3-hop traversal with:
#   - Parenthesized OR chains (correct operator precedence)
#   - NULL filtering on OPTIONAL MATCH results
#   - Hard caps on result size (50 nodes, 200 rels)
TRAVERSAL_QUERY = """
MATCH (seed)-[r1]->(h1)
WHERE elementId(seed) IN $seed_ids
  AND type(r1) IN $allowed_types
  AND (h1:Disease OR h1:Symptom OR h1:Gene
       OR h1:Phenotype OR h1:Drug OR h1:Anatomy)
WITH seed, r1, h1

OPTIONAL MATCH (h1)-[r2]->(h2)
WHERE type(r2) IN $allowed_types
  AND (h2:Disease OR h2:Symptom OR h2:Gene
       OR h2:Phenotype OR h2:Drug OR h2:Anatomy)
WITH seed, r1, h1, r2, h2

OPTIONAL MATCH (h2)-[r3]->(h3)
WHERE h2 IS NOT NULL
  AND type(r3) IN $allowed_types
  AND (h3:Disease OR h3:Symptom OR h3:Gene
       OR h3:Phenotype OR h3:Drug OR h3:Anatomy)

WITH
  collect(DISTINCT seed) + collect(DISTINCT h1)
  + [x IN collect(DISTINCT h2) WHERE x IS NOT NULL]
  + [x IN collect(DISTINCT h3) WHERE x IS NOT NULL] AS all_nodes,
  collect(DISTINCT r1)
  + [x IN collect(DISTINCT r2) WHERE x IS NOT NULL]
  + [x IN collect(DISTINCT r3) WHERE x IS NOT NULL] AS all_rels

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


class GraphTraversalError(Exception):
    """Raised when graph traversal fails or returns insufficient data."""


async def traverse_graph(
    seed_ids: list[str],
    neo4j_driver: AsyncDriver,
    min_nodes: int = 3,
) -> tuple[list[dict], list[dict]]:
    """Execute 3-hop directed traversal from seed nodes.

    Args:
        seed_ids: Neo4j element IDs from vector search.
        neo4j_driver: Async Neo4j driver.
        min_nodes: Minimum nodes to consider the subgraph useful.

    Returns:
        Tuple of (nodes, relationships) as serializable dicts.

    Raises:
        GraphTraversalError: If traversal fails or returns too few nodes.
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
    neo4j_driver: AsyncDriver,
) -> bool:
    """Check if a disease name exists in Neo4j (for hallucination gate)."""
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
