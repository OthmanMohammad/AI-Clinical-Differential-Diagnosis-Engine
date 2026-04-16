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

from app.models.diagnosis import DISCLAIMER_TEXT, DiagnosisResponse, DifferentialDiagnosis
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
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "in",
        "on",
        "with",
        "to",
        "for",
        "by",
        "at",
        "from",
        "as",
        "is",
        "be",
        "type",
        "syndrome",
        "disease",
        "disorder",
        "condition",
    }
)


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
        clean_sentences = [s for s in sentences if not TREATMENT_KEYWORDS.search(s)]
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


# ---------------------------------------------------------------------------
# Gate 6.5 — Evidence grounding check
# ---------------------------------------------------------------------------
#
# Why this exists
# ---------------
# The Tier 2 retrieval rewrite was supposed to ensure that every graph_path
# field in a diagnosis corresponds to an actual edge we retrieved for the
# LLM. In practice we found the LLM will happily populate graph_path with
# correct-looking edges it pulled from its training data even when the
# retrieval layer missed the target disease entirely. That's "citation
# theater" — the fields look like graph-grounded reasoning but the LLM
# hallucinated them. Measuring graph_path non-emptiness as a proxy for
# grounding was therefore misleading.
#
# This gate verifies each graph_path entry against the prompt context
# (graph_nodes + graph_edges passed through from the retrieval layer).
# An entry is "grounded" if there's an edge in the context from a node
# whose name matches the diagnosis to a node whose name matches the
# graph_path entry. Anything else is counted as hallucinated.
#
# The gate is diagnostic-only: we NEVER reject a diagnosis because its
# graph_path was hallucinated. We just count and log, so downstream
# observability can tell us the true grounding rate per request. The
# eval harness reads these fields to compute evidence_grounding_rate
# across cases.

_MATCH_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "in",
        "on",
        "with",
        "to",
        "for",
        "by",
        "at",
        "from",
        "as",
        "is",
        "be",
        "syndrome",
        "disease",
        "disorder",
        "condition",
        "mellitus",
    }
)


def _name_tokens(name: str) -> frozenset[str]:
    """Tokenize a disease/phenotype name into a set of meaningful tokens.
    Same logic as eval/metrics.py._tokenize_name — kept here because we
    can't import across the eval/services boundary.
    """
    if not name:
        return frozenset()
    raw = re.findall(r"[a-z0-9]+", name.lower())
    return frozenset(t for t in raw if t not in _MATCH_STOPWORDS and (t.isdigit() or len(t) > 1))


def _names_match(a: str, b: str) -> bool:
    """Token-set subset match (either direction). Handles word reorder
    and qualifier differences like "Acute Pancreatitis" <-> "Pancreatitis"
    without crossing type/number distinctions (Type 1 DM vs Type 2 DM).
    """
    a_toks = _name_tokens(a)
    b_toks = _name_tokens(b)
    if not a_toks or not b_toks:
        return False
    smaller, larger = (a_toks, b_toks) if len(a_toks) <= len(b_toks) else (b_toks, a_toks)
    return smaller.issubset(larger)


def gate_evidence_grounding(
    diagnosis: DifferentialDiagnosis,
    graph_nodes: list[dict],
    graph_edges: list[dict],
) -> tuple[DifferentialDiagnosis, int, int]:
    """Gate 6.5 — Verify each diagnosis.graph_path entry against the
    context actually passed to the LLM.

    Args:
        diagnosis: The LLM's parsed output.
        graph_nodes: Nodes that were in the prompt context.
        graph_edges: Edges that were in the prompt context.

    Returns:
        Tuple of (diagnosis mutated with per-item grounding counts,
                  total entries across all diagnoses,
                  grounded entries across all diagnoses).

    Side effects:
        * Populates DiagnosisItem.grounded_path_entries and
          .hallucinated_path_entries on each item.
        * Logs `evidence_grounding_complete` with the aggregate numbers.
        * Increments GATE_TRIGGERS with the pass/fail label.
    """
    if not diagnosis.diagnoses:
        return diagnosis, 0, 0
    # Note: we deliberately DON'T early-exit on empty graph_nodes or
    # graph_edges. If the LLM returned graph_path entries but the
    # prompt context had no edges, every entry is by definition
    # hallucinated and should be counted as such. Early-exit would
    # silently mark them as "untested" which is exactly the opposite
    # signal we want.
    graph_nodes = graph_nodes or []
    graph_edges = graph_edges or []

    # Index nodes by elementId for fast lookup.
    nodes_by_id: dict[str, dict] = {n.get("id"): n for n in graph_nodes if n.get("id")}

    # Build disease_id -> set of phenotype names it connects to (via edges).
    disease_id_to_phenotype_names: dict[str, set[str]] = {}
    for edge in graph_edges:
        src_id = edge.get("source")
        tgt_id = edge.get("target")
        if not src_id or not tgt_id:
            continue
        tgt_node = nodes_by_id.get(tgt_id)
        if not tgt_node:
            continue
        tgt_name = (tgt_node.get("name") or "").strip()
        if not tgt_name:
            continue
        disease_id_to_phenotype_names.setdefault(src_id, set()).add(tgt_name.lower())

    # Pair each disease NODE NAME in the graph with its phenotype names,
    # so we can match the LLM's `disease_name` (a string) back to the
    # context via token-set matching.
    disease_name_to_phenotype_names: list[tuple[str, set[str]]] = []
    for d_id, phen_names in disease_id_to_phenotype_names.items():
        d_node = nodes_by_id.get(d_id)
        if not d_node:
            continue
        d_name = (d_node.get("name") or "").strip()
        if not d_name:
            continue
        disease_name_to_phenotype_names.append((d_name, phen_names))

    total_entries = 0
    grounded_entries = 0

    for item in diagnosis.diagnoses:
        # Collect every phenotype name in the context that belongs to a
        # disease whose name token-set-matches the LLM's diagnosis.
        allowed_phenotypes: set[str] = set()
        for d_name, phen_names in disease_name_to_phenotype_names:
            if _names_match(item.disease_name, d_name):
                allowed_phenotypes |= phen_names

        item_grounded = 0
        for entry in item.graph_path:
            total_entries += 1
            entry_norm = (entry or "").strip().lower()
            if entry_norm and entry_norm in allowed_phenotypes:
                item_grounded += 1
                grounded_entries += 1

        item.grounded_path_entries = item_grounded
        item.hallucinated_path_entries = len(item.graph_path) - item_grounded

    if total_entries > 0:
        grounding_rate = grounded_entries / total_entries
        hallucinated = total_entries - grounded_entries
        logger.info(
            "evidence_grounding_complete",
            total=total_entries,
            grounded=grounded_entries,
            hallucinated=hallucinated,
            grounding_rate=round(grounding_rate, 3),
        )
        if hallucinated > 0:
            GATE_TRIGGERS.labels(gate_name="evidence_grounding", result="partial").inc()
            logger.warning(
                "evidence_grounding_hallucinations",
                count=hallucinated,
                total=total_entries,
            )
        else:
            GATE_TRIGGERS.labels(gate_name="evidence_grounding", result="clean").inc()
    else:
        GATE_TRIGGERS.labels(gate_name="evidence_grounding", result="empty").inc()

    return diagnosis, total_entries, grounded_entries


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

    # Gate 6.5 — Evidence grounding (diagnostic-only; never rejects)
    diagnosis, total_evidence, grounded_evidence = gate_evidence_grounding(
        diagnosis,
        graph_nodes or [],
        graph_edges or [],
    )

    # Mandatory disclaimer (always present) + assembly
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
        total_evidence_entries=total_evidence,
        grounded_evidence_entries=grounded_evidence,
    )
