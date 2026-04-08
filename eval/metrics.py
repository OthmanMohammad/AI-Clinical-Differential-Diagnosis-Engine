"""Evaluation metrics for PathoDX."""

from __future__ import annotations

from collections import defaultdict


def compute_metrics(results: list[dict]) -> dict:
    """Compute evaluation metrics from run results."""
    total = len(results)
    if total == 0:
        return {}

    successful = [r for r in results if r["status_code"] == 200]
    success_rate = len(successful) / total

    # Top-K accuracy: is any expected diagnosis in the top K predictions?
    top1_hits = 0
    top3_hits = 0

    for r in successful:
        expected_lower = {e.lower() for e in r.get("expected", [])}
        predicted = [p.lower() for p in r.get("predicted", [])]

        if predicted and any(p in expected_lower for p in predicted[:1]):
            top1_hits += 1
        if predicted and any(p in expected_lower for p in predicted[:3]):
            top3_hits += 1

    top1_accuracy = top1_hits / len(successful) if successful else 0
    top3_accuracy = top3_hits / len(successful) if successful else 0

    # Latency
    latencies = [r["latency_ms"] for r in results]
    mean_latency = sum(latencies) / len(latencies)
    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]

    # Metrics by mapping confidence
    by_confidence: dict[str, list[dict]] = defaultdict(list)
    for r in successful:
        conf = r.get("mapping_confidence", "unknown")
        by_confidence[conf].append(r)

    confidence_metrics = {}
    for conf, conf_results in by_confidence.items():
        conf_top3 = 0
        for r in conf_results:
            expected_lower = {e.lower() for e in r.get("expected", [])}
            predicted = [p.lower() for p in r.get("predicted", [])]
            if predicted and any(p in expected_lower for p in predicted[:3]):
                conf_top3 += 1

        confidence_metrics[conf] = {
            "count": len(conf_results),
            "top3_accuracy": conf_top3 / len(conf_results) if conf_results else 0,
        }

    return {
        "success_rate": success_rate,
        "top1_accuracy": top1_accuracy,
        "top3_accuracy": top3_accuracy,
        "mean_latency_ms": mean_latency,
        "p95_latency_ms": p95_latency,
        "by_confidence": confidence_metrics,
    }
