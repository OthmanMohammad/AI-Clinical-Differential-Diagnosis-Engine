"""Evaluation metrics for PathoDX.

Computes:
- success_rate    — fraction of cases where the API returned HTTP 200
- top1_accuracy   — fraction where the expected diagnosis is #1
- top3_accuracy   — fraction where the expected diagnosis is in the top 3
- top5_accuracy   — fraction where the expected diagnosis is in the top 5
- mrr             — mean reciprocal rank. For each case, the reciprocal of the
                    rank position of the first expected diagnosis in the
                    predicted list (0 if not found). The single best metric
                    for small test sets because it differentiates "rank 1"
                    from "rank 3" without needing more cases.
- graph_path_rate — fraction of successful diagnoses that cite at least one
                    graph edge. Catches regressions where Tier 2's per-
                    candidate evidence attribution breaks and diagnoses
                    come back with empty graph_path (the "LLM fell back
                    to world knowledge" failure mode).
- mean_latency_ms / p95_latency_ms
- by_confidence breakdown (preserved from the original metrics)
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# Tokens too generic to carry diagnostic signal. Deliberately DOES NOT
# include "type", "acute", "chronic", "primary", "secondary" — those
# carry real clinical meaning (Type 1 vs Type 2 diabetes, acute vs
# chronic kidney disease, primary vs secondary hypothyroidism).
_MATCH_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "in", "on", "with", "to", "for",
    "by", "at", "from", "as", "is", "be", "syndrome", "disease", "disorder",
    "condition", "mellitus",
})


def _tokenize_name(name: str) -> set[str]:
    """Tokenize a disease name into a set of meaningful lowercase tokens.

    Single-character numeric tokens (like "2" in "Type 2 Diabetes") are
    KEPT because they carry diagnostic signal. Single-character alphabetic
    tokens ("a", "i") are dropped as noise.
    """
    if not name:
        return set()
    raw = re.findall(r"[a-z0-9]+", name.lower())
    return {
        t for t in raw
        if t not in _MATCH_STOPWORDS
        and (t.isdigit() or len(t) > 1)
    }


def _matches(predicted: str, expected_set: set[str]) -> bool:
    """Case-insensitive token-set match between a predicted name and any
    expected name. A match is declared if the smaller token set is a
    subset of the larger (after stripping generic stopwords).

    Handles:
    - Word reordering: "Type 2 Diabetes Mellitus" ↔ "Diabetes Mellitus Type 2"
    - Extra qualifiers: "Acute Pancreatitis" ↔ "Pancreatitis"
    - Substring-free aliases: "CHF" ↔ "Congestive Heart Failure"
      (only works if we also add the expansion as an expected alias
      in the case file — see eval/cases/README.md)
    """
    p_tokens = _tokenize_name(predicted)
    if not p_tokens:
        return False
    for e in expected_set:
        e_tokens = _tokenize_name(e)
        if not e_tokens:
            continue
        smaller, larger = (
            (p_tokens, e_tokens) if len(p_tokens) <= len(e_tokens) else (e_tokens, p_tokens)
        )
        if smaller.issubset(larger):
            return True
    return False


def _first_hit_rank(predicted: list[str], expected_set: set[str]) -> int:
    """Return the 1-indexed rank of the first predicted name that matches any
    expected name. Returns 0 if no match."""
    for i, p in enumerate(predicted):
        if _matches(p, expected_set):
            return i + 1
    return 0


def _has_graph_path(response: dict) -> bool:
    """True if the TOP diagnosis has a non-empty graph_path.

    This is the Tier 2 shipping guard — after the retrieval rewrite, the
    top diagnosis should almost always have graph evidence. If most of them
    come back empty, the per-candidate evidence attribution is broken.
    """
    diagnoses = (response or {}).get("diagnoses") or []
    if not diagnoses:
        return False
    top = diagnoses[0] or {}
    path = top.get("graph_path") or []
    return len(path) > 0


def compute_metrics(results: list[dict]) -> dict:
    """Compute evaluation metrics from run results."""
    total = len(results)
    if total == 0:
        return {}

    successful = [r for r in results if r.get("status_code") == 200]
    success_rate = len(successful) / total

    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    reciprocal_ranks: list[float] = []
    graph_path_hits = 0

    for r in successful:
        expected_lower = {e.lower() for e in r.get("expected", [])}
        predicted = [p for p in r.get("predicted", []) if p]

        rank = _first_hit_rank(predicted, expected_lower)
        if rank == 1:
            top1_hits += 1
        if 1 <= rank <= 3:
            top3_hits += 1
        if 1 <= rank <= 5:
            top5_hits += 1
        reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

        if _has_graph_path(r.get("response", {})):
            graph_path_hits += 1

    n_success = len(successful) or 1
    top1_accuracy = top1_hits / n_success
    top3_accuracy = top3_hits / n_success
    top5_accuracy = top5_hits / n_success
    mrr = sum(reciprocal_ranks) / n_success if reciprocal_ranks else 0.0
    graph_path_rate = graph_path_hits / n_success

    # Latency
    latencies = [r.get("latency_ms", 0) for r in results]
    mean_latency = sum(latencies) / len(latencies) if latencies else 0
    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_latency = (
        sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
        if sorted_latencies
        else 0
    )

    # Metrics by mapping confidence (preserved from original)
    by_confidence: dict[str, list[dict]] = defaultdict(list)
    for r in successful:
        conf = r.get("mapping_confidence", "unknown")
        by_confidence[conf].append(r)

    confidence_metrics: dict[str, dict[str, Any]] = {}
    for conf, conf_results in by_confidence.items():
        conf_top3 = 0
        conf_rr: list[float] = []
        for r in conf_results:
            expected_lower = {e.lower() for e in r.get("expected", [])}
            predicted = [p for p in r.get("predicted", []) if p]
            rank = _first_hit_rank(predicted, expected_lower)
            if 1 <= rank <= 3:
                conf_top3 += 1
            conf_rr.append(1.0 / rank if rank > 0 else 0.0)

        confidence_metrics[conf] = {
            "count": len(conf_results),
            "top3_accuracy": conf_top3 / len(conf_results) if conf_results else 0,
            "mrr": sum(conf_rr) / len(conf_rr) if conf_rr else 0,
        }

    return {
        "success_rate": success_rate,
        "top1_accuracy": top1_accuracy,
        "top3_accuracy": top3_accuracy,
        "top5_accuracy": top5_accuracy,
        "mrr": mrr,
        "graph_path_rate": graph_path_rate,
        "mean_latency_ms": mean_latency,
        "p95_latency_ms": p95_latency,
        "by_confidence": confidence_metrics,
    }


def format_summary(metrics: dict, label: str = "") -> str:
    """Format a metrics dict as a human-readable summary block."""
    lines = []
    if label:
        lines.append(f"=== {label} ===")
    else:
        lines.append("=== Evaluation Metrics ===")
    lines.append(f"  Success rate:     {metrics.get('success_rate', 0):.1%}")
    lines.append(f"  MRR:              {metrics.get('mrr', 0):.3f}")
    lines.append(f"  Top-1 accuracy:   {metrics.get('top1_accuracy', 0):.1%}")
    lines.append(f"  Top-3 accuracy:   {metrics.get('top3_accuracy', 0):.1%}")
    lines.append(f"  Top-5 accuracy:   {metrics.get('top5_accuracy', 0):.1%}")
    lines.append(f"  Graph-path rate:  {metrics.get('graph_path_rate', 0):.1%}")
    lines.append(f"  Mean latency:     {metrics.get('mean_latency_ms', 0):.0f}ms")
    lines.append(f"  P95 latency:      {metrics.get('p95_latency_ms', 0):.0f}ms")
    return "\n".join(lines)


def diff_metrics(baseline: dict, current: dict) -> str:
    """Format a before/after comparison between two metrics dicts."""
    def _delta(key: str, fmt: str = "{:+.3f}") -> str:
        b = baseline.get(key, 0)
        c = current.get(key, 0)
        if isinstance(b, (int, float)) and isinstance(c, (int, float)):
            return fmt.format(c - b)
        return "n/a"

    lines = [
        "=== Baseline → Current ===",
        f"  MRR:             {baseline.get('mrr', 0):.3f}"
        f" → {current.get('mrr', 0):.3f}  ({_delta('mrr')})",
        f"  Top-1 accuracy:  {baseline.get('top1_accuracy', 0):.1%}"
        f" → {current.get('top1_accuracy', 0):.1%}"
        f"  ({_delta('top1_accuracy', '{:+.1%}')})",
        f"  Top-3 accuracy:  {baseline.get('top3_accuracy', 0):.1%}"
        f" → {current.get('top3_accuracy', 0):.1%}"
        f"  ({_delta('top3_accuracy', '{:+.1%}')})",
        f"  Graph-path rate: {baseline.get('graph_path_rate', 0):.1%}"
        f" → {current.get('graph_path_rate', 0):.1%}"
        f"  ({_delta('graph_path_rate', '{:+.1%}')})",
        f"  Mean latency:    {baseline.get('mean_latency_ms', 0):.0f}ms"
        f" → {current.get('mean_latency_ms', 0):.0f}ms",
    ]
    return "\n".join(lines)
