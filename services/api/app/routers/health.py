"""Health check endpoints — public, no auth required."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "healthy", "service": "pathodx"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe — checks downstream dependencies.

    For now, just returns healthy. In production, this would check
    Neo4j, Qdrant, and LLM provider availability.
    """
    return {"status": "ready", "service": "pathodx"}
