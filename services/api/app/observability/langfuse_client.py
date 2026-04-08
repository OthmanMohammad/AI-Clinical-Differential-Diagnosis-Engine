"""Langfuse tracing integration."""

from __future__ import annotations

import structlog
from langfuse import Langfuse

from app.config import Settings

logger = structlog.get_logger()

_langfuse: Langfuse | None = None


def init_langfuse(settings: Settings) -> None:
    """Initialize Langfuse client if keys are configured."""
    global _langfuse
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse_initialized")
    else:
        logger.info("langfuse_skipped", reason="no keys configured")


def get_langfuse() -> Langfuse | None:
    """Get the Langfuse client (may be None if not configured)."""
    return _langfuse


def get_langfuse_callback():
    """Get LiteLLM-compatible Langfuse callback handler."""
    if _langfuse is None:
        return None
    try:
        from langfuse.callback import CallbackHandler
        return CallbackHandler(
            public_key=_langfuse.client._public_key,
            secret_key=_langfuse.client._secret_key,
            host=_langfuse.client._base_url,
        )
    except Exception:
        logger.warning("langfuse_callback_failed")
        return None


def create_trace(
    name: str,
    request_id: str,
    metadata: dict | None = None,
):
    """Create a Langfuse trace for a request."""
    if _langfuse is None:
        return None
    return _langfuse.trace(
        name=name,
        id=request_id,
        metadata=metadata or {},
    )


def create_span(trace, name: str, input_data: dict | None = None):
    """Create a span within a trace."""
    if trace is None:
        return None
    return trace.span(name=name, input=input_data or {})


def end_span(span, output_data: dict | None = None, level: str = "DEFAULT"):
    """End a span with output data."""
    if span is None:
        return
    span.end(output=output_data or {}, level=level)
