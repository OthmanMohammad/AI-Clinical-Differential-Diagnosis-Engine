"""Unit tests for app/guardrails/output_validator.gate_evidence_grounding.

This is the Gate 6.5 validator that catches hallucinated graph_path
entries — the T2DM citation theater failure mode where the LLM
populates graph_path with edges that were never in the prompt context.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.guardrails.output_validator import (  # noqa: E402
    _name_tokens,
    _names_match,
    gate_evidence_grounding,
)
from app.models.diagnosis import DiagnosisItem, DifferentialDiagnosis  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _diag(
    name: str,
    graph_path: list[str] | None = None,
    confidence: float = 0.9,
    verified: bool = True,
) -> DiagnosisItem:
    return DiagnosisItem(
        disease_name=name,
        confidence=confidence,
        supporting_evidence=[f"dummy evidence for {name}"],
        graph_path=graph_path or [],
        verified_in_graph=verified,
    )


def _dx(*items: DiagnosisItem) -> DifferentialDiagnosis:
    return DifferentialDiagnosis(diagnoses=list(items), reasoning_summary="test")


def _node(eid: str, name: str, type_: str = "Disease") -> dict:
    return {"id": eid, "name": name, "type": type_}


def _edge(src: str, tgt: str, rel: str = "disease_phenotype_positive") -> dict:
    return {"source": src, "target": tgt, "type": rel}


# ---------------------------------------------------------------------------
# _name_tokens and _names_match
# ---------------------------------------------------------------------------


def test_name_tokens_drops_stopwords_and_keeps_numbers():
    tokens = _name_tokens("Type 2 Diabetes Mellitus")
    assert "2" in tokens
    assert "type" in tokens
    assert "diabetes" in tokens
    assert "mellitus" not in tokens  # stopword


def test_name_tokens_empty_input():
    assert _name_tokens("") == frozenset()
    assert _name_tokens("   ") == frozenset()


def test_names_match_word_reorder():
    assert _names_match("Type 2 Diabetes Mellitus", "Diabetes Mellitus Type 2")
    assert _names_match("Acute Pancreatitis", "Pancreatitis Acute")


def test_names_match_qualifier_subset():
    # "Pancreatitis" is a subset of "Acute Pancreatitis"
    assert _names_match("Pancreatitis", "Acute Pancreatitis")
    assert _names_match("Acute Pancreatitis", "Pancreatitis")


def test_names_match_type_distinction_preserved():
    assert not _names_match("Type 1 Diabetes", "Type 2 Diabetes")


def test_names_match_different_diseases():
    assert not _names_match("Asthma", "COPD")
    assert not _names_match("Pneumonia", "Migraine")


# ---------------------------------------------------------------------------
# gate_evidence_grounding — the main function
# ---------------------------------------------------------------------------


def test_fully_grounded_case():
    """Every graph_path entry corresponds to a real edge in context."""
    diagnosis = _dx(
        _diag(
            "Type 2 Diabetes Mellitus",
            graph_path=["Polyuria", "Polydipsia"],
        )
    )
    nodes = [
        _node("d1", "Type 2 Diabetes Mellitus", "Disease"),
        _node("p1", "Polyuria", "Phenotype"),
        _node("p2", "Polydipsia", "Phenotype"),
    ]
    edges = [
        _edge("d1", "p1"),
        _edge("d1", "p2"),
    ]
    result, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 2
    assert grounded == 2
    assert result.diagnoses[0].grounded_path_entries == 2
    assert result.diagnoses[0].hallucinated_path_entries == 0


def test_fully_hallucinated_case():
    """LLM returned T2DM with graph_path but T2DM isn't in context.
    This is the exact T2DM citation theater failure mode."""
    diagnosis = _dx(
        _diag(
            "Type 2 Diabetes Mellitus",
            graph_path=["Polyuria", "Polydipsia", "Blurred vision"],
        )
    )
    # Context only has Gitelman syndrome, not T2DM
    nodes = [
        _node("d1", "Gitelman syndrome", "Disease"),
        _node("p1", "Polyuria", "Phenotype"),
    ]
    edges = [
        _edge("d1", "p1"),
    ]
    result, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 3
    assert grounded == 0
    assert result.diagnoses[0].grounded_path_entries == 0
    assert result.diagnoses[0].hallucinated_path_entries == 3


def test_partially_grounded_case():
    """Some graph_path entries are real, others are hallucinated."""
    diagnosis = _dx(
        _diag(
            "Type 2 Diabetes Mellitus",
            graph_path=["Polyuria", "Polydipsia", "Hallucinated symptom"],
        )
    )
    nodes = [
        _node("d1", "Type 2 Diabetes Mellitus", "Disease"),
        _node("p1", "Polyuria", "Phenotype"),
        _node("p2", "Polydipsia", "Phenotype"),
    ]
    edges = [
        _edge("d1", "p1"),
        _edge("d1", "p2"),
    ]
    result, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 3
    assert grounded == 2
    assert result.diagnoses[0].grounded_path_entries == 2
    assert result.diagnoses[0].hallucinated_path_entries == 1


def test_word_reorder_still_matches():
    """The LLM's 'Diabetes Mellitus Type 2' should match context's
    'Type 2 Diabetes Mellitus' — token-set matching handles reorder."""
    diagnosis = _dx(
        _diag(
            "Diabetes Mellitus Type 2",
            graph_path=["Polyuria"],
        )
    )
    nodes = [
        _node("d1", "Type 2 Diabetes Mellitus", "Disease"),
        _node("p1", "Polyuria", "Phenotype"),
    ]
    edges = [_edge("d1", "p1")]
    _, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 1
    assert grounded == 1


def test_phenotype_name_match_case_insensitive():
    diagnosis = _dx(_diag("Pneumonia", graph_path=["FEVER", "cough"]))
    nodes = [
        _node("d1", "Pneumonia", "Disease"),
        _node("p1", "Fever", "Phenotype"),
        _node("p2", "Cough", "Phenotype"),
    ]
    edges = [_edge("d1", "p1"), _edge("d1", "p2")]
    _, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert grounded == 2


def test_multiple_diagnoses_each_counted_per_candidate():
    diagnosis = _dx(
        _diag("Pneumonia", graph_path=["Fever", "Cough"]),  # 2 grounded
        _diag("Asthma", graph_path=["Wheezing", "Not in graph"]),  # 1 grounded
    )
    nodes = [
        _node("d1", "Pneumonia", "Disease"),
        _node("d2", "Asthma", "Disease"),
        _node("p1", "Fever", "Phenotype"),
        _node("p2", "Cough", "Phenotype"),
        _node("p3", "Wheezing", "Phenotype"),
    ]
    edges = [
        _edge("d1", "p1"),
        _edge("d1", "p2"),
        _edge("d2", "p3"),
    ]
    result, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 4
    assert grounded == 3
    assert result.diagnoses[0].grounded_path_entries == 2
    assert result.diagnoses[0].hallucinated_path_entries == 0
    assert result.diagnoses[1].grounded_path_entries == 1
    assert result.diagnoses[1].hallucinated_path_entries == 1


def test_cross_candidate_edges_are_not_counted_for_wrong_diagnosis():
    """Pneumonia's edges should NOT be credited to Asthma's graph_path,
    even if the phenotype name happens to match something in the global
    node list."""
    diagnosis = _dx(
        _diag("Asthma", graph_path=["Fever"]),  # Asthma doesn't have Fever edge
    )
    nodes = [
        _node("d1", "Pneumonia", "Disease"),
        _node("d2", "Asthma", "Disease"),
        _node("p1", "Fever", "Phenotype"),
    ]
    # Fever is only connected to Pneumonia, NOT to Asthma
    edges = [_edge("d1", "p1")]
    _, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 1
    assert grounded == 0


def test_empty_graph_path_has_zero_total():
    diagnosis = _dx(_diag("Pneumonia", graph_path=[]))
    nodes = [_node("d1", "Pneumonia", "Disease")]
    edges: list[dict] = []
    _, total, grounded = gate_evidence_grounding(diagnosis, nodes, edges)
    assert total == 0
    assert grounded == 0


def test_empty_context_counts_all_entries_as_hallucinated():
    """If the LLM returned graph_path entries but the prompt context
    had no nodes/edges, every entry is hallucinated by definition.
    We don't early-exit to 'untested' — we correctly mark them as 0-grounded.
    """
    diagnosis = _dx(_diag("Pneumonia", graph_path=["Fever", "Cough"]))
    result, total, grounded = gate_evidence_grounding(diagnosis, [], [])
    assert total == 2
    assert grounded == 0
    assert result.diagnoses[0].grounded_path_entries == 0
    assert result.diagnoses[0].hallucinated_path_entries == 2


def test_empty_diagnosis_list_returns_zero():
    """No diagnoses at all = no grounding to measure."""
    diagnosis = DifferentialDiagnosis(
        diagnoses=[_diag("placeholder", graph_path=[])],  # schema requires ≥1
        reasoning_summary="",
    )
    result, total, grounded = gate_evidence_grounding(diagnosis, [], [])
    assert total == 0
    assert grounded == 0


def test_gate_never_rejects_diagnoses():
    """Gate 6.5 is diagnostic-only. It must never remove or alter
    a diagnosis — only annotate the per-item counts."""
    diagnosis = _dx(
        _diag("Totally Hallucinated Disease", graph_path=["Made up", "Also made up"]),
    )
    nodes = [_node("d1", "Real Disease")]
    edges: list[dict] = []
    result, _, _ = gate_evidence_grounding(diagnosis, nodes, edges)
    assert len(result.diagnoses) == 1
    assert result.diagnoses[0].disease_name == "Totally Hallucinated Disease"
    # Both entries flagged hallucinated but diagnosis still present
    assert result.diagnoses[0].hallucinated_path_entries == 2
