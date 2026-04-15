"""Unit tests for app/core/retrieval.py.

The retrieval layer is the heart of Tier 2. We test its behaviour
against a fake AsyncDriver that returns canned records, so we don't
need a real Neo4j. The fake driver accepts a dict of (disease, overlap,
matched_edges) rows and serves them via a stub session.

Tests cover:
- The phenotype-intersection query returns graph candidates in the
  right score order with per-candidate matched edges attached
- Rule boosts amplify graph candidates that match by name (case-insens)
- Rule boosts that don't match any graph candidate are treated as
  "unmatched" and only seed fallback candidates when the graph pool
  is too thin
- Rule-only candidates are flagged source="clinical_rule"
- Ranking puts the highest-scored candidate first, including after
  rule amplification (the T2DM case)
- Empty phenotype list + no rule matches raises RetrievalError
- LRU cache on phenotype intersection returns the same candidates
  without re-querying Neo4j
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.core import retrieval  # noqa: E402
from app.core.lab_rules import ClinicalRule, DiseaseBoost, RuleBoost  # noqa: E402
from app.core.retrieval import (  # noqa: E402
    Candidate,
    MatchedEdge,
    RetrievalError,
    _apply_rule_boosts,
    retrieve_candidates,
)
from app.services.disease_index import (  # noqa: E402
    DiseaseIndex,
    DiseaseRecord,
    reset_disease_index,
)
from app.models.patient import PatientIntake  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRecord:
    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=None):
        return self._d.get(k, default)


class _FakeAsyncResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        return _FakeAsyncResult._Iter(self._rows)

    class _Iter:
        def __init__(self, rows):
            self._it = iter(rows)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration


class _FakeSession:
    def __init__(self, query_handler):
        self._handler = query_handler

    async def run(self, query, **kwargs):
        rows = self._handler(query, kwargs)
        return _FakeAsyncResult(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    """Test double AsyncDriver. Accepts one query handler that produces
    rows; every session() call uses the same handler. Session count
    observable for cache tests."""

    def __init__(self, query_handler):
        self._handler = query_handler
        self.session_count = 0

    def session(self):
        self.session_count += 1
        return _FakeSession(self._handler)


def _intake(
    *,
    symptoms: list[str] | None = None,
    labs: dict[str, float] | None = None,
    age: int = 50,
    sex: str = "male",
) -> PatientIntake:
    return PatientIntake(
        symptoms=symptoms or ["polyuria"],
        age=age,
        sex=sex,
        history=[],
        medications=[],
        labs=labs,
        free_text="",
    )


def _edge(phen_id, phen_name, rel_type="disease_phenotype_positive"):
    return {
        "phenotype_id": phen_id,
        "phenotype_name": phen_name,
        "rel_type": rel_type,
        "rel_id": f"rel-{phen_id}",
    }


def _row(disease_id, name, overlap, edges):
    return _FakeRecord({
        "disease_id": disease_id,
        "disease_name": name,
        "overlap_count": overlap,
        "matched_edges": edges,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a clean retrieval cache."""
    retrieval._clear_intersection_cache()
    reset_disease_index()
    yield
    retrieval._clear_intersection_cache()
    reset_disease_index()


@pytest.fixture
def empty_rules(monkeypatch):
    """By default, run retrieval with no clinical rules so graph behaviour
    is testable in isolation. Individual tests can override this fixture."""
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: [])
    yield


# ---------------------------------------------------------------------------
# _apply_rule_boosts — pure function test
# ---------------------------------------------------------------------------


def test_apply_rule_boosts_amplifies_matching_candidate():
    candidates = [
        Candidate(
            disease_id="d1",
            disease_name="Type 2 Diabetes Mellitus",
            overlap_count=3,
            score=3.0,
        ),
        Candidate(
            disease_id="d2",
            disease_name="Pneumonia",
            overlap_count=2,
            score=2.0,
        ),
    ]
    boosts = [
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="r1",
            rule_label="glucose rule",
            rationale="high glucose",
        )
    ]
    unmatched = _apply_rule_boosts(candidates, boosts)

    assert candidates[0].score == pytest.approx(7.5)
    assert len(candidates[0].rule_boosts) == 1
    assert candidates[1].score == pytest.approx(2.0)  # untouched
    assert unmatched == {}


def test_apply_rule_boosts_unmatched_returns_for_fallback():
    candidates = [
        Candidate(
            disease_id="d1",
            disease_name="Pneumonia",
            overlap_count=2,
            score=2.0,
        )
    ]
    boosts = [
        RuleBoost(
            disease_name="Heart Failure",
            multiplier=2.5,
            rule_id="r1",
            rule_label="bnp rule",
            rationale="high bnp",
        )
    ]
    unmatched = _apply_rule_boosts(candidates, boosts)

    assert candidates[0].score == 2.0  # untouched
    assert "heart failure" in unmatched
    assert len(unmatched["heart failure"]) == 1


def test_apply_rule_boosts_case_insensitive_name_matching():
    candidates = [
        Candidate(
            disease_id="d1",
            disease_name="type 2 diabetes mellitus",  # lower
            overlap_count=3,
            score=3.0,
        )
    ]
    boosts = [
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",  # title case
            multiplier=2.5,
            rule_id="r1",
            rule_label="",
            rationale="",
        )
    ]
    _apply_rule_boosts(candidates, boosts)
    assert candidates[0].score == pytest.approx(7.5)


def test_apply_rule_boosts_multiple_boosts_compound():
    candidates = [
        Candidate(
            disease_id="d1",
            disease_name="Type 2 Diabetes Mellitus",
            overlap_count=2,
            score=2.0,
        )
    ]
    boosts = [
        RuleBoost("Type 2 Diabetes Mellitus", 2.5, "r1", "glucose", ""),
        RuleBoost("Type 2 Diabetes Mellitus", 2.5, "r2", "hba1c", ""),
    ]
    _apply_rule_boosts(candidates, boosts)
    # 2.0 * 2.5 * 2.5 = 12.5
    assert candidates[0].score == pytest.approx(12.5)
    assert len(candidates[0].rule_boosts) == 2


# ---------------------------------------------------------------------------
# retrieve_candidates — integration with fake driver (no rules)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_graph_only_returns_sorted_candidates(empty_rules):
    rows = [
        _row(
            "d1",
            "Type 2 Diabetes Mellitus",
            overlap=4,
            edges=[
                _edge("p1", "Polyuria"),
                _edge("p2", "Polydipsia"),
                _edge("p3", "Fatigue"),
                _edge("p4", "Blurred vision"),
            ],
        ),
        _row(
            "d2",
            "Wolfram Syndrome",
            overlap=2,
            edges=[_edge("p1", "Polyuria"), _edge("p2", "Polydipsia")],
        ),
    ]
    driver = _FakeDriver(lambda q, kw: rows)

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1", "p2", "p3", "p4"],
        neo4j_driver=driver,
    )

    assert len(cands) == 2
    assert cands[0].disease_name == "Type 2 Diabetes Mellitus"
    assert cands[0].overlap_count == 4
    assert cands[0].score == 4.0
    assert cands[0].source == "graph"
    assert len(cands[0].matched_edges) == 4
    assert all(isinstance(e, MatchedEdge) for e in cands[0].matched_edges)

    assert cands[1].disease_name == "Wolfram Syndrome"
    assert cands[1].overlap_count == 2


@pytest.mark.asyncio
async def test_retrieve_empty_phenotype_list_raises_when_no_rules(empty_rules):
    driver = _FakeDriver(lambda q, kw: [])
    with pytest.raises(RetrievalError):
        await retrieve_candidates(
            intake=_intake(),
            phenotype_ids=[],
            neo4j_driver=driver,
        )


@pytest.mark.asyncio
async def test_retrieve_uses_lru_cache(empty_rules):
    rows = [_row("d1", "Pneumonia", overlap=3, edges=[_edge("p1", "Fever")])]
    driver = _FakeDriver(lambda q, kw: rows)

    await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1", "p2"],
        neo4j_driver=driver,
    )
    await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p2", "p1"],  # same set, different order
        neo4j_driver=driver,
    )
    await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1", "p2"],
        neo4j_driver=driver,
    )

    assert driver.session_count == 1, (
        "LRU cache should collapse repeat queries; only first hit Neo4j"
    )


# ---------------------------------------------------------------------------
# retrieve_candidates — with rule boosts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t2dm_case_promoted_by_rule_boosts(monkeypatch):
    """The headline case. Graph returns T2DM with overlap=4 and a rare
    disease with overlap=5, but the lab rules fire on T2DM and amplify
    its score so T2DM ends up ranked first."""
    rows = [
        _row(
            "d_rare",
            "Wolfram Syndrome",
            overlap=5,  # raw overlap is higher
            edges=[_edge("p1", "Polyuria"), _edge("p2", "Polydipsia")],
        ),
        _row(
            "d_t2dm",
            "Type 2 Diabetes Mellitus",
            overlap=4,
            edges=[
                _edge("p1", "Polyuria"),
                _edge("p2", "Polydipsia"),
                _edge("p3", "Fatigue"),
                _edge("p4", "Blurred vision"),
            ],
        ),
    ]
    driver = _FakeDriver(lambda q, kw: rows)

    fake_boosts = [
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="hyperglycemia_diabetes",
            rule_label="Hyperglycemia",
            rationale="glucose > 200",
        ),
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="elevated_hba1c_diabetes",
            rule_label="HbA1c",
            rationale="hba1c > 6.5",
        ),
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    cands = await retrieve_candidates(
        intake=_intake(labs={"glucose": 287, "hba1c": 9.2}),
        phenotype_ids=["p1", "p2", "p3", "p4"],
        neo4j_driver=driver,
    )

    # T2DM score = 4 * 2.5 * 2.5 = 25. Wolfram score = 5. T2DM should rank first.
    assert cands[0].disease_name == "Type 2 Diabetes Mellitus"
    assert cands[0].score == pytest.approx(25.0)
    assert len(cands[0].rule_boosts) == 2
    assert cands[1].disease_name == "Wolfram Syndrome"
    assert cands[1].score == 5.0


@pytest.mark.asyncio
async def test_graph_path_attribution_preserved_per_candidate(empty_rules):
    """Per-candidate matched_edges must survive the whole pipeline so the
    context builder can serialize them with provenance. This is the
    explicit fix for the T2DM 'graph_path is empty' bug."""
    rows = [
        _row(
            "d1",
            "T2DM",
            overlap=3,
            edges=[
                _edge("p_a", "Polyuria"),
                _edge("p_b", "Polydipsia"),
                _edge("p_c", "Fatigue"),
            ],
        ),
        _row(
            "d2",
            "Hypothyroidism",
            overlap=1,
            edges=[_edge("p_c", "Fatigue")],
        ),
    ]
    driver = _FakeDriver(lambda q, kw: rows)

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p_a", "p_b", "p_c"],
        neo4j_driver=driver,
        min_overlap=1,
    )

    assert cands[0].disease_name == "T2DM"
    assert [e.phenotype_name for e in cands[0].matched_edges] == [
        "Polyuria",
        "Polydipsia",
        "Fatigue",
    ]
    # Second candidate's edges must NOT be contaminated with the first
    # candidate's phenotype matches.
    assert [e.phenotype_name for e in cands[1].matched_edges] == ["Fatigue"]


# ---------------------------------------------------------------------------
# Fallback seeding from rules when graph pool is too thin
# ---------------------------------------------------------------------------


class _FakeDiseaseIndex:
    """A stand-in DiseaseIndex for rule-seeding tests.

    The mapping is `{display_name: element_id}`. Lookups are
    case-insensitive on the display name, matching the real
    DiseaseIndex.find_by_name contract.
    """

    def __init__(self, mapping: dict[str, str]):
        self._records: dict[str, DiseaseRecord] = {}
        for display_name, eid in mapping.items():
            rec = DiseaseRecord(
                element_id=eid,
                name=display_name,
                name_lower=display_name.lower(),
                tokens=frozenset(),
            )
            self._records[display_name.lower()] = rec

    async def find_by_name(self, driver, name):
        return self._records.get(name.lower())


@pytest.mark.asyncio
async def test_rule_fallback_seeds_when_graph_pool_is_small(monkeypatch):
    """If the graph query returns only 1 candidate and the patient's labs
    fire a rule for a disease that isn't in the graph result, the rule
    seed should be injected as a rule-only fallback candidate."""
    # Graph returns 1 candidate only
    rows = [
        _row(
            "d1",
            "Polydipsia-related condition",
            overlap=2,
            edges=[_edge("p1", "Polydipsia")],
        )
    ]
    driver = _FakeDriver(lambda q, kw: rows)

    # Rule fires for Type 2 Diabetes Mellitus, which is NOT in the graph rows
    fake_boosts = [
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="hyperglycemia_diabetes",
            rule_label="Hyperglycemia",
            rationale="glucose > 200",
        )
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    # Stub the disease index so the fallback lookup succeeds
    fake_idx = _FakeDiseaseIndex({"Type 2 Diabetes Mellitus": "d_t2dm"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(labs={"glucose": 287}),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
        fallback_min=3,  # force fallback
    )

    graph_sources = [c for c in cands if c.source == "graph"]
    rule_sources = [c for c in cands if c.source == "clinical_rule"]
    assert len(graph_sources) == 1
    assert len(rule_sources) == 1
    assert rule_sources[0].disease_name == "Type 2 Diabetes Mellitus"
    assert rule_sources[0].matched_edges == []  # no graph evidence
    assert len(rule_sources[0].rule_boosts) == 1


@pytest.mark.asyncio
async def test_rule_fallback_suppressed_when_pool_is_big_enough(monkeypatch):
    """If the graph already has >= fallback_min candidates, unmatched
    rule boosts must NOT create rule-only seeds (no 'invented' diagnoses)."""
    rows = [
        _row("d1", "D1", overlap=3, edges=[_edge("p1", "X")]),
        _row("d2", "D2", overlap=2, edges=[_edge("p1", "X")]),
        _row("d3", "D3", overlap=2, edges=[_edge("p1", "X")]),
    ]
    driver = _FakeDriver(lambda q, kw: rows)

    fake_boosts = [
        RuleBoost(
            disease_name="Completely Different Disease",
            multiplier=3.0,
            rule_id="r1",
            rule_label="",
            rationale="",
        )
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    # The disease index would return a record if asked, but we shouldn't ask
    class _ShouldNotBeCalled:
        async def find_by_name(self, d, n):
            raise AssertionError("fallback seeding should not fire")

    monkeypatch.setattr(retrieval, "get_disease_index", lambda: _ShouldNotBeCalled())

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
        fallback_min=3,
    )

    assert len(cands) == 3
    assert all(c.source == "graph" for c in cands)


@pytest.mark.asyncio
async def test_rule_fallback_skips_diseases_not_in_graph(monkeypatch):
    """Rules can reference diseases not in the graph (PrimeKG subset may
    omit them). Those rule seeds must be silently dropped rather than
    fabricated as fake candidates."""
    rows: list[_FakeRecord] = []
    driver = _FakeDriver(lambda q, kw: rows)

    fake_boosts = [
        RuleBoost(
            disease_name="Not In Graph",
            multiplier=2.0,
            rule_id="r1",
            rule_label="",
            rationale="",
        ),
        RuleBoost(
            disease_name="Also In Graph",
            multiplier=2.0,
            rule_id="r2",
            rule_label="",
            rationale="",
        ),
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    # Only one of the two disease names is in the index
    fake_idx = _FakeDiseaseIndex({"Also In Graph": "d_also"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
        fallback_min=3,
    )

    names = {c.disease_name for c in cands}
    assert "Also In Graph" in names
    assert "Not In Graph" not in names
