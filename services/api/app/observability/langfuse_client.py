"""Langfuse v4 integration with graceful fallback across SDK versions.

Langfuse v4 uses `start_observation(as_type="span", ...)` and
`start_as_current_observation(...)`. Older versions used `start_span()`
(v3) or `trace()` (v2). This module detects the available API at runtime.

LLM calls are also auto-traced via LiteLLM's "langfuse" string callback,
which Langfuse's own LiteLLM integration hooks into.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from app.config import Settings

logger = structlog.get_logger()

_langfuse: Any = None
_enabled: bool = False
_span_method: str | None = None  # The method name we detected on the client


def _detect_span_method(client: Any) -> str | None:
    """Figure out which method to call for creating a span on this SDK version."""
    candidates = [
        "start_observation",           # v4.x
        "start_span",                  # v3.x
        "start_as_current_observation",  # v4.x context manager
        "start_as_current_span",       # v3.x context manager
        "trace",                       # v2.x
    ]
    for name in candidates:
        if hasattr(client, name):
            return name
    return None


def init_langfuse(settings: Settings) -> None:
    """Initialize Langfuse client and detect the span-creation API."""
    global _langfuse, _enabled, _span_method

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("langfuse_skipped", reason="no keys configured")
        return

    # LiteLLM reads these from environment for its auto-tracing callback
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _span_method = _detect_span_method(_langfuse)
        _enabled = True
        logger.info(
            "langfuse_initialized",
            host=settings.langfuse_host,
            span_method=_span_method,
        )
    except Exception as exc:
        logger.warning("langfuse_init_failed", error=str(exc))


def configure_litellm_callbacks() -> None:
    """Register Langfuse as a LiteLLM callback for automatic LLM-call tracing."""
    if not _enabled:
        return

    try:
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
    except Exception as exc:
        logger.warning("litellm_langfuse_callback_failed", error=str(exc))


def _call_span_method(parent: Any, name: str, input_data: dict | None) -> Any:
    """Call whichever span-creation method is available, returning a span object."""
    target = parent if parent is not None else _langfuse
    if target is None or _span_method is None:
        return None

    method = getattr(target, _span_method, None)
    if method is None:
        # Parent doesn't have the same method — try creating from the root client
        method = getattr(_langfuse, _span_method, None)
        if method is None:
            return None

    kwargs: dict[str, Any] = {"name": name}
    if input_data:
        kwargs["input"] = input_data

    # v4: start_observation / start_as_current_observation take as_type
    if _span_method and "observation" in _span_method:
        kwargs["as_type"] = "span"

    try:
        return method(**kwargs)
    except TypeError:
        # Some versions don't accept `input` or `as_type` — retry minimal
        try:
            return method(name=name)
        except Exception as exc:
            logger.debug("langfuse_span_create_failed", error=str(exc))
            return None
    except Exception as exc:
        logger.debug("langfuse_span_create_failed", error=str(exc))
        return None


def create_trace(name: str, request_id: str, metadata: dict | None = None):
    """Create a root span/trace for the request."""
    if not _enabled:
        return None
    input_data = {"request_id": request_id, **(metadata or {})}
    return _call_span_method(None, name, input_data)


def create_span(parent, name: str, input_data: dict | None = None):
    """Create a child span under a parent."""
    if parent is None or not _enabled:
        return None
    return _call_span_method(parent, name, input_data)


def end_span(span, output_data: dict | None = None, level: str = "DEFAULT"):  # noqa: ARG001
    """Finalize a span with output data."""
    if span is None:
        return
    try:
        if output_data and hasattr(span, "update"):
            span.update(output=output_data)
        if hasattr(span, "end"):
            span.end()
        elif hasattr(span, "__exit__"):
            # Context manager style — close it
            span.__exit__(None, None, None)
    except Exception as exc:
        logger.debug("langfuse_span_end_failed", error=str(exc))


def flush() -> None:
    """Flush pending traces to Langfuse."""
    if _enabled and _langfuse is not None:
        try:
            if hasattr(_langfuse, "flush"):
                _langfuse.flush()
        except Exception as exc:
            logger.debug("langfuse_flush_failed", error=str(exc))
