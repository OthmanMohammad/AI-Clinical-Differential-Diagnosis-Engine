"""Evaluation Pipeline — run eval cases against the live API.

Usage:
    python -m eval.run_eval --api-url http://localhost:8000 --api-key <key>
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import httpx

from eval.metrics import compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CASES_DIR = Path("eval/cases")


def load_cases(cases_dir: Path, max_cases: int = 100) -> list[dict]:
    """Load eval cases from JSON files."""
    cases = []
    for case_path in sorted(cases_dir.glob("case_*.json"))[:max_cases]:
        with open(case_path) as f:
            cases.append(json.load(f))
    logger.info("Loaded %d eval cases", len(cases))
    return cases


def run_case(
    case: dict,
    api_url: str,
    api_key: str,
    timeout: float = 30.0,
) -> dict:
    """Run a single eval case against the API."""
    payload = case["patient"]

    start = time.monotonic()
    try:
        resp = httpx.post(
            f"{api_url}/api/v1/diagnose",
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        elapsed = time.monotonic() - start

        if resp.status_code == 200:
            response_data = resp.json()
            predicted = [d["disease_name"] for d in response_data.get("diagnoses", [])]
        else:
            predicted = []
            response_data = {"error": resp.text}

        return {
            "expected": case.get("expected_diagnoses", []),
            "predicted": predicted,
            "icd_codes": case.get("icd_codes", []),
            "mapping_confidence": case.get("mapping_confidence", "automated"),
            "status_code": resp.status_code,
            "latency_ms": round(elapsed * 1000),
            "response": response_data,
        }

    except Exception as exc:
        elapsed = time.monotonic() - start
        return {
            "expected": case.get("expected_diagnoses", []),
            "predicted": [],
            "mapping_confidence": case.get("mapping_confidence", "automated"),
            "status_code": 0,
            "latency_ms": round(elapsed * 1000),
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PathoDX evaluation")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--max-cases", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("eval/results.json"))
    args = parser.parse_args()

    cases = load_cases(args.cases_dir, args.max_cases)
    if not cases:
        logger.error("No eval cases found in %s", args.cases_dir)
        return

    results = []
    for i, case in enumerate(cases):
        logger.info("Running case %d/%d", i + 1, len(cases))
        result = run_case(case, args.api_url, args.api_key)
        results.append(result)

    # Compute metrics
    metrics = compute_metrics(results)

    # Save results
    output = {
        "total_cases": len(results),
        "metrics": metrics,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    # Print summary
    print("\n=== Evaluation Results ===")
    print(f"  Total cases: {len(results)}")
    print(f"  Success rate: {metrics['success_rate']:.1%}")
    print(f"  Top-1 accuracy: {metrics['top1_accuracy']:.1%}")
    print(f"  Top-3 accuracy: {metrics['top3_accuracy']:.1%}")
    print(f"  Mean latency: {metrics['mean_latency_ms']:.0f}ms")
    print(f"  P95 latency: {metrics['p95_latency_ms']:.0f}ms")

    if "by_confidence" in metrics:
        print("\n  By mapping confidence:")
        for conf, m in metrics["by_confidence"].items():
            print(f"    {conf}: top3={m['top3_accuracy']:.1%} (n={m['count']})")

    print(f"\n  Results saved to {args.output}")


if __name__ == "__main__":
    main()
