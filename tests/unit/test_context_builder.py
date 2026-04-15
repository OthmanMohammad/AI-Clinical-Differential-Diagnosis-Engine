"""Unit tests for app/core/context_builder.py.

Focus: the v3 per-candidate serialization, which is the explicit fix
for the "graph_path is empty on correct top diagnosis" failure mode.
The serialized output is what the LLM sees, so if it doesn't contain
per-candidate evidence in a recognizable form the whole rewrite is
pointless.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.core.context_builder import (  # noqa: E402
    build_messages_v3,
    serialize_candidates,
    serialize_subgraph,
)
from app.core.lab_rules import RuleBoost  # noqa: E402
from app.core.retrieval import Candidate, MatchedEdge  # noqa: E402
from app.models.patient import PatientIntake  # noqa: E402


def _edge(name: str, rel="disease_phenotype_positive"):
    return MatchedEdge(
        phenotype_id=f"p_{name.lower().replace(' ', '_')}",
        phenotype_name=name,
        rel_type=rel,
    )


def _intake() -> PatientIntake:
    return PatientIntake(
        symptoms=["polyuria", "polydipsia", "fatigue"],
        age=52,
        sex="male",
        history=[],
        medications=[],
        labs={"glucose": 287.0, "hba1c": 9.2},
        free_text="",
    )


# ---------------------------------------------------------------------------
# serialize_candidates
# ---------------------------------------------------------------------------


def test_serialize_candidates_empty():
    out = serialize_candidates([])
    assert "CANDIDATE DIAGNOSES" in out
    assert "none" in out.lower()


def test_serialize_candidates_shows_rank_and_score():
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="Type 2 Diabetes Mellitus",
            overlap_count=4,
            score=25.0,
            matched_edges=[
                _edge("Polyuria"),
                _edge("Polydipsia"),
                _edge("Fatigue"),
                _edge("Blurred vision"),
            ],
            source="graph",
        )
    ]
    out = serialize_candidates(cands)
    assert "#1" in out
    assert "Type 2 Diabetes Mellitus" in out
    assert "score 25.00" in out
    assert "source: graph" in out
    assert "phenotype_overlap: 4" in out


def test_serialize_candidates_includes_matched_edges_with_rel_type():
    """This is the explicit fix for the bug where the LLM couldn't
    tell which edges supported which diagnosis. Each edge must appear
    under its candidate's block with its relationship type visible."""
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="T2DM",
            overlap_count=2,
            score=2.0,
            matched_edges=[
                _edge("Polyuria"),
                _edge("Polydipsia", rel="disease_phenotype_positive"),
            ],
            source="graph",
        )
    ]
    out = serialize_candidates(cands)
    assert "Polyuria" in out
    assert "Polydipsia" in out
    assert "disease_phenotype_positive" in out
    # The phenotype list should be under a "matched phenotypes" header
    assert "matched phenotypes (2)" in out


def test_serialize_candidates_includes_rule_boosts():
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="Type 2 Diabetes Mellitus",
            overlap_count=4,
            score=25.0,
            matched_edges=[_edge("Polyuria")],
            rule_boosts=[
                RuleBoost(
                    disease_name="Type 2 Diabetes Mellitus",
                    multiplier=2.5,
                    rule_id="hyperglycemia_diabetes",
                    rule_label="Hyperglycemia",
                    rationale="glucose ≥200 meets ADA diagnostic threshold",
                )
            ],
            source="graph",
        )
    ]
    out = serialize_candidates(cands)
    assert "clinical rules that fired" in out
    assert "glucose ≥200" in out
    assert "x2.5" in out


def test_serialize_candidates_rule_only_flagged():
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="Sepsis",
            overlap_count=0,
            score=2.2,
            matched_edges=[],
            rule_boosts=[
                RuleBoost(
                    disease_name="Sepsis",
                    multiplier=2.2,
                    rule_id="elevated_lactate_sepsis",
                    rule_label="",
                    rationale="elevated lactate",
                )
            ],
            source="clinical_rule",
        )
    ]
    out = serialize_candidates(cands)
    assert "source: clinical_rule" in out
    assert "none — rule-only candidate" in out


def test_serialize_candidates_multiple_blocks_separate_evidence():
    """Each candidate's evidence must be in its own block. This is the
    anti-flat-subgraph invariant."""
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="T2DM",
            overlap_count=3,
            score=15.0,
            matched_edges=[_edge("Polyuria"), _edge("Polydipsia"), _edge("Fatigue")],
            source="graph",
        ),
        Candidate(
            disease_id="d2",
            disease_name="Wolfram Syndrome",
            overlap_count=1,
            score=1.0,
            matched_edges=[_edge("Polydipsia")],
            source="graph",
        ),
    ]
    out = serialize_candidates(cands)
    lines = out.split("\n")
    # Find the rank 1 and rank 2 headers
    rank1 = next(i for i, l in enumerate(lines) if "#1" in l)
    rank2 = next(i for i, l in enumerate(lines) if "#2" in l)
    assert rank1 < rank2
    # Between the two ranks there must be T2DM's phenotypes, not Wolfram's
    block1 = "\n".join(lines[rank1:rank2])
    block2 = "\n".join(lines[rank2:])
    assert "Polyuria" in block1
    assert "Fatigue" in block1
    assert "Polyuria" not in block2  # not in Wolfram's block
    assert "Polydipsia" in block2  # Wolfram's only match


# ---------------------------------------------------------------------------
# build_messages_v3 end-to-end
# ---------------------------------------------------------------------------


def test_build_messages_v3_includes_patient_and_candidates(tmp_path, monkeypatch):
    cands = [
        Candidate(
            disease_id="d1",
            disease_name="Type 2 Diabetes Mellitus",
            overlap_count=4,
            score=25.0,
            matched_edges=[_edge("Polyuria"), _edge("Polydipsia")],
            source="graph",
        )
    ]
    messages, version = build_messages_v3(_intake(), cands)
    assert version == "3.0"
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    user = messages[1]["content"]
    # Patient data
    assert "polyuria" in user
    assert "287" in user  # glucose value
    # Candidate block
    assert "Type 2 Diabetes Mellitus" in user
    assert "Polyuria" in user
    assert "disease_phenotype_positive" in user
    # Output schema
    assert "DifferentialDiagnosis" in user or "disease_name" in user


def test_build_messages_v3_truncates_long_candidate_list():
    """If we hand in 50 candidates, build_messages_v3 should only
    serialize the top N to keep the token count bounded."""
    cands = [
        Candidate(
            disease_id=f"d{i}",
            disease_name=f"Disease {i}",
            overlap_count=2,
            score=float(50 - i),
            matched_edges=[_edge(f"Sym {i}")],
            source="graph",
        )
        for i in range(50)
    ]
    messages, _ = build_messages_v3(_intake(), cands, max_candidates=5)
    user = messages[1]["content"]
    assert "Disease 0" in user
    assert "Disease 4" in user
    # The 6th candidate should NOT appear — it's beyond max_candidates
    assert "Disease 49" not in user


# ---------------------------------------------------------------------------
# Legacy serialize_subgraph — regression test to ensure v2 still works
# ---------------------------------------------------------------------------


def test_serialize_subgraph_v2_still_works():
    nodes = [
        {"id": "n1", "name": "T2DM", "type": "Disease"},
        {"id": "n2", "name": "Polyuria", "type": "Phenotype"},
    ]
    rels = [
        {"source": "n1", "target": "n2", "type": "disease_phenotype_positive"}
    ]
    out = serialize_subgraph(nodes, rels)
    assert "KNOWLEDGE GRAPH CONTEXT" in out
    assert "T2DM" in out
    assert "Polyuria" in out
    assert "disease_phenotype_positive" in out
