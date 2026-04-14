"""POST /api/v1/diagnose/stream — Server-Sent Events diagnosis endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient

from app.core.graph_rag_stream import run_diagnosis_pipeline_stream
from app.dependencies import get_neo4j, get_qdrant, verify_api_key
from app.models.patient import PatientIntake

logger = structlog.get_logger()

router = APIRouter(tags=["diagnosis"])


@router.post(
    "/diagnose/stream",
    summary="Streaming differential diagnosis (SSE)",
    description=(
        "Server-Sent Events endpoint that yields pipeline stage events as they "
        "run, followed by the final DiagnosisResponse. Use this for real-time "
        "progress indicators in the UI."
    ),
)
async def diagnose_stream(
    intake: PatientIntake,
    request: Request,
    _api_key: str = Depends(verify_api_key),
    neo4j_driver: AsyncDriver = Depends(get_neo4j),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant),
) -> StreamingResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.info("diagnose_stream.start", request_id=request_id)

    generator = run_diagnosis_pipeline_stream(
        intake=intake,
        neo4j_driver=neo4j_driver,
        qdrant_client=qdrant_client,
        request_id=request_id,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
