"""Unit tests for eval/metrics.py.

Runs without any external services. Catches regressions in:
- Disease name matching (word reorder, qualifiers, type preservation)
- Rank computation
- MRR calculation
- Top-K accuracy
- Graph-path rate
"""

from __future__ import annotations

import pytest

from eval.metrics import (
    _first_hit_rank,
    _has_graph_path,
    _matches,
    _tokenize_name,
    compute_metrics,
    diff_metrics,
    format_summary,
)


# -----------------------------
# Tokenization
# -----------------------------


def test_tokenize_reorder_produces_same_set():
    assert _tokenize_name("Type 2 Diabetes Mellitus") == _tokenize_name(
        "Diabetes Mellitus Type 2"
    )


def test_tokenize_keeps_numeric_single_chars():
    tokens = _tokenize_name("Type 2 Diabetes Mellitus")
    assert "2" in tokens
    assert "type" in tokens
    assert "diabetes" in tokens


def test_tokenize_drops_stopwords():
    tokens = _tokenize_name("Disease of the Kidney")
    # 'disease', 'of', 'the' dropped; 'kidney' kept
    assert tokens == {"kidney"}


def test_tokenize_empty_string():
    assert _tokenize_name("") == set()
    assert _tokenize_name("   ") == set()


def test_tokenize_preserves_type_number_distinction():
    t1 = _tokenize_name("Type 1 Diabetes")
    t2 = _tokenize_name("Type 2 Diabetes")
    assert t1 != t2
    assert "1" in t1 and "2" not in t1
    assert "2" in t2 and "1" not in t2


# -----------------------------
# _matches
# -----------------------------


def test_matches_word_reorder():
    assert _matches("Type 2 Diabetes Mellitus", {"diabetes mellitus type 2"})
    assert _matches("diabetes mellitus type 2", {"type 2 diabetes mellitus"})


def test_matches_qualifier_extra_word():
    assert _matches("Acute Pancreatitis", {"pancreatitis"})
    assert _matches("Pancreatitis", {"acute pancreatitis"})


def test_matches_does_not_cross_types():
    """Type 1 DM must NOT match Type 2 DM."""
    assert not _matches("Type 1 Diabetes Mellitus", {"type 2 diabetes mellitus"})


def test_matches_negative_different_disease():
    assert not _matches("Asthma", {"copd"})
    assert not _matches("Pneumonia", {"bronchitis"})


def test_matches_empty_predicted():
    assert not _matches("", {"copd"})
    assert not _matches("   ", {"copd"})


def test_matches_multi_expected_aliases():
    assert _matches("CHF", {"congestive heart failure", "chf", "heart failure"})


def test_matches_common_cold_not_pneumonia():
    assert not _matches("Common Cold", {"pneumonia"})


# -----------------------------
# _first_hit_rank
# -----------------------------


def test_first_hit_rank_first_position():
    assert (
        _first_hit_rank(
            ["Diabetes Mellitus Type 2", "Wolfram Syndrome"],
            {"type 2 diabetes mellitus"},
        )
        == 1
    )


def test_first_hit_rank_second_position():
    assert (
        _first_hit_rank(
            ["Wolfram Syndrome", "Diabetes Mellitus Type 2"],
            {"type 2 diabetes mellitus"},
        )
        == 2
    )


def test_first_hit_rank_no_match():
    assert _first_hit_rank(["a", "b", "c"], {"d"}) == 0


def test_first_hit_rank_empty_predicted():
    assert _first_hit_rank([], {"anything"}) == 0


# -----------------------------
# _has_graph_path
# -----------------------------


def test_has_graph_path_populated():
    resp = {"diagnoses": [{"disease_name": "x", "graph_path": ["a", "b"]}]}
    assert _has_graph_path(resp) is True


def test_has_graph_path_empty_list():
    resp = {"diagnoses": [{"disease_name": "x", "graph_path": []}]}
    assert _has_graph_path(resp) is False


def test_has_graph_path_missing_field():
    resp = {"diagnoses": [{"disease_name": "x"}]}
    assert _has_graph_path(resp) is False


def test_has_graph_path_no_diagnoses():
    assert _has_graph_path({"diagnoses": []}) is False
    assert _has_graph_path({}) is False


# -----------------------------
# compute_metrics
# -----------------------------


@pytest.fixture
def fake_results():
    return [
        {
            "status_code": 200,
            "latency_ms": 1000,
            "split": "train",
            "expected": ["Type 2 Diabetes Mellitus"],
            "predicted": ["Diabetes Mellitus Type 2", "Polydipsia"],
            "response": {
                "diagnoses": [
                    {
                        "disease_name": "Diabetes Mellitus Type 2",
                        "graph_path": ["polyuria", "Type 2 DM"],
                    }
                ]
            },
        },
        {
            "status_code": 200,
            "latency_ms": 2000,
            "split": "train",
            "expected": ["Pneumonia"],
            "predicted": ["Bronchitis", "Community-Acquired Pneumonia"],
            "response": {
                "diagnoses": [{"disease_name": "Bronchitis", "graph_path": []}]
            },
        },
        {
            "status_code": 500,
            "latency_ms": 500,
            "split": "train",
            "expected": ["STEMI"],
            "predicted": [],
        },
    ]


def test_compute_metrics_success_rate(fake_results):
    m = compute_metrics(fake_results)
    assert m["success_rate"] == pytest.approx(2 / 3)


def test_compute_metrics_mrr(fake_results):
    m = compute_metrics(fake_results)
    # Case 1: rank 1 → 1.0, Case 2: rank 2 → 0.5. Mean over successful = 0.75.
    assert m["mrr"] == pytest.approx(0.75)


def test_compute_metrics_top1_accuracy(fake_results):
    m = compute_metrics(fake_results)
    assert m["top1_accuracy"] == pytest.approx(0.5)


def test_compute_metrics_top3_accuracy(fake_results):
    m = compute_metrics(fake_results)
    assert m["top3_accuracy"] == pytest.approx(1.0)


def test_compute_metrics_graph_path_rate(fake_results):
    m = compute_metrics(fake_results)
    # 1 of 2 successful cases had a non-empty graph_path on the top diagnosis.
    assert m["graph_path_rate"] == pytest.approx(0.5)


def test_compute_metrics_empty_input():
    assert compute_metrics([]) == {}


def test_format_summary_contains_key_metrics(fake_results):
    m = compute_metrics(fake_results)
    out = format_summary(m, label="test-label")
    assert "test-label" in out
    assert "MRR" in out
    assert "Top-1" in out
    assert "Graph-path" in out


def test_diff_metrics_reports_deltas():
    a = {"mrr": 0.3, "top1_accuracy": 0.2, "top3_accuracy": 0.5, "graph_path_rate": 0.1, "evidence_grounding_rate": 0.1, "mean_latency_ms": 2000}
    b = {"mrr": 0.6, "top1_accuracy": 0.4, "top3_accuracy": 0.8, "graph_path_rate": 0.5, "evidence_grounding_rate": 0.55, "mean_latency_ms": 1500}
    out = diff_metrics(a, b)
    assert "+0.300" in out  # MRR delta
    assert "Baseline" in out
    # Evidence grounding delta surfaces in the diff
    assert "Evidence grounding" in out


# ---------------------------------------------------------------------------
# evidence_grounding_rate
# ---------------------------------------------------------------------------


def test_evidence_grounding_rate_all_grounded():
    results = [
        {
            "status_code": 200, "latency_ms": 100, "split": "train",
            "expected": ["T2DM"], "predicted": ["T2DM"],
            "response": {
                "diagnoses": [{"disease_name": "T2DM", "graph_path": ["Polyuria", "Polydipsia"]}],
                "total_evidence_entries": 2,
                "grounded_evidence_entries": 2,
            },
        },
    ]
    m = compute_metrics(results)
    assert m["evidence_grounding_rate"] == pytest.approx(1.0)
    assert m["total_evidence_entries"] == 2
    assert m["grounded_evidence_entries"] == 2


def test_evidence_grounding_rate_all_hallucinated():
    """T2DM case in the wild: LLM returned graph_path but the edges
    weren't in context, so grounded_evidence_entries=0."""
    results = [
        {
            "status_code": 200, "latency_ms": 100, "split": "train",
            "expected": ["T2DM"], "predicted": ["T2DM"],
            "response": {
                "diagnoses": [{"disease_name": "T2DM", "graph_path": ["Polyuria", "Polydipsia", "Fatigue"]}],
                "total_evidence_entries": 3,
                "grounded_evidence_entries": 0,
            },
        },
    ]
    m = compute_metrics(results)
    assert m["evidence_grounding_rate"] == pytest.approx(0.0)
    # graph_path_rate (the weak proxy) is still 100% because the field
    # IS populated — just with hallucinated entries. This is the whole
    # point of adding evidence_grounding_rate: it separates "populated"
    # from "actually grounded".
    assert m["graph_path_rate"] == pytest.approx(1.0)


def test_evidence_grounding_rate_partial_across_cases():
    results = [
        {
            "status_code": 200, "latency_ms": 100, "split": "train",
            "expected": ["A"], "predicted": ["A"],
            "response": {
                "diagnoses": [{"disease_name": "A", "graph_path": ["x", "y"]}],
                "total_evidence_entries": 2,
                "grounded_evidence_entries": 2,
            },
        },
        {
            "status_code": 200, "latency_ms": 100, "split": "train",
            "expected": ["B"], "predicted": ["B"],
            "response": {
                "diagnoses": [{"disease_name": "B", "graph_path": ["p", "q", "r"]}],
                "total_evidence_entries": 3,
                "grounded_evidence_entries": 1,
            },
        },
    ]
    m = compute_metrics(results)
    # (2 grounded + 1 grounded) / (2 total + 3 total) = 3/5 = 0.6
    assert m["evidence_grounding_rate"] == pytest.approx(0.6)


def test_evidence_grounding_rate_missing_fields_is_zero():
    """Older API responses without the new fields get 0 (not divide-by-zero)."""
    results = [
        {
            "status_code": 200, "latency_ms": 100, "split": "train",
            "expected": ["A"], "predicted": ["A"],
            "response": {
                "diagnoses": [{"disease_name": "A", "graph_path": ["x"]}],
                # No total_evidence_entries / grounded_evidence_entries
            },
        },
    ]
    m = compute_metrics(results)
    assert m["evidence_grounding_rate"] == 0.0
    assert m["total_evidence_entries"] == 0
