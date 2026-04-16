"""MooseGlove API — Clinical Differential Diagnosis Engine.

Application entry point. This module wires together:

  - Configuration (CORS, rate limits, body size, timeouts)
  - Lifespan (preload models, connect to Neo4j/Qdrant/Langfuse on startup,
    cleanly close them on shutdown)
  - Middleware (request ID, timeout, security headers, body size limit)
  - Routers (health, metadata, diagnosis, diagnosis stream, graph)
  - Observability (/metrics for Prometheus, structured logging)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import litellm
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.core.vector_search import preload_embedder
from app.dependencies import (
    close_neo4j,
    close_qdrant,
    get_neo4j_or_none,
    init_neo4j,
    init_qdrant,
)
from app.guardrails.emergency import preload_nlp
from app.guardrails.output_validator import preload_disease_cache
from app.observability.langfuse_client import configure_litellm_callbacks, init_langfuse
from app.observability.metrics import configure_logging
from app.rate_limit import limiter
from app.routers import diagnosis, diagnosis_stream, graph, health, metadata

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle.

    Startup order is important — preloading happens AFTER connections are
    established, because the disease cache needs Neo4j and the embedder
    pre-warm needs the local model files.
    """
    settings = get_settings()
    configure_logging(settings.environment)

    logger.info(
        "starting_mooseglove",
        environment=settings.environment,
        cors_origins=settings.cors_origin_list,
    )

    # ---- 1. External connections ----
    await init_neo4j(settings)
    await init_qdrant(settings)
    init_langfuse(settings)

    # ---- 2. LiteLLM provider setup ----
    litellm.telemetry = False
    litellm.drop_params = True

    if settings.groq_api_key:
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.cerebras_api_key:
        os.environ["CEREBRAS_API_KEY"] = settings.cerebras_api_key

    # Register Langfuse as LiteLLM callback (after env vars are set)
    configure_litellm_callbacks()

    # ---- 3. Preload heavy models so first request is fast ----
    # Run in a thread so we don't block the event loop.
    logger.info("preloading_models")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, preload_nlp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("nlp_preload_failed", error=str(exc))
    try:
        await loop.run_in_executor(None, preload_embedder)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedder_preload_failed", error=str(exc))

    # ---- 4. Preload the disease cache for the hallucination gate ----
    neo4j_driver = get_neo4j_or_none()
    if neo4j_driver is not None:
        try:
            await preload_disease_cache(neo4j_driver)
        except Exception as exc:  # noqa: BLE001
            logger.warning("disease_cache_preload_failed", error=str(exc))

    logger.info("mooseglove_started")
    yield

    # ---- Shutdown ----
    logger.info("stopping_mooseglove")
    await close_neo4j()
    await close_qdrant()
    logger.info("mooseglove_stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_app_settings = get_settings()

app = FastAPI(
    title="MooseGlove",
    description="Clinical Differential Diagnosis Engine",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _app_settings.is_production else "/docs",
    redoc_url=None if _app_settings.is_production else "/redoc",
    openapi_url=None if _app_settings.is_production else "/openapi.json",
)

# CORS — locked to configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_app_settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Accept"],
    expose_headers=["X-Request-ID"],
)

# Rate limiter — endpoints opt in via decorators in their routers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Prometheus /metrics — scrape-ready
app.mount("/metrics", make_asgi_app())


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Inject a unique request ID into every request and bind it to logs."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def body_size_limit(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Reject requests whose Content-Length exceeds the configured cap."""
    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError:
            length = 0
        if length > settings.max_request_body_bytes:
            logger.warning(
                "request_body_too_large",
                length=length,
                limit=settings.max_request_body_bytes,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "type": "about:blank",
                    "title": "Payload Too Large",
                    "status": 413,
                    "detail": f"Request body exceeds {settings.max_request_body_bytes} bytes",
                },
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add basic security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "interest-cohort=()")
    if get_settings().is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def timeout_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Enforce a total request timeout."""
    settings = get_settings()
    try:
        return await asyncio.wait_for(
            call_next(request),
            timeout=float(settings.request_timeout),
        )
    except TimeoutError:
        logger.error("request_timeout", path=request.url.path)
        return JSONResponse(
            status_code=504,
            content={
                "type": "about:blank",
                "title": "Gateway Timeout",
                "status": 504,
                "detail": "Request timed out",
            },
        )


# ---------------------------------------------------------------------------
# Exception handlers — sanitize errors in production
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Format HTTPException as RFC 7807 Problem Details."""
    detail = exc.detail
    if isinstance(detail, dict):
        body = detail
    else:
        body = {
            "type": "about:blank",
            "title": _status_phrase(exc.status_code),
            "status": exc.status_code,
            "detail": str(detail),
        }
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a clean validation error without leaking internal field paths in prod."""
    settings = get_settings()
    if settings.is_production:
        body = {
            "type": "about:blank",
            "title": "Bad Request",
            "status": 422,
            "detail": "Request validation failed",
        }
    else:
        body = {
            "type": "about:blank",
            "title": "Bad Request",
            "status": 422,
            "detail": "Request validation failed",
            "errors": exc.errors(),
        }
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Logs the full trace but only
    returns a generic message to the client in production."""
    settings = get_settings()
    logger.exception("unhandled_exception", path=request.url.path)
    if settings.is_production:
        body = {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred",
        }
    else:
        body = {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": str(exc),
        }
    return JSONResponse(status_code=500, content=body)


def _status_phrase(code: int) -> str:
    return {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        413: "Payload Too Large",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }.get(code, "Error")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(diagnosis.router, prefix="/api/v1")
app.include_router(diagnosis_stream.router, prefix="/api/v1")
app.include_router(graph.router, prefix="/api/v1")
app.include_router(metadata.router, prefix="/api/v1")
