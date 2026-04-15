"""Output Guardrail Gates 6.1–6.5.

All gates run (except 6.1 which is a hard stop on schema failure).

The hallucination gate (6.2) used to keep its own 5-minute TTL cache
of Neo4j disease names inside this module. That cache was extracted
into `app.services.disease_index.DiseaseIndex` in the Phase 2
retrieval rewrite so the retrieval layer and this gate share one
consistent snapshot. Both consume it via `get_disease_index()`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from app.models.diagnosis import DISCLAIMER_TEXT, DifferentialDiagnosis, DiagnosisResponse
from app.observability.metrics import GATE_TRIGGERS
from app.services.disease_index import get_disease_index

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = structlog.get_logger()

# Gate 6.3 — Treatment advice keywords
# Note: deliberately NOT matching bare "\d+ mg" / "\d+ ml" because those
# patterns false-positive on lab values like "287 mg/dL" or "1.1 mg/dL".
# Stick to clearly imperative language about prescribing, administering,
# or treating a patient.
TREATMENT_KEYWORDS = re.compile(
    r"\b("
    r"prescribe(?:s|d)?|"
    r"recommended\s+dose|recommended\s+dosage|"
    r"treat\s+with|treatment\s+with|start\s+(?:on|with)|"
    r"give\s+the\s+patient|give\s+\d+\s*mg|"
    r"medication\s+regimen|drug\s+regimen|"
    r"take\s+\d+\s*(?:mg|ml|tablet|pill|capsule)|"
    r"inject(?:ed|ion)?\s+with|infuse\s+with|"
    r"recommend(?:ed)?\s+treatment|therapy\s+with|"
    r"should\s+(?:take|receive|be\s+given|be\s+prescribed)"
    r")\b",
    re.IGNORECASE,
)


def gate_schema_validation(raw_output: dict) -> DifferentialDiagnosis:
    """Gate 6.1 — Parse and validate LLM output against schema. Hard stop on failure."""
    try:
        result = DifferentialDiagnosis.model_validate(raw_output)
        GATE_TRIGGERS.labels(gate_name="output_schema", result="passed").inc()
        return result
    except Exception as exc:
        GATE_TRIGGERS.labels(gate_name="output_schema", result="failed").inc()
        logger.error("output_schema_validation_failed", error=str(exc))
        raise


async def gate_hallucination_check(
    diagnosis: DifferentialDiagnosis,
    neo4j_driver: AsyncDriver,
) -> DifferentialDiagnosis:
    """Gate 6.2 — Verify every disease_name exists in Neo4j (fuzzy).

    Strategy:
      1. Tokenize each LLM disease name (skip stopwords, single chars).
      2. Pull all PrimeKG disease records from the shared DiseaseIndex
         singleton (which both this gate and the retrieval layer consume —
         no duplicate caches).
      3. For each LLM diagnosis, compute Jaccard similarity against
         every record. Mark verified if best similarity >= 0.4.

    This handles word reordering ("Diabetes Mellitus Type 2" vs
    "type 2 diabetes mellitus"), abbreviations, and minor variations
    without dragging in fuzzy-string libraries.

    Unverified diseases get verified_in_graph=False + orange badge in UI.
    They are NOT removed — the clinician sees them with a clear marker.
    """
    # Tokenize all LLM diagnoses up front
    llm_tokens: dict[str, frozenset[str]] = {}
    all_query_tokens: set[str] = set()
    for item in diagnosis.diagnoses:
        toks = frozenset(_meaningful_tokens(item.disease_name))
        llm_tokens[item.disease_name] = toks
        all_query_tokens.update(toks)

    # If no meaningful tokens at all, mark everything unverified
    if not all_query_tokens:
        for item in diagnosis.diagnoses:
            item.verified_in_graph = False
        return diagnosis

    # Use the shared DiseaseIndex — same snapshot that the retrieval layer
    # uses, so a disease in the hallucination gate's view is always also
    # in the retrieval layer's view.
    try:
        records = await get_disease_index().all(neo4j_driver)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hallucination_cache_load_failed", error=str(exc))
        # On query failure, default to "verified" to avoid flooding the UI
        # with false negatives. The disclaimer still applies.
        return diagnosis

    logger.debug(
        "hallucination_candidates",
        count=len(records),
        tokens=len(all_query_tokens),
    )

    # Match each LLM name against the index
    hallucination_count = 0
    for item in diagnosis.diagnoses:
        toks = llm_tokens[item.disease_name]
        if not toks:
            item.verified_in_graph = False
            hallucination_count += 1
            continue

        best = 0.0
        for rec in records:
            inter = len(toks & rec.tokens)
            if inter == 0:
                continue
            union = len(toks | rec.tokens)
            jaccard = inter / union
            if jaccard > best:
                best = jaccard
                if best >= 0.99:
                    break  # near-perfect match, stop

        # Threshold tuned for clinical names — 0.4 catches most reasonable
        # variants while still flagging genuinely made-up names.
        if best < 0.4:
            item.verified_in_graph = False
            hallucination_count += 1
            logger.debug(
                "hallucination_unverified",
                name=item.disease_name,
                best_jaccard=round(best, 3),
            )
        else:
            item.verified_in_graph = True

    if hallucination_count:
        GATE_TRIGGERS.labels(gate_name="hallucination_check", result="found").inc()
        logger.warning("hallucinations_found", count=hallucination_count)
    else:
        GATE_TRIGGERS.labels(gate_name="hallucination_check", result="clean").inc()

    return diagnosis


# Tokenizer + stopwords kept in sync with app/services/disease_index.py.
# If the two ever drift the hallucination check would see different token
# sets than the retrieval layer, which is how silent mismatches happen.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "in", "on", "with", "to", "for",
    "by", "at", "from", "as", "is", "be", "type", "syndrome", "disease",
    "disorder", "condition",
})


def _meaningful_tokens(name: str) -> list[str]:
    """Strip stopwords + tokenize for fuzzy disease matching."""
    raw = re.findall(r"[a-zA-Z0-9]+", name.lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


async def preload_disease_cache(neo4j_driver: AsyncDriver) -> None:
    """Eagerly populate the shared DiseaseIndex at app startup.

    Kept as a top-level name for backwards compatibility with app/main.py
    which imports it by this name.
    """
    await get_disease_index().preload(neo4j_driver)


def gate_treatment_filter(diagnosis: DifferentialDiagnosis) -> tuple[DifferentialDiagnosis, bool]:
    """Gate 6.3 — Strip treatment advice from all text fields.

    Returns (modified diagnosis, whether any stripping occurred).
    """
    stripped = False

    # Check and clean reasoning summary
    if TREATMENT_KEYWORDS.search(diagnosis.reasoning_summary):
        sentences = diagnosis.reasoning_summary.split(". ")
        clean_sentences = [
            s for s in sentences
            if not TREATMENT_KEYWORDS.search(s)
        ]
        diagnosis.reasoning_summary = ". ".join(clean_sentences)
        stripped = True

    # Check and clean evidence strings
    for item in diagnosis.diagnoses:
        clean_evidence: list[str] = []
        for evidence in item.supporting_evidence:
            if TREATMENT_KEYWORDS.search(evidence):
                stripped = True
                # Keep the evidence but remove the treatment portion
                clean = TREATMENT_KEYWORDS.sub("[treatment advice removed]", evidence)
                clean_evidence.append(clean)
            else:
                clean_evidence.append(evidence)
        item.supporting_evidence = clean_evidence

    if stripped:
        GATE_TRIGGERS.labels(gate_name="treatment_filter", result="stripped").inc()
        logger.info("treatment_advice_stripped")
    else:
        GATE_TRIGGERS.labels(gate_name="treatment_filter", result="clean").inc()

    return diagnosis, stripped


def gate_confidence_threshold(
    diagnosis: DifferentialDiagnosis,
    threshold: float = 0.25,
) -> tuple[DifferentialDiagnosis, bool]:
    """Gate 6.4 — Flag when all diagnoses are below confidence threshold."""
    all_low = all(d.confidence < threshold for d in diagnosis.diagnoses)

    if all_low:
        GATE_TRIGGERS.labels(gate_name="confidence_threshold", result="low").inc()
        logger.info("all_diagnoses_low_confidence", threshold=threshold)
    else:
        GATE_TRIGGERS.labels(gate_name="confidence_threshold", result="normal").inc()

    return diagnosis, all_low


async def run_output_gates(
    raw_output: dict,
    neo4j_driver: AsyncDriver,
    request_id: str = "",
    model_used: str = "",
    prompt_version: str = "",
    graph_nodes: list[dict] | None = None,
    graph_edges: list[dict] | None = None,
) -> DiagnosisResponse:
    """Run all output guardrail gates and assemble the final response."""

    # Gate 6.1 — Schema validation (hard stop)
    diagnosis = gate_schema_validation(raw_output)

    # Gate 6.2 — Hallucination check
    diagnosis = await gate_hallucination_check(diagnosis, neo4j_driver)

    # Gate 6.3 — Treatment advice filter
    diagnosis, treatment_stripped = gate_treatment_filter(diagnosis)

    # Gate 6.4 — Confidence threshold
    diagnosis, low_confidence = gate_confidence_threshold(diagnosis)

    # Gate 6.5 — Mandatory disclaimer (always present)
    return DiagnosisResponse(
        diagnoses=diagnosis.diagnoses,
        reasoning_summary=diagnosis.reasoning_summary,
        low_confidence=low_confidence,
        treatment_advice_stripped=treatment_stripped,
        disclaimer=DISCLAIMER_TEXT,
        request_id=request_id,
        model_used=model_used,
        prompt_version=prompt_version,
        graph_nodes=graph_nodes or [],
        graph_edges=graph_edges or [],
    )
