"""Integration smoke test for the full diagnose pipeline.

This is NOT a unit test — it hits a running backend (local Docker
compose stack OR the Oracle VM) and validates the whole Graph RAG
pipeline end-to-end. Run it after merging the Tier 2 retrieval
rewrite to confirm nothing is broken in production.

Usage
-----

Skip-by-default mode (doesn't run in normal pytest):
    pytest tests/integration/                  # skipped
    pytest tests/unit/                         # unit tests only

Explicit run against local or remote backend:
    MOOSEGLOVE_API_URL=http://127.0.0.1:8080 \\
    MOOSEGLOVE_API_KEY=<key> \\
    pytest tests/integration/test_diagnose_smoke.py -v

Against production (once Session 3 is live):
    MOOSEGLOVE_API_URL=https://api.mooseglove.com \\
    MOOSEGLOVE_API_KEY=<prod key> \\
    pytest tests/integration/test_diagnose_smoke.py -v

What's tested
-------------
- /health and /ready return 200
- /api/v1/diagnose with the T2DM golden case returns:
    * HTTP 200
    * non-empty diagnoses list
    * top diagnosis matches "Type 2 Diabetes" (case-insens, token-set)
    * top diagnosis has verified_in_graph=True
    * top diagnosis has a non-empty graph_path (Tier 2 guarantee)

This test is intentionally thin — the heavy assertions live in
tests/unit/ and the full accuracy measurement lives in eval/run_eval.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Allow sibling imports from eval/ without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.metrics import _matches  # noqa: E402

API_URL = os.environ.get("MOOSEGLOVE_API_URL")
API_KEY = os.environ.get("MOOSEGLOVE_API_KEY")

# Skip the whole module unless both env vars are set. This keeps
# the integration tests out of the default pytest run while still
# making them easy to fire on demand.
pytestmark = pytest.mark.skipif(
    not (API_URL and API_KEY),
    reason="MOOSEGLOVE_API_URL and MOOSEGLOVE_API_KEY must be set",
)


T2DM_PAYLOAD = {
    "symptoms": [
        "polyuria",
        "polydipsia",
        "fatigue",
        "blurred vision",
        "unintended weight loss",
    ],
    "age": 52,
    "sex": "male",
    "history": ["hypertension", "obesity", "hyperlipidemia"],
    "medications": ["amlodipine", "atorvastatin"],
    "labs": {"glucose": 287, "hba1c": 9.2},
    "free_text": "3-month history of increased thirst and urination with fatigue.",
}


@pytest.fixture(scope="module")
def http_client():
    import httpx

    with httpx.Client(base_url=API_URL, timeout=60.0) as client:
        yield client


def test_health(http_client):
    r = http_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "healthy")


def test_ready(http_client):
    r = http_client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    checks = body.get("checks", {})
    # Both Neo4j and Qdrant must be reporting OK
    neo4j = checks.get("neo4j", {})
    qdrant = checks.get("qdrant", {})
    assert neo4j.get("ok") is True, f"Neo4j not ready: {neo4j}"
    assert qdrant.get("ok") is True, f"Qdrant not ready: {qdrant}"


def test_diagnose_t2dm_golden_case(http_client):
    """The headline test. If this fails on a backend claiming to
    run the Tier 2 retrieval rewrite, something is wrong.
    """
    r = http_client.post(
        "/api/v1/diagnose",
        json=T2DM_PAYLOAD,
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200, f"API returned {r.status_code}: {r.text[:300]}"
    body = r.json()

    diagnoses = body.get("diagnoses") or []
    assert diagnoses, f"empty diagnoses: {body}"

    top = diagnoses[0]

    # Top diagnosis must resolve to Type 2 Diabetes Mellitus via the
    # same token-set matcher the eval harness uses.
    assert _matches(top["disease_name"], {"type 2 diabetes mellitus"}), (
        f"top diagnosis '{top['disease_name']}' is not T2DM"
    )

    # Hallucination gate must have verified it against the graph
    assert top.get("verified_in_graph") is True, (
        f"top T2DM diagnosis not verified in graph: {top}"
    )

    # The Tier 2 guarantee: graph_path must not be empty for the
    # top diagnosis when the retrieval layer surfaced it via the
    # phenotype intersection query.
    graph_path = top.get("graph_path") or []
    assert graph_path, (
        f"top T2DM diagnosis has empty graph_path — Tier 2 per-candidate "
        f"evidence attribution is broken. Full diagnosis: {top}"
    )

    # And confidence should be high — glucose 287 + HbA1c 9.2 is
    # textbook T2DM.
    assert top.get("confidence", 0) >= 0.8, (
        f"top T2DM confidence too low: {top.get('confidence')}"
    )


def test_diagnose_without_api_key_rejected(http_client):
    r = http_client.post("/api/v1/diagnose", json=T2DM_PAYLOAD)
    assert r.status_code == 401


def test_diagnose_rate_limit_enforced(http_client):
    """Send 15 rapid requests; the rate limiter should kick in
    somewhere in the last few. If all 15 succeed, slowapi is off."""
    import time

    statuses: list[int] = []
    for _ in range(15):
        r = http_client.post(
            "/api/v1/diagnose",
            json=T2DM_PAYLOAD,
            headers={"X-API-Key": API_KEY},
        )
        statuses.append(r.status_code)
        time.sleep(0.1)

    # We expect at least ONE 429 in the tail of the burst. If nothing
    # 429s, the rate limiter is not wired. We deliberately don't assert
    # all 15 hit — the exact cutoff depends on timing.
    assert 429 in statuses, (
        f"expected at least one 429 in 15 rapid requests, got {statuses}"
    )
