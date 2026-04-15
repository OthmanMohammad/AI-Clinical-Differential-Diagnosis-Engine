"""Pipeline Orchestrator — ties all layers together.

Runs the full Graph RAG pipeline (Tier 2 retrieval rewrite):

  1. Input guardrails (gates 2.1–2.5)
  2. Vector search → phenotype seeds
  3. Retrieval — phenotype intersection + rule boosts + fallback
     seeding. Produces a ranked Candidate list with per-candidate
     matched edges (the explicit fix for "graph_path is empty on
     correct top diagnosis").
  4. Subgraph expansion — 1 hop out from each candidate disease
     for LLM context.
  5. Context assembly (v3 prompt) — per-candidate evidence blocks
     instead of a flat subgraph.
  6. LLM reasoning
  7. Output guardrails (gates 6.1–6.5)

The old flow (vector_search → traverse_graph → flat context) is
still available via graph_rag_stream.py for the streaming endpoint,
but the default pipeline uses the new retrieval layer.
"""

from __future__ import annotations

import structlog
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient

from app.core.context_builder import build_messages_v3
from app.core.graph_traversal import expand_candidates
from app.core.llm_client import call_llm
from app.core.retrieval import RetrievalError, retrieve_candidates
from app.core.vector_search import NoSeedNodesError, get_phenotype_seeds
from app.guardrails.emergency import check_emergency
from app.guardrails.input_validator import run_input_gates
from app.guardrails.output_validator import run_output_gates
from app.models.diagnosis import DISCLAIMER_TEXT, DiagnosisResponse
from app.models.patient import PatientIntake
from app.observability.langfuse_client import create_span, create_trace, end_span

logger = structlog.get_logger()


async def run_diagnosis_pipeline(
    intake: PatientIntake,
    neo4j_driver: AsyncDriver,
    qdrant_client: AsyncQdrantClient,
    request_id: str = "",
) -> DiagnosisResponse:
    """Execute the full diagnosis pipeline (Tier 2).

    Args:
        intake: Validated patient intake data.
        neo4j_driver: Neo4j async driver.
        qdrant_client: Qdrant async client.
        request_id: Unique request ID for tracing.

    Returns:
        DiagnosisResponse with diagnoses, graph data, and metadata.
    """
    # Create Langfuse trace
    trace = create_trace(
        name="diagnosis_pipeline_v3",
        request_id=request_id,
        metadata={"symptoms": intake.symptoms[:5]},
    )

    # --- Gate 2.1: Emergency Detection ---------------------------------
    span = create_span(trace, "emergency_check")
    emergency = check_emergency(intake)
    end_span(
        span,
        output_data={"triggered": emergency.triggered, "pattern": emergency.pattern_name},
    )

    if emergency.triggered:
        logger.warning("emergency_short_circuit", pattern=emergency.pattern_name)
        return DiagnosisResponse(
            diagnoses=[],
            emergency=emergency,
            disclaimer=DISCLAIMER_TEXT,
            request_id=request_id,
        )

    # --- Gates 2.3–2.5: Input Validation -------------------------------
    span = create_span(trace, "input_gates")
    run_input_gates(intake)
    end_span(span, output_data={"status": "passed"})

    # --- Layer 3.1: Vector search → phenotype seeds --------------------
    span = create_span(trace, "phenotype_seeds")
    try:
        phenotype_ids, scored_points = await get_phenotype_seeds(intake, qdrant_client)
    except NoSeedNodesError as exc:
        end_span(span, output_data={"error": str(exc)}, level="WARNING")
        return DiagnosisResponse(
            diagnoses=[],
            reasoning_summary=str(exc),
            low_context=True,
            disclaimer=DISCLAIMER_TEXT,
            request_id=request_id,
        )
    end_span(span, output_data={"phenotype_count": len(phenotype_ids)})

    # --- Layer 3.2: Retrieval — phenotype intersection + rule fusion ---
    span = create_span(trace, "retrieval")
    try:
        candidates = await retrieve_candidates(
            intake=intake,
            phenotype_ids=phenotype_ids,
            neo4j_driver=neo4j_driver,
        )
    except RetrievalError as exc:
        end_span(span, output_data={"error": str(exc)}, level="WARNING")
        return DiagnosisResponse(
            diagnoses=[],
            reasoning_summary=str(exc),
            low_context=True,
            disclaimer=DISCLAIMER_TEXT,
            request_id=request_id,
        )
    end_span(
        span,
        output_data={
            "total_candidates": len(candidates),
            "from_graph": sum(1 for c in candidates if c.source == "graph"),
            "from_rules": sum(1 for c in candidates if c.source == "clinical_rule"),
            "top_name": candidates[0].disease_name if candidates else "",
            "top_score": candidates[0].score if candidates else 0.0,
        },
    )

    # --- Layer 3.3: Subgraph expansion for LLM context ------------------
    # Pull 1 hop out from each candidate to give the LLM a small set
    # of neighbors to reason about (related symptoms, associated
    # genes/drugs). This is purely enrichment — retrieval has already
    # settled the ranked candidate list.
    span = create_span(trace, "subgraph_expand")
    nodes, relationships = await expand_candidates(
        candidates=candidates,
        neo4j_driver=neo4j_driver,
        per_candidate=12,
    )
    low_context = len(candidates) < 2
    end_span(
        span,
        output_data={"nodes": len(nodes), "relationships": len(relationships)},
    )

    # --- Layer 4: Context Assembly (v3 prompt) --------------------------
    span = create_span(trace, "context_assembly")
    messages, prompt_version = build_messages_v3(intake, candidates)
    end_span(span, output_data={"prompt_version": prompt_version})

    # --- Layer 5: LLM Reasoning ----------------------------------------
    span = create_span(trace, "llm_call")
    raw_output, model_used = await call_llm(messages)
    end_span(span, output_data={"model": model_used})

    # Detect fallback — LiteLLM returns "llama-3.3-70b-versatile" without the
    # "groq/" provider prefix, so strip the prefix from the configured primary
    # before comparing.
    from app.config import get_settings
    primary = get_settings().primary_llm
    primary_bare = primary.split("/", 1)[-1] if "/" in primary else primary
    model_bare = model_used.split("/", 1)[-1] if "/" in model_used else model_used
    llm_fallback = model_bare != primary_bare

    # --- Layer 6: Output Guardrails ------------------------------------
    span = create_span(trace, "output_gates")
    response = await run_output_gates(
        raw_output=raw_output,
        neo4j_driver=neo4j_driver,
        request_id=request_id,
        model_used=model_used,
        prompt_version=prompt_version,
        graph_nodes=nodes,
        graph_edges=relationships,
    )

    response.low_context = low_context
    response.llm_fallback = llm_fallback
    end_span(span, output_data={"diagnoses_count": len(response.diagnoses)})

    logger.info(
        "pipeline_complete",
        diagnoses=len(response.diagnoses),
        model=model_used,
        low_context=low_context,
        llm_fallback=llm_fallback,
        candidates=len(candidates),
        top_candidate=candidates[0].disease_name if candidates else "",
    )

    return response
