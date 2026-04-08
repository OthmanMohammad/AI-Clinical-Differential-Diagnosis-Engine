"""Structured logging and Prometheus metrics."""

from __future__ import annotations

import structlog
from prometheus_client import Counter, Histogram

# --- Prometheus metrics ---

REQUEST_LATENCY = Histogram(
    "pathodx_request_latency_seconds",
    "Total request latency",
    ["endpoint", "status_code"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

LLM_LATENCY = Histogram(
    "pathodx_llm_latency_seconds",
    "LLM call latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

NEO4J_LATENCY = Histogram(
    "pathodx_neo4j_latency_seconds",
    "Neo4j query latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)

QDRANT_LATENCY = Histogram(
    "pathodx_qdrant_latency_seconds",
    "Qdrant search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5],
)

GATE_TRIGGERS = Counter(
    "pathodx_gate_triggers_total",
    "Guardrail gate trigger count",
    ["gate_name", "result"],
)

EMERGENCY_TRIGGERS = Counter(
    "pathodx_emergency_triggers_total",
    "Emergency pattern triggers",
    ["pattern_name"],
)

ERRORS = Counter(
    "pathodx_errors_total",
    "Error count by type",
    ["error_type"],
)


# --- Structured logging ---

def configure_logging(environment: str) -> None:
    """Configure structlog for JSON output."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
