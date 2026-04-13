"""Langfuse tracing integration — fully optional, version-agnostic.

If Langfuse is not configured or the installed version has an incompatible API,
all tracing calls become no-ops. The pipeline continues to work.
"""

from __future__ import annotations

import structlog

from app.config import Settings

logger = structlog.get_logger()

_langfuse = None  # type: ignore[var-annotated]


def init_langfuse(settings: Settings) -> None:
    """Initialize Langfuse client if keys are configured."""
    global _langfuse
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("langfuse_skipped", reason="no keys configured")
        return

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse_initialized")
    except Exception as exc:
        logger.warning("langfuse_init_failed", error=str(exc))
        _langfuse = None


def get_langfuse():
    """Get the Langfuse client (may be None if not configured)."""
    return _langfuse


def get_langfuse_callback():
    """Get LiteLLM-compatible Langfuse callback handler."""
    if _langfuse is None:
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler()
    except Exception as exc:
        logger.debug("langfuse_callback_unavailable", error=str(exc))
        return None


def create_trace(name: str, request_id: str, metadata: dict | None = None):
    """Create a trace — returns None if Langfuse unavailable or API mismatch."""
    if _langfuse is None:
        return None
    try:
        # Try v2.x API
        if hasattr(_langfuse, "trace"):
            return _langfuse.trace(name=name, id=request_id, metadata=metadata or {})
        # Try v3.x API
        if hasattr(_langfuse, "start_as_current_span"):
            return _langfuse.start_as_current_span(name=name)
    except Exception as exc:
        logger.debug("langfuse_trace_failed", error=str(exc))
    return None


def create_span(trace, name: str, input_data: dict | None = None):
    """Create a span within a trace — returns None gracefully on any error."""
    if trace is None:
        return None
    try:
        if hasattr(trace, "span"):
            return trace.span(name=name, input=input_data or {})
    except Exception as exc:
        logger.debug("langfuse_span_failed", error=str(exc))
    return None


def end_span(span, output_data: dict | None = None, level: str = "DEFAULT"):
    """End a span with output data — no-op if span is None or API mismatch."""
    if span is None:
        return
    try:
        if hasattr(span, "end"):
            span.end(output=output_data or {}, level=level)
    except Exception as exc:
        logger.debug("langfuse_end_failed", error=str(exc))
