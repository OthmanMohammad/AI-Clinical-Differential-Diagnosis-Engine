"""PathoDX API — Clinical Differential Diagnosis Engine."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import litellm
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.dependencies import close_neo4j, close_qdrant, init_neo4j, init_qdrant
from app.observability.langfuse_client import configure_litellm_callbacks, init_langfuse
from app.observability.metrics import configure_logging
from app.routers import diagnosis, diagnosis_stream, graph, health, metadata

logger = structlog.get_logger()


def get_real_ip(request: Request) -> str:
    """Extract real client IP behind Fly.io proxy."""
    return request.headers.get("fly-client-ip", request.client.host if request.client else "unknown")


limiter = Limiter(key_func=get_real_ip)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    configure_logging(settings.environment)

    # Startup
    logger.info("starting_pathodx", environment=settings.environment)

    await init_neo4j(settings)
    await init_qdrant(settings)
    init_langfuse(settings)

    # Configure LiteLLM
    litellm.telemetry = False
    litellm.drop_params = True

    # Set provider API keys in environment for LiteLLM
    import os
    if settings.groq_api_key:
        os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.cerebras_api_key:
        os.environ["CEREBRAS_API_KEY"] = settings.cerebras_api_key

    # Register Langfuse as LiteLLM callback (must happen after env vars are set)
    configure_litellm_callbacks()

    logger.info("pathodx_started")
    yield

    # Shutdown
    logger.info("stopping_pathodx")
    await close_neo4j()
    await close_qdrant()
    logger.info("pathodx_stopped")


app = FastAPI(
    title="PathoDX",
    description="AI Clinical Differential Diagnosis Engine",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Inject a unique request ID into every request."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Timeout middleware
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    """Enforce a total request timeout."""
    settings = get_settings()
    try:
        return await asyncio.wait_for(
            call_next(request),
            timeout=float(settings.request_timeout),
        )
    except asyncio.TimeoutError:
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


# Routers
app.include_router(health.router)
app.include_router(diagnosis.router, prefix="/api/v1")
app.include_router(diagnosis_stream.router, prefix="/api/v1")
app.include_router(graph.router, prefix="/api/v1")
app.include_router(metadata.router, prefix="/api/v1")
