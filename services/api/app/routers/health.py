"""Health check endpoints — public, no auth required.

/health   — liveness probe. Always 200 if the process is up.
/ready    — readiness probe. 200 only if Neo4j + Qdrant are reachable.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.dependencies import get_neo4j, get_qdrant

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Liveness probe — always returns 200 if the process is running.

    Used by Fly.io / Kubernetes to know whether to restart the container.
    Should be cheap and never depend on external services.
    """
    return {"status": "healthy", "service": "pathodx"}


@router.get("/ready", summary="Readiness probe")
async def ready() -> JSONResponse:
    """Readiness probe — returns 200 only if all downstream services are up.

    Checked by load balancers before routing traffic. Returns 503 if any
    component is down so the orchestrator knows not to send requests yet.
    """
    started = time.monotonic()
    checks: dict[str, dict[str, object]] = {}
    all_ok = True

    # ---- Neo4j ----
    try:
        neo4j_driver = get_neo4j()
    except Exception as exc:  # noqa: BLE001
        checks["neo4j"] = {"ok": False, "error": str(exc)}
        all_ok = False
    else:
        try:
            t0 = time.monotonic()
            async with neo4j_driver.session() as session:
                result = await asyncio.wait_for(session.run("RETURN 1 AS ok"), timeout=2.0)
                record = await result.single()
                if record and record.get("ok") == 1:
                    checks["neo4j"] = {
                        "ok": True,
                        "elapsed_ms": round((time.monotonic() - t0) * 1000),
                    }
                else:
                    checks["neo4j"] = {"ok": False, "error": "unexpected response"}
                    all_ok = False
        except Exception as exc:  # noqa: BLE001
            checks["neo4j"] = {"ok": False, "error": str(exc)}
            all_ok = False

    # ---- Qdrant ----
    try:
        qdrant_client = get_qdrant()
    except Exception as exc:  # noqa: BLE001
        checks["qdrant"] = {"ok": False, "error": str(exc)}
        all_ok = False
    else:
        try:
            t0 = time.monotonic()
            collections = await asyncio.wait_for(qdrant_client.get_collections(), timeout=2.0)
            checks["qdrant"] = {
                "ok": True,
                "collections": len(collections.collections),
                "elapsed_ms": round((time.monotonic() - t0) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            checks["qdrant"] = {"ok": False, "error": str(exc)}
            all_ok = False

    body = {
        "status": "ready" if all_ok else "not_ready",
        "service": "pathodx",
        "checks": checks,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }

    if not all_ok:
        logger.warning("readiness_check_failed", checks=checks)

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )
