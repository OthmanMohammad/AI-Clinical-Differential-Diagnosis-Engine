"""Streaming variant of the diagnosis pipeline.

Yields Server-Sent Event payloads describing each pipeline stage as it
runs so the frontend can render a live progress indicator. The final
event includes the fully-validated DiagnosisResponse.

Event schema (the `data` field of each SSE frame is a JSON object):
  {"type": "stage_start", "stage": "<name>"}
  {"type": "stage_end",   "stage": "<name>", "elapsed_ms": 123, "data": "..."}
  {"type": "emergency",   "data": { ... EmergencyResult ... }}
  {"type": "diagnosis_ready", "data": { ... DiagnosisResponse ... }}
  {"type": "error",       "message": "..."}
  {"type": "done"}
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import structlog
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient

from app.core.context_builder import build_messages
from app.core.graph_traversal import traverse_graph
from app.core.llm_client import LLMError, LLMSchemaError, call_llm
from app.core.vector_search import NoSeedNodesError, get_seed_nodes
from app.config import get_settings
from app.guardrails.emergency import check_emergency
from app.guardrails.input_validator import InputValidationError, run_input_gates
from app.guardrails.output_validator import run_output_gates
from app.models.diagnosis import DISCLAIMER_TEXT, DiagnosisResponse
from app.models.patient import PatientIntake

logger = structlog.get_logger()


def _sse(event_type: str, **fields: object) -> str:
    """Serialize a payload as an SSE data frame."""
    payload = {"type": event_type, **fields}
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def run_diagnosis_pipeline_stream(
    intake: PatientIntake,
    neo4j_driver: AsyncDriver,
    qdrant_client: AsyncQdrantClient,
    request_id: str = "",
) -> AsyncIterator[str]:
    """Run the pipeline and yield SSE frames for each stage.

    This intentionally re-implements the orchestration instead of wrapping
    the non-streaming version so each stage has a clear start/end marker.
    """
    logger.info("pipeline_stream.start", request_id=request_id)

    # ---- Stage 1: Emergency check ----
    yield _sse("stage_start", stage="emergency_check")
    started = time.monotonic()
    try:
        emergency = check_emergency(intake)
    except Exception as exc:  # noqa: BLE001 — emergency must never crash the stream
        logger.exception("pipeline_stream.emergency_failed")
        yield _sse("error", message=f"emergency_check failed: {exc}")
        return
    elapsed = int((time.monotonic() - started) * 1000)
    yield _sse(
        "stage_end",
        stage="emergency_check",
        elapsed_ms=elapsed,
        data="triggered" if emergency.triggered else "clean",
    )

    if emergency.triggered:
        yield _sse("emergency", data=emergency.model_dump())
        response = DiagnosisResponse(
            diagnoses=[],
            emergency=emergency,
            disclaimer=DISCLAIMER_TEXT,
            request_id=request_id,
        )
        yield _sse("diagnosis_ready", data=response.model_dump())
        yield _sse("done")
        return

    # ---- Stage 2: Input validation ----
    yield _sse("stage_start", stage="input_gates")
    started = time.monotonic()
    try:
        run_input_gates(intake)
    except InputValidationError as exc:
        yield _sse("error", message=f"input_gates failed: {exc.detail}")
        return
    elapsed = int((time.monotonic() - started) * 1000)
    yield _sse("stage_end", stage="input_gates", elapsed_ms=elapsed, data="passed")

    # ---- Stage 3: Vector search ----
    yield _sse("stage_start", stage="vector_search")
    started = time.monotonic()
    try:
        seed_ids, scored_points = await get_seed_nodes(intake, qdrant_client)
    except NoSeedNodesError as exc:
        yield _sse("error", message=str(exc))
        return
    elapsed = int((time.monotonic() - started) * 1000)
    yield _sse(
        "stage_end",
        stage="vector_search",
        elapsed_ms=elapsed,
        data=f"{len(seed_ids)} matches, top score {scored_points[0].score:.3f}"
        if scored_points
        else "no matches",
    )

    # ---- Stage 4: Graph traversal ----
    yield _sse("stage_start", stage="graph_traversal")
    started = time.monotonic()
    try:
        nodes, relationships = await traverse_graph(seed_ids, neo4j_driver)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline_stream.traversal_failed")
        yield _sse("error", message=f"graph_traversal failed: {exc}")
        return
    elapsed = int((time.monotonic() - started) * 1000)
    low_context = len(nodes) < 3
    yield _sse(
        "stage_end",
        stage="graph_traversal",
        elapsed_ms=elapsed,
        data=f"{len(nodes)} nodes, {len(relationships)} edges",
    )

    # ---- Stage 5: Context assembly ----
    yield _sse("stage_start", stage="context_assembly")
    started = time.monotonic()
    messages, prompt_version = build_messages(intake, nodes, relationships)
    elapsed = int((time.monotonic() - started) * 1000)
    yield _sse(
        "stage_end",
        stage="context_assembly",
        elapsed_ms=elapsed,
        data=f"prompt v{prompt_version}",
    )

    # ---- Stage 6: LLM reasoning ----
    yield _sse("stage_start", stage="llm_call")
    started = time.monotonic()
    try:
        raw_output, model_used = await call_llm(messages)
    except LLMError as exc:
        yield _sse("error", message=str(exc))
        return
    except LLMSchemaError as exc:
        yield _sse("error", message=str(exc))
        return
    elapsed = int((time.monotonic() - started) * 1000)
    primary = get_settings().primary_llm
    primary_bare = primary.split("/", 1)[-1] if "/" in primary else primary
    model_bare = model_used.split("/", 1)[-1] if "/" in model_used else model_used
    llm_fallback = model_bare != primary_bare
    yield _sse(
        "stage_end",
        stage="llm_call",
        elapsed_ms=elapsed,
        data=f"{model_used}" + (" (fallback)" if llm_fallback else ""),
    )

    # ---- Stage 7: Output validation ----
    yield _sse("stage_start", stage="output_gates")
    started = time.monotonic()
    try:
        response = await run_output_gates(
            raw_output=raw_output,
            neo4j_driver=neo4j_driver,
            request_id=request_id,
            model_used=model_used,
            prompt_version=prompt_version,
            graph_nodes=nodes,
            graph_edges=relationships,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline_stream.output_gates_failed")
        yield _sse("error", message=f"output_gates failed: {exc}")
        return
    response.low_context = low_context
    response.llm_fallback = llm_fallback
    elapsed = int((time.monotonic() - started) * 1000)
    yield _sse(
        "stage_end",
        stage="output_gates",
        elapsed_ms=elapsed,
        data=f"{len(response.diagnoses)} diagnoses",
    )

    # ---- Final payload ----
    yield _sse("diagnosis_ready", data=response.model_dump())
    yield _sse("done")
    logger.info(
        "pipeline_stream.complete",
        request_id=request_id,
        diagnoses=len(response.diagnoses),
    )
