"""Structured logging and Prometheus metrics."""

from __future__ import annotations

import structlog
from prometheus_client import Counter, Histogram

# --- Prometheus metrics ---

REQUEST_LATENCY = Histogram(
    "mooseglove_request_latency_seconds",
    "Total request latency",
    ["endpoint", "status_code"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

LLM_LATENCY = Histogram(
    "mooseglove_llm_latency_seconds",
    "LLM call latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

NEO4J_LATENCY = Histogram(
    "mooseglove_neo4j_latency_seconds",
    "Neo4j query latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)

QDRANT_LATENCY = Histogram(
    "mooseglove_qdrant_latency_seconds",
    "Qdrant search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5],
)

GATE_TRIGGERS = Counter(
    "mooseglove_gate_triggers_total",
    "Guardrail gate trigger count",
    ["gate_name", "result"],
)

EMERGENCY_TRIGGERS = Counter(
    "mooseglove_emergency_triggers_total",
    "Emergency pattern triggers",
    ["pattern_name"],
)

ERRORS = Counter(
    "mooseglove_errors_total",
    "Error count by type",
    ["error_type"],
)


# --- Structured logging ---


def configure_logging(environment: str) -> None:
    """Configure structlog for JSON output and silence noisy third-party loggers."""
    import logging

    # Silence noisy third-party loggers — they spam DEBUG/INFO output
    # that drowns out actual application logs
    noisy_loggers = {
        "PyRuSH": logging.WARNING,
        "PyRuSH.PyRuSHSentencizer": logging.WARNING,
        "medspacy": logging.WARNING,
        "spacy": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "huggingface_hub": logging.WARNING,
        "fastembed": logging.WARNING,
        "urllib3": logging.WARNING,
        "neo4j.notifications": logging.ERROR,
        "neo4j.pool": logging.WARNING,
        "LiteLLM": logging.WARNING,
        "litellm": logging.WARNING,
        "openai": logging.WARNING,
    }
    for logger_name, level in noisy_loggers.items():
        logging.getLogger(logger_name).setLevel(level)

    # Also disable loguru for PyRuSH which uses it separately
    try:
        from loguru import logger as loguru_logger

        loguru_logger.remove()
        loguru_logger.add(lambda msg: None, level="ERROR")  # swallow all loguru logs
    except ImportError:
        pass

    # Base processors common to both environments
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if environment == "production":
        # JSONRenderer needs format_exc_info to stringify exceptions
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # ConsoleRenderer handles exceptions itself — don't pre-format
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set root logger level for app's own loggers
    logging.getLogger("app").setLevel(logging.INFO)
