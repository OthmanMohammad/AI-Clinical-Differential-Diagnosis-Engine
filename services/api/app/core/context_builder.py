"""Layer 4 — Context Assembly.

Serializes the graph subgraph into structured text for the LLM prompt,
loads versioned prompt templates from YAML, and enforces token budget.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
import yaml

from app.models.diagnosis import DifferentialDiagnosis
from app.models.patient import PatientIntake

logger = structlog.get_logger()

# Prompt template cache
_prompt_cache: dict[str, dict] = {}

# Default prompt template path
PROMPTS_DIR = Path("prompts")


def serialize_subgraph(nodes: list[dict], relationships: list[dict]) -> str:
    """Convert graph nodes and relationships into structured text for LLM context.

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


def load_prompt_template(version: str = "v2") -> dict:
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


def build_messages(
    intake: PatientIntake,
    nodes: list[dict],
    relationships: list[dict],
    prompt_version: str = "v2",
) -> tuple[list[dict], str]:
    """Assemble the full message list for the LLM call.

    Returns:
        Tuple of (messages, prompt_version).
    """
    template = load_prompt_template(prompt_version)

    # Serialize patient data
    patient_json = json.dumps(
        intake.model_dump(exclude_none=True),
        indent=2,
    )

    # Serialize subgraph
    subgraph_context = serialize_subgraph(nodes, relationships)

    # Get output schema
    output_schema = get_output_schema()

    # Build system message
    system_content = template["system"]

    # Build user message from template
    user_content = template["user"].format(
        patient_json=patient_json,
        subgraph_context=subgraph_context,
        output_schema=output_schema,
    )

    # Token budget check and pruning
    total_chars = len(system_content) + len(user_content)
    approx_tokens = total_chars / 4
    max_tokens = 8000

    if approx_tokens > max_tokens:
        logger.warning(
            "context_too_large_pruning",
            approx_tokens=int(approx_tokens),
            max_tokens=max_tokens,
            nodes=len(nodes),
            relationships=len(relationships),
        )
        # Prune: keep nodes closest to seed (first in list), drop from the end
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

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    version = template.get("version", prompt_version)
    return messages, str(version)
