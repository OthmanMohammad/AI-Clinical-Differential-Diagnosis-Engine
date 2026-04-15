"""Evaluation Pipeline — run eval cases against the live API.

Usage:
    python -m eval.run_eval \\
        --api-url http://127.0.0.1:8080 \\
        --api-key <key> \\
        --output eval/results/baseline.json \\
        --label baseline

    # Hold-out only (never tune against these)
    python -m eval.run_eval --api-url ... --api-key ... --only-holdout

    # Compare a new run against a saved baseline
    python -m eval.run_eval --api-url ... --api-key ... --diff eval/results/baseline.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import httpx

from eval.metrics import compute_metrics, diff_metrics, format_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CASES_DIR = Path("eval/cases")


def load_cases(
    cases_dir: Path,
    max_cases: int = 100,
    split: str = "all",
) -> list[dict]:
    """Load eval cases from JSON files.

    Args:
        cases_dir: Directory containing case_*.json.
        max_cases: Maximum number of cases to load.
        split: "all", "train" (cases with split=train), or "holdout".
    """
    cases: list[dict] = []
    for case_path in sorted(cases_dir.glob("case_*.json"))[:max_cases]:
        with open(case_path) as f:
            case = json.load(f)
        case_split = case.get("split", "train")
        if split == "all" or split == case_split:
            case["_source_file"] = case_path.name
            cases.append(case)
    logger.info("Loaded %d eval cases (split=%s)", len(cases), split)
    return cases


def run_case(
    case: dict,
    api_url: str,
    api_key: str,
    timeout: float = 60.0,
) -> dict:
    """Run a single eval case against the API."""
    payload = case["patient"]
    case_id = case.get("_source_file", case.get("id", "?"))

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
            predicted = [
                d.get("disease_name", "")
                for d in response_data.get("diagnoses", [])
            ]
        else:
            predicted = []
            response_data = {"error": resp.text[:500]}

        return {
            "case_id": case_id,
            "expected": case.get("expected_diagnoses", []),
            "predicted": predicted,
            "icd_codes": case.get("icd_codes", []),
            "mapping_confidence": case.get("mapping_confidence", "automated"),
            "split": case.get("split", "train"),
            "status_code": resp.status_code,
            "latency_ms": round(elapsed * 1000),
            "response": response_data,
        }

    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.warning("case_failed case_id=%s error=%s", case_id, exc)
        return {
            "case_id": case_id,
            "expected": case.get("expected_diagnoses", []),
            "predicted": [],
            "mapping_confidence": case.get("mapping_confidence", "automated"),
            "split": case.get("split", "train"),
            "status_code": 0,
            "latency_ms": round(elapsed * 1000),
            "error": str(exc)[:500],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PathoDX evaluation")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--max-cases", type=int, default=100)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/results/run.json"),
        help="Where to save the full results JSON.",
    )
    parser.add_argument(
        "--label",
        default="",
        help="Human label for this run (e.g. 'baseline', 'post_tier2').",
    )
    parser.add_argument(
        "--only-holdout",
        action="store_true",
        help="Run only cases with split=holdout (never tune against these).",
    )
    parser.add_argument(
        "--only-train",
        action="store_true",
        help="Run only cases with split=train.",
    )
    parser.add_argument(
        "--diff",
        type=Path,
        default=None,
        help="Optional path to a previous results.json to diff against.",
    )
    args = parser.parse_args()

    split = "all"
    if args.only_holdout:
        split = "holdout"
    elif args.only_train:
        split = "train"

    cases = load_cases(args.cases_dir, args.max_cases, split=split)
    if not cases:
        logger.error("No eval cases found in %s (split=%s)", args.cases_dir, split)
        return

    results = []
    for i, case in enumerate(cases):
        logger.info("Running case %d/%d: %s", i + 1, len(cases), case["_source_file"])
        result = run_case(case, args.api_url, args.api_key)
        results.append(result)

    metrics = compute_metrics(results)
    # Per-split breakdown
    train_metrics = compute_metrics([r for r in results if r.get("split") == "train"])
    holdout_metrics = compute_metrics([r for r in results if r.get("split") == "holdout"])

    output = {
        "label": args.label,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": len(results),
        "metrics": metrics,
        "metrics_train": train_metrics,
        "metrics_holdout": holdout_metrics,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print()
    print(format_summary(metrics, label=args.label or "Evaluation"))
    if train_metrics and train_metrics.get("success_rate") is not None:
        print()
        print(format_summary(train_metrics, label="train split"))
    if holdout_metrics and holdout_metrics.get("success_rate") is not None:
        print()
        print(format_summary(holdout_metrics, label="holdout split"))

    if args.diff and args.diff.exists():
        try:
            with open(args.diff) as f:
                prev = json.load(f)
            print()
            print(diff_metrics(prev.get("metrics", {}), metrics))
        except Exception as exc:
            logger.warning("failed to load diff baseline: %s", exc)

    print()
    print(f"  Results saved to {args.output}")


if __name__ == "__main__":
    main()
