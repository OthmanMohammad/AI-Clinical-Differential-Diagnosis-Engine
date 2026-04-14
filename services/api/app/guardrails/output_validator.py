"""Output Guardrail Gates 6.1–6.5.

All gates run (except 6.1 which is a hard stop on schema failure).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from app.models.diagnosis import DISCLAIMER_TEXT, DifferentialDiagnosis, DiagnosisResponse
from app.observability.metrics import GATE_TRIGGERS

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
    """Gate 6.2 — Verify every disease_name exists in Neo4j.

    Uses a fuzzy match strategy: a diagnosis is considered "verified"
    if any of the following hold against PrimeKG disease names:
      1. Exact case-insensitive match
      2. Substring match in either direction (handles word reordering
         and minor variations like "type 2 diabetes mellitus" vs
         "diabetes mellitus type 2")
      3. All meaningful tokens of the LLM name are present in some graph
         disease name (handles "Type 2 Diabetes Mellitus" vs
         "Diabetes Mellitus, Type 2")

    Unverified diseases get verified_in_graph=False + orange badge in UI.
    They are NOT removed — the clinician sees them with a clear marker.
    """
    disease_names = [d.disease_name for d in diagnosis.diagnoses]

    async with neo4j_driver.session() as session:
        # First try exact match for fast path
        result = await session.run(
            """
            UNWIND $names AS name
            OPTIONAL MATCH (d:Disease)
            WHERE toLower(d.name) = toLower(name)
               OR toLower(d.name) CONTAINS toLower(name)
               OR toLower(name) CONTAINS toLower(d.name)
            WITH name, count(d) AS hit_count
            RETURN name, hit_count > 0 AS found
            """,
            names=disease_names,
        )
        records = await result.data()

    found_set: set[str] = set()
    for record in records:
        if record["found"]:
            found_set.add(record["name"].lower())

    # Token-based fallback for names that didn't match by substring.
    # Example: "Diabetes Mellitus Type 2" should match "type 2 diabetes mellitus".
    unmatched = [
        item.disease_name
        for item in diagnosis.diagnoses
        if item.disease_name.lower() not in found_set
    ]
    if unmatched:
        async with neo4j_driver.session() as session:
            for name in unmatched:
                tokens = _meaningful_tokens(name)
                if not tokens:
                    continue
                result = await session.run(
                    """
                    MATCH (d:Disease)
                    WHERE ALL(token IN $tokens
                              WHERE toLower(d.name) CONTAINS token)
                    RETURN count(d) > 0 AS found
                    LIMIT 1
                    """,
                    tokens=[t.lower() for t in tokens],
                )
                record = await result.single()
                if record and record["found"]:
                    found_set.add(name.lower())

    hallucination_count = 0
    for item in diagnosis.diagnoses:
        if item.disease_name.lower() not in found_set:
            item.verified_in_graph = False
            hallucination_count += 1

    if hallucination_count:
        GATE_TRIGGERS.labels(gate_name="hallucination_check", result="found").inc()
        logger.warning("hallucinations_found", count=hallucination_count)
    else:
        GATE_TRIGGERS.labels(gate_name="hallucination_check", result="clean").inc()

    return diagnosis


# Words to ignore when token-matching disease names — they're too common
# to be meaningful for matching (every disease has "syndrome" or "disease").
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "in", "on", "with", "to", "for",
    "by", "at", "from", "as", "is", "be", "type", "syndrome", "disease",
    "disorder",
})


def _meaningful_tokens(name: str) -> list[str]:
    """Strip stopwords + tokenize for fuzzy disease matching."""
    raw = re.findall(r"[a-zA-Z0-9]+", name.lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


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
