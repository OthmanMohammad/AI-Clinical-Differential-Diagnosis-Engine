"""GET /api/v1/graph/{node_id} — Graph exploration endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver

from app.dependencies import get_neo4j, verify_api_key

logger = structlog.get_logger()

router = APIRouter(tags=["graph"])


@router.get(
    "/graph/{node_id}",
    summary="Get node neighborhood",
    description="Retrieve a single node and its immediate neighbors from the knowledge graph.",
)
async def get_node_neighborhood(
    node_id: str,
    _api_key: str = Depends(verify_api_key),
    neo4j_driver: AsyncDriver = Depends(get_neo4j),
) -> dict:
    """Return a node and its 1-hop neighborhood."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE elementId(n) = $node_id
            OPTIONAL MATCH (n)-[r]-(neighbor)
            RETURN
              {id: elementId(n), name: n.name, type: labels(n)[0], properties: properties(n)} AS node,
              collect(DISTINCT {
                id: elementId(neighbor),
                name: neighbor.name,
                type: labels(neighbor)[0]
              })[..20] AS neighbors,
              collect(DISTINCT {
                source: elementId(startNode(r)),
                target: elementId(endNode(r)),
                type: type(r)
              })[..50] AS relationships
            """,
            node_id=node_id,
        )
        record = await result.single()

    if record is None or record["node"] is None:
        raise HTTPException(status_code=404, detail="Node not found")

    return {
        "node": record["node"],
        "neighbors": record["neighbors"],
        "relationships": record["relationships"],
    }
