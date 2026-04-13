"""Langfuse v3 tracing integration.

Uses the OpenTelemetry-based span API introduced in Langfuse v3.
LiteLLM integration is handled via environment variables + callback strings.
"""

from __future__ import annotations

import os

import structlog

from app.config import Settings

logger = structlog.get_logger()

_langfuse = None  # type: ignore[var-annotated]
_enabled: bool = False


def init_langfuse(settings: Settings) -> None:
    """Initialize Langfuse v3 client and configure LiteLLM callbacks."""
    global _langfuse, _enabled

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("langfuse_skipped", reason="no keys configured")
        return

    # LiteLLM reads Langfuse config from environment variables
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host

    from langfuse import Langfuse

    _langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    _enabled = True
    logger.info("langfuse_initialized", host=settings.langfuse_host)


def configure_litellm_callbacks() -> None:
    """Wire LiteLLM success/failure callbacks to Langfuse (v3 style)."""
    if not _enabled:
        return

    import litellm

    # v3 uses the string-based callback registration
    if "langfuse" not in (litellm.success_callback or []):
        litellm.success_callback = [*(litellm.success_callback or []), "langfuse"]
    if "langfuse" not in (litellm.failure_callback or []):
        litellm.failure_callback = [*(litellm.failure_callback or []), "langfuse"]

    logger.info("litellm_langfuse_callbacks_registered")


def get_langfuse():
    """Get the Langfuse client (may be None if not configured)."""
    return _langfuse


def create_trace(name: str, request_id: str, metadata: dict | None = None):
    """Create a root span that acts as the request trace.

    Returns a Langfuse v3 span object (or None if disabled).
    """
    if not _enabled or _langfuse is None:
        return None

    span = _langfuse.start_span(
        name=name,
        input={"request_id": request_id, **(metadata or {})},
    )
    return span


def create_span(parent, name: str, input_data: dict | None = None):
    """Create a child span under a parent span."""
    if parent is None:
        return None
    return parent.start_span(name=name, input=input_data or {})


def end_span(span, output_data: dict | None = None, level: str = "DEFAULT"):
    """End a span with output data."""
    if span is None:
        return
    if output_data:
        span.update(output=output_data)
    span.end()


def flush() -> None:
    """Flush pending traces to Langfuse server (call at request end)."""
    if _enabled and _langfuse is not None:
        try:
            _langfuse.flush()
        except Exception as exc:
            logger.debug("langfuse_flush_failed", error=str(exc))
