"""Langfuse v2 tracing integration.

Uses the stable Langfuse v2 API:
  - langfuse.trace(name=..., id=..., metadata=...)
  - trace.span(name=..., input=...)
  - span.end(output=..., level=...)

LLM calls are auto-traced via LiteLLM's built-in "langfuse" callback.
"""

from __future__ import annotations

import os

import structlog
from langfuse import Langfuse

from app.config import Settings

logger = structlog.get_logger()

_langfuse: Langfuse | None = None
_enabled: bool = False


def init_langfuse(settings: Settings) -> None:
    """Initialize Langfuse v2 client."""
    global _langfuse, _enabled

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("langfuse_skipped", reason="no keys configured")
        return

    # LiteLLM reads these from environment for its auto-tracing callback
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host

    _langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    _enabled = True
    logger.info("langfuse_initialized", host=settings.langfuse_host)


def configure_litellm_callbacks() -> None:
    """Register Langfuse as LiteLLM's success and failure callback."""
    if not _enabled:
        return

    import litellm

    callbacks = list(litellm.success_callback or [])
    if "langfuse" not in callbacks:
        callbacks.append("langfuse")
        litellm.success_callback = callbacks

    failure = list(litellm.failure_callback or [])
    if "langfuse" not in failure:
        failure.append("langfuse")
        litellm.failure_callback = failure

    logger.info("litellm_langfuse_callbacks_registered")


def get_langfuse() -> Langfuse | None:
    """Return the global Langfuse client (None if not configured)."""
    return _langfuse


def create_trace(name: str, request_id: str, metadata: dict | None = None):
    """Create a trace for the full request."""
    if not _enabled or _langfuse is None:
        return None
    return _langfuse.trace(
        name=name,
        id=request_id,
        metadata=metadata or {},
    )


def create_span(parent, name: str, input_data: dict | None = None):
    """Create a span under a trace or parent span."""
    if parent is None:
        return None
    return parent.span(name=name, input=input_data or {})


def end_span(span, output_data: dict | None = None, level: str = "DEFAULT"):
    """Finalize a span with output data."""
    if span is None:
        return
    span.end(output=output_data or {}, level=level)


def flush() -> None:
    """Flush pending traces to Langfuse."""
    if _enabled and _langfuse is not None:
        _langfuse.flush()
