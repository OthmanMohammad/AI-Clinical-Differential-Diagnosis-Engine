"""FastAPI dependency injection — DB clients, auth, settings."""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from neo4j import AsyncDriver, AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient

from app.config import Settings, get_settings

logger = structlog.get_logger()

# API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Singleton clients (initialized at startup, closed at shutdown)
_neo4j_driver: AsyncDriver | None = None
_qdrant_client: AsyncQdrantClient | None = None


async def init_neo4j(settings: Settings) -> None:
    """Initialize Neo4j async driver. Called at app startup."""
    global _neo4j_driver
    _neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=settings.neo4j_query_timeout,
        max_transaction_retry_time=settings.neo4j_query_timeout,
    )
    logger.info("neo4j_driver_initialized", uri=settings.neo4j_uri)


async def close_neo4j() -> None:
    """Close Neo4j driver. Called at app shutdown."""
    global _neo4j_driver
    if _neo4j_driver:
        await _neo4j_driver.close()
        _neo4j_driver = None
        logger.info("neo4j_driver_closed")


async def init_qdrant(settings: Settings) -> None:
    """Initialize Qdrant async client. Called at app startup."""
    global _qdrant_client
    _qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=5,
    )
    logger.info("qdrant_client_initialized", url=settings.qdrant_url)


async def close_qdrant() -> None:
    """Close Qdrant client. Called at app shutdown."""
    global _qdrant_client
    if _qdrant_client:
        await _qdrant_client.close()
        _qdrant_client = None
        logger.info("qdrant_client_closed")


def get_neo4j() -> AsyncDriver:
    """Dependency: get the Neo4j driver."""
    if _neo4j_driver is None:
        raise HTTPException(status_code=503, detail="Neo4j connection not available")
    return _neo4j_driver


def get_qdrant() -> AsyncQdrantClient:
    """Dependency: get the Qdrant client."""
    if _qdrant_client is None:
        raise HTTPException(status_code=503, detail="Qdrant connection not available")
    return _qdrant_client


def get_neo4j_or_none() -> AsyncDriver | None:
    """Lifespan-safe accessor that returns None instead of raising HTTPException.
    Used by startup tasks that need the driver but cannot raise HTTP errors."""
    return _neo4j_driver


def get_qdrant_or_none() -> AsyncQdrantClient | None:
    """Lifespan-safe accessor for the Qdrant client."""
    return _qdrant_client


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Dependency: validate the API key from X-API-Key header."""
    # Health endpoint is public
    if request.url.path in ("/health", "/ready"):
        return "public"

    if not api_key or api_key != settings.api_key:
        logger.warning("auth_failed", path=request.url.path)
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return api_key
