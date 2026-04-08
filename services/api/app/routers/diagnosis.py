"""POST /api/v1/diagnose — Main diagnosis endpoint."""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from slowapi import Limiter

from app.config import Settings, get_settings
from app.core.graph_rag import run_diagnosis_pipeline
from app.core.llm_client import LLMError, LLMSchemaError
from app.core.vector_search import NoSeedNodesError
from app.dependencies import get_neo4j, get_qdrant, verify_api_key
from app.guardrails.input_validator import InputValidationError
from app.models.diagnosis import DiagnosisResponse
from app.models.patient import PatientIntake
from app.observability.metrics import ERRORS, REQUEST_LATENCY

logger = structlog.get_logger()

router = APIRouter(tags=["diagnosis"])


def get_real_ip(request: Request) -> str:
    return request.headers.get("fly-client-ip", request.client.host if request.client else "unknown")


limiter = Limiter(key_func=get_real_ip)


@router.post(
    "/diagnose",
    response_model=DiagnosisResponse,
    summary="Generate differential diagnosis",
    description=(
        "Submit patient intake data and receive a ranked differential diagnosis "
        "powered by Graph RAG + LLM reasoning."
    ),
)
async def diagnose(
    intake: PatientIntake,
    request: Request,
    _api_key: str = Depends(verify_api_key),
    neo4j_driver: AsyncDriver = Depends(get_neo4j),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant),
    settings: Settings = Depends(get_settings),
) -> DiagnosisResponse:
    """Run the full diagnosis pipeline."""
    request_id = getattr(request.state, "request_id", "unknown")
    start = time.monotonic()

    try:
        response = await run_diagnosis_pipeline(
            intake=intake,
            neo4j_driver=neo4j_driver,
            qdrant_client=qdrant_client,
            request_id=request_id,
        )

        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="200").observe(elapsed)

        return response

    except InputValidationError as exc:
        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="400").observe(elapsed)
        ERRORS.labels(error_type="input_validation").inc()
        raise HTTPException(
            status_code=400,
            detail={
                "type": "about:blank",
                "title": "Input Validation Failed",
                "status": 400,
                "detail": exc.detail,
                "gate": exc.gate,
            },
        ) from exc

    except NoSeedNodesError as exc:
        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="422").observe(elapsed)
        ERRORS.labels(error_type="no_seed_nodes").inc()
        raise HTTPException(
            status_code=422,
            detail={
                "type": "about:blank",
                "title": "No Matching Concepts",
                "status": 422,
                "detail": str(exc),
            },
        ) from exc

    except LLMSchemaError as exc:
        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="502").observe(elapsed)
        ERRORS.labels(error_type="llm_schema").inc()
        logger.error("llm_schema_error", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "type": "about:blank",
                "title": "LLM Output Error",
                "status": 502,
                "detail": "LLM returned malformed output. Please retry.",
            },
        ) from exc

    except LLMError as exc:
        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="503").observe(elapsed)
        ERRORS.labels(error_type="llm_unavailable").inc()
        logger.error("llm_unavailable", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "type": "about:blank",
                "title": "Service Unavailable",
                "status": 503,
                "detail": str(exc),
            },
        ) from exc

    except Exception as exc:
        elapsed = time.monotonic() - start
        REQUEST_LATENCY.labels(endpoint="/api/v1/diagnose", status_code="500").observe(elapsed)
        ERRORS.labels(error_type="internal").inc()
        logger.exception("unhandled_error", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred. Please retry.",
            },
        ) from exc
