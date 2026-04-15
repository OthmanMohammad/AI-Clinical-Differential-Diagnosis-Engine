"""Layer 4 — Context Assembly.

Serializes the retrieval pipeline output into a structured text block
the LLM can reason about. Supports two prompt versions side-by-side:

    v2 — the legacy flat-subgraph format. Used by the old
         vector_search → graph_traversal path. Kept for backwards
         compatibility until graph_rag_stream.py migrates.

    v3 — the Tier 2 per-candidate format. Each candidate gets its own
         evidence block with explicit matched edges and rule boosts.
         This is what graph_rag.py calls after retrieve_candidates()
         runs. Fixes the "graph_path is empty on correct top diagnosis"
         bug from v2.

Use `build_messages_v3(...)` for the Tier 2 pipeline and
`build_messages(...)` for the legacy pipeline. Both return
(messages, prompt_version) so the caller doesn't need to know
which one is default.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
import yaml

from app.config import PROMPTS_DIR
from app.models.diagnosis import DifferentialDiagnosis
from app.models.patient import PatientIntake

if TYPE_CHECKING:
    from app.core.retrieval import Candidate

logger = structlog.get_logger()

# Prompt template cache
_prompt_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Legacy v2 serialization — flat subgraph
# ---------------------------------------------------------------------------


def serialize_subgraph(nodes: list[dict], relationships: list[dict]) -> str:
    """Convert graph nodes and relationships into structured text for LLM
    context (v2 format).

    Compact formatted text — LLMs reason better with this than nested JSON.
    """
    lines = ["KNOWLEDGE GRAPH CONTEXT:", "", "Entities:"]

    for node in nodes:
        node_type = node.get("type", "Unknown")
        node_name = node.get("name", "unnamed")
        node_id = node.get("id", "?")
        lines.append(f"  [{node_type}] {node_name} (id:{node_id})")

    lines.extend(["", "Relationships:"])

    # Build a name lookup for readable edge display
    id_to_name: dict[str, str] = {
        node["id"]: node.get("name", "unnamed") for node in nodes
    }

    for rel in relationships:
        source_name = id_to_name.get(rel.get("source", ""), "?")
        target_name = id_to_name.get(rel.get("target", ""), "?")
        rel_type = rel.get("type", "RELATED_TO")
        lines.append(f"  {source_name} --[{rel_type}]--> {target_name}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# New v3 serialization — per-candidate evidence blocks
# ---------------------------------------------------------------------------


def serialize_candidates(candidates: "list[Candidate]") -> str:
    """Convert a ranked Candidate list into structured text for v3 prompts.

    Each candidate gets its own block with:
      - rank and retrieval score
      - source tag (graph vs clinical_rule)
      - matched_edges (for graph-sourced)
      - rule_boosts (for any rule that fired on it)

    Example output:

        CANDIDATE DIAGNOSES (ranked by retrieval score):

        #1  Type 2 Diabetes Mellitus  [score 25.00, source: graph]
              matched phenotypes (4):
                - Polyuria         via disease_phenotype_positive
                - Polydipsia       via disease_phenotype_positive
                - Fatigue          via disease_phenotype_positive
                - Blurred vision   via disease_phenotype_positive
              clinical rules that fired:
                - glucose ≥200 meets ADA diagnostic threshold  (x2.5)
                - HbA1c ≥6.5% meets ADA diagnostic threshold   (x2.5)

        #2  Wolfram Syndrome  [score 5.00, source: graph]
              matched phenotypes (5):
                - Polyuria         via disease_phenotype_positive
                ...

    The format is designed to be pattern-matchable by the LLM but still
    compact — each candidate takes ~8-15 lines, so 20 candidates fit
    in well under 2k tokens.
    """
    if not candidates:
        return "CANDIDATE DIAGNOSES:\n\n  (none — pipeline returned no candidates)"

    lines = ["CANDIDATE DIAGNOSES (ranked by retrieval score):", ""]

    for rank, cand in enumerate(candidates, start=1):
        header = (
            f"#{rank}  {cand.disease_name}  "
            f"[score {cand.score:.2f}, source: {cand.source}, "
            f"phenotype_overlap: {cand.overlap_count}]"
        )
        lines.append(header)

        # Matched edges (graph evidence)
        if cand.matched_edges:
            lines.append(f"      matched phenotypes ({len(cand.matched_edges)}):")
            for edge in cand.matched_edges:
                lines.append(
                    f"        - {edge.phenotype_name:<35s} "
                    f"via {edge.rel_type}"
                )
        else:
            lines.append("      matched phenotypes: (none — rule-only candidate)")

        # Rule boosts
        if cand.rule_boosts:
            lines.append("      clinical rules that fired:")
            for boost in cand.rule_boosts:
                rationale = boost.rationale or boost.rule_label
                lines.append(
                    f"        - {rationale}  (x{boost.multiplier:.1f})"
                )

        lines.append("")  # blank line between candidates

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt template loading
# ---------------------------------------------------------------------------


def load_prompt_template(version: str = "v3") -> dict:
    """Load a versioned prompt template from YAML."""
    if version in _prompt_cache:
        return _prompt_cache[version]

    template_path = PROMPTS_DIR / f"differential_{version}.yaml"
    if not template_path.exists():
        logger.error("prompt_template_not_found", path=str(template_path))
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    with open(template_path) as f:
        template = yaml.safe_load(f)

    _prompt_cache[version] = template
    logger.info("prompt_template_loaded", version=version)
    return template


def get_output_schema() -> str:
    """Return the JSON schema string for the expected LLM output."""
    return json.dumps(
        DifferentialDiagnosis.model_json_schema(),
        indent=2,
    )


# ---------------------------------------------------------------------------
# v2 message builder (legacy path)
# ---------------------------------------------------------------------------


def build_messages(
    intake: PatientIntake,
    nodes: list[dict],
    relationships: list[dict],
    prompt_version: str = "v2",
) -> tuple[list[dict], str]:
    """Assemble the full message list for the legacy v2 LLM call.

    Returns:
        Tuple of (messages, prompt_version).
    """
    template = load_prompt_template(prompt_version)

    patient_json = json.dumps(intake.model_dump(exclude_none=True), indent=2)
    subgraph_context = serialize_subgraph(nodes, relationships)
    output_schema = get_output_schema()

    system_content = template["system"]
    user_content = template["user"].format(
        patient_json=patient_json,
        subgraph_context=subgraph_context,
        output_schema=output_schema,
    )

    # Token budget pruning
    system_content, user_content = _maybe_prune_v2(
        template=template,
        system_content=system_content,
        user_content=user_content,
        patient_json=patient_json,
        nodes=nodes,
        relationships=relationships,
        output_schema=output_schema,
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    version = template.get("version", prompt_version)
    return messages, str(version)


def _maybe_prune_v2(
    template: dict,
    system_content: str,
    user_content: str,
    patient_json: str,
    nodes: list[dict],
    relationships: list[dict],
    output_schema: str,
) -> tuple[str, str]:
    """Prune nodes/relationships if the combined prompt exceeds budget."""
    total_chars = len(system_content) + len(user_content)
    approx_tokens = total_chars / 4
    max_tokens = 8000

    if approx_tokens <= max_tokens:
        return system_content, user_content

    logger.warning(
        "context_too_large_pruning",
        approx_tokens=int(approx_tokens),
        max_tokens=max_tokens,
        nodes=len(nodes),
        relationships=len(relationships),
    )
    prune_ratio = max_tokens / approx_tokens
    pruned_node_count = max(3, int(len(nodes) * prune_ratio))
    pruned_rel_count = max(5, int(len(relationships) * prune_ratio))

    pruned_nodes = nodes[:pruned_node_count]
    pruned_rels = relationships[:pruned_rel_count]

    subgraph_context = serialize_subgraph(pruned_nodes, pruned_rels)
    user_content = template["user"].format(
        patient_json=patient_json,
        subgraph_context=subgraph_context,
        output_schema=output_schema,
    )

    logger.info(
        "context_pruned",
        original_nodes=len(nodes),
        pruned_nodes=pruned_node_count,
    )
    return system_content, user_content


# ---------------------------------------------------------------------------
# v3 message builder (new path)
# ---------------------------------------------------------------------------


def build_messages_v3(
    intake: PatientIntake,
    candidates: "list[Candidate]",
    prompt_version: str = "v3",
    max_candidates: int = 12,
) -> tuple[list[dict], str]:
    """Assemble the message list for the Tier 2 v3 prompt.

    Args:
        intake: Validated patient intake.
        candidates: Ranked list from retrieve_candidates(). Truncated
            to `max_candidates` before serialization — the LLM doesn't
            need all 20 and the token count grows linearly.
        prompt_version: Prompt template version (default "v3").
        max_candidates: Maximum number of candidates to serialize.

    Returns:
        Tuple of (messages, prompt_version).
    """
    template = load_prompt_template(prompt_version)

    patient_json = json.dumps(intake.model_dump(exclude_none=True), indent=2)
    trimmed = candidates[:max_candidates]
    candidates_context = serialize_candidates(trimmed)
    output_schema = get_output_schema()

    system_content = template["system"]
    user_content = template["user"].format(
        patient_json=patient_json,
        candidates_context=candidates_context,
        output_schema=output_schema,
    )

    # If we're somehow still over budget, drop candidates from the tail.
    # Per-candidate blocks are ~200 chars, so this rarely fires.
    total_chars = len(system_content) + len(user_content)
    approx_tokens = total_chars / 4
    max_tokens = 8000

    if approx_tokens > max_tokens and len(trimmed) > 3:
        logger.warning(
            "v3_context_too_large_pruning",
            approx_tokens=int(approx_tokens),
            max_tokens=max_tokens,
            candidates=len(trimmed),
        )
        keep = max(3, int(len(trimmed) * max_tokens / approx_tokens))
        trimmed = trimmed[:keep]
        candidates_context = serialize_candidates(trimmed)
        user_content = template["user"].format(
            patient_json=patient_json,
            candidates_context=candidates_context,
            output_schema=output_schema,
        )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    version = template.get("version", prompt_version)
    return messages, str(version)
