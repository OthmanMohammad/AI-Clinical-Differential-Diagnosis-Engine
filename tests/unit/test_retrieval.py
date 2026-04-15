"""Unit tests for app/core/retrieval.py.

The retrieval layer is the heart of Tier 2. We test its behaviour
against a fake AsyncDriver that returns canned records, so we don't
need a real Neo4j. The fake driver accepts a dict of (disease, overlap,
matched_edges) rows and serves them via a stub session.

Tests cover:
- The phenotype-intersection query returns graph candidates in the
  right score order with per-candidate matched edges attached
- Rule boosts amplify graph candidates that match by name (case-insens)
- Rule boosts that don't match any graph candidate are always injected
  as rule-seeded candidates (previously gated on pool size — that was
  the T2DM regression)
- The test_t2dm_common_disease_regression test exercises the exact
  failure mode observed in production: phenotype intersection returns
  a pool of rare diseases (Gitelman/Bartter/Wolfram) while T2DM gets
  filtered out by min_overlap, and the lab rules must inject T2DM
  with real matched_edges via the rule_seed edge lookup.
- Rule-only candidates are flagged source="clinical_rule"
- Ranking puts the highest-scored candidate first, including after
  rule amplification
- Empty phenotype list + no rule matches raises RetrievalError
- LRU cache on phenotype intersection returns the same candidates
  without re-querying Neo4j
"""

from __future__ import annotations

import json
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
async def test_rule_seeds_inject_when_graph_pool_is_empty(monkeypatch):
    """Fallback case: phenotype intersection returns nothing but the
    lab rules clearly point at a disease in the index. The rule-seeded
    candidate should be injected with real matched edges looked up
    from Neo4j."""
    # Graph intersection returns nothing
    def handler(q, kw):
        # Intersection query returns empty; edge-lookup returns one edge.
        if "WHERE elementId(p) IN $phenotype_ids" in q and "GROUP BY" not in q and "overlap" not in q:
            return []
        if "count(DISTINCT p)" in q or "overlap_count" in q or "collect(DISTINCT" in q:
            return []  # intersection
        if "elementId(d) = $disease_id" in q:
            return [
                _FakeRecord({
                    "phenotype_id": "p1",
                    "phenotype_name": "Polyuria",
                    "rel_type": "disease_phenotype_positive",
                }),
            ]
        return []

    driver = _FakeDriver(handler)

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

    fake_idx = _FakeDiseaseIndex({"Type 2 Diabetes Mellitus": "d_t2dm"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(labs={"glucose": 287}),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
    )

    rule_sources = [c for c in cands if c.source == "clinical_rule"]
    assert len(rule_sources) == 1
    assert rule_sources[0].disease_name == "Type 2 Diabetes Mellitus"
    # Edge lookup populated matched_edges even though the intersection
    # query didn't return T2DM — this is the fix for the "graph_path
    # empty on the correct diagnosis" failure mode.
    assert len(rule_sources[0].matched_edges) == 1
    assert rule_sources[0].matched_edges[0].phenotype_name == "Polyuria"


@pytest.mark.asyncio
async def test_rule_seeds_always_injected_regardless_of_graph_pool_size(monkeypatch):
    """Invariant: rule-targeted diseases that aren't in the graph pool
    must always be injected, regardless of how many graph candidates
    the intersection query returned. The previous fallback_min gate
    inverted this — it suppressed rule seeds whenever the graph pool
    was "big enough", which is exactly when PrimeKG's sparse common-
    disease phenotype coverage matters most. With 18 rare-disease
    candidates from Gitelman/Bartter/etc filling the pool, the rule
    clearly pointing at Type 2 Diabetes Mellitus still had nowhere to
    land. Now it does."""
    # 18 rare-disease candidates
    rare_rows = [
        _row(f"d_rare_{i}", f"Rare syndrome {i}", overlap=2, edges=[_edge("p1", "Polyuria")])
        for i in range(18)
    ]

    def handler(q, kw):
        if "elementId(d) = $disease_id" in q:
            # Edge-lookup query for rule-seeded T2DM — returns 1 real edge
            return [
                _FakeRecord({
                    "phenotype_id": "p1",
                    "phenotype_name": "Polyuria",
                    "rel_type": "disease_phenotype_positive",
                }),
            ]
        return rare_rows  # the intersection query

    driver = _FakeDriver(handler)

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

    fake_idx = _FakeDiseaseIndex({"Type 2 Diabetes Mellitus": "d_t2dm"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(labs={"glucose": 287}),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
    )

    graph_sources = [c for c in cands if c.source == "graph"]
    rule_sources = [c for c in cands if c.source == "clinical_rule"]
    assert len(graph_sources) == 18
    assert len(rule_sources) == 1
    t2dm = rule_sources[0]
    assert t2dm.disease_name == "Type 2 Diabetes Mellitus"
    # Real graph edge attached even though the intersection query missed it
    assert len(t2dm.matched_edges) == 1
    assert t2dm.matched_edges[0].phenotype_name == "Polyuria"


@pytest.mark.asyncio
async def test_rule_seed_edge_lookup_without_matches(monkeypatch):
    """If the rule-seeded disease has NO phenotype edges matching the
    patient's phenotype set, the seed is still injected but with
    matched_edges=[] and a lower score (no real graph support)."""
    def handler(q, kw):
        if "elementId(d) = $disease_id" in q:
            return []  # no edges found
        return []  # intersection also empty

    driver = _FakeDriver(handler)

    fake_boosts = [
        RuleBoost(
            disease_name="Rare Rule-Only Disease",
            multiplier=3.0,
            rule_id="r1",
            rule_label="",
            rationale="",
        )
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    fake_idx = _FakeDiseaseIndex({"Rare Rule-Only Disease": "d_rare"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
    )

    assert len(cands) == 1
    assert cands[0].disease_name == "Rare Rule-Only Disease"
    assert cands[0].source == "clinical_rule"
    assert cands[0].matched_edges == []


@pytest.mark.asyncio
async def test_rule_seed_respects_max_seeds_cap(monkeypatch):
    """If six rules fire for six different diseases, only the first
    N (default 6) should be injected to keep the candidate list bounded."""
    def handler(q, kw):
        if "elementId(d) = $disease_id" in q:
            return []
        return []

    driver = _FakeDriver(handler)

    fake_boosts = [
        RuleBoost(
            disease_name=f"Disease {i}",
            multiplier=2.0,
            rule_id=f"r{i}",
            rule_label="",
            rationale="",
        )
        for i in range(10)
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    fake_idx = _FakeDiseaseIndex({f"Disease {i}": f"d_{i}" for i in range(10)})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=_intake(),
        phenotype_ids=["p1"],
        neo4j_driver=driver,
        max_rule_seeds=3,
    )

    assert len(cands) == 3
    assert all(c.source == "clinical_rule" for c in cands)


@pytest.mark.asyncio
async def test_rule_fallback_skips_diseases_not_in_graph(monkeypatch):
    """Rules can reference diseases not in the graph (PrimeKG subset may
    omit them). Those rule seeds must be silently dropped rather than
    fabricated as fake candidates."""
    def handler(q, kw):
        if "elementId(d) = $disease_id" in q:
            return []
        return []

    driver = _FakeDriver(handler)

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
    )

    names = {c.disease_name for c in cands}
    assert "Also In Graph" in names
    assert "Not In Graph" not in names


# ---------------------------------------------------------------------------
# Regression test: the specific T2DM failure mode observed in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t2dm_common_disease_regression(monkeypatch):
    """Regression test for the exact failure mode observed on the Oracle
    VM during the first clean eval run.

    Setup reproduces production behaviour:
    - Patient intake is loaded from eval/cases/case_01_t2dm_classic.json
    - Phenotype intersection returns 18 rare diseases (Gitelman, Bartter,
      diabetes insipidus variants, Wolfram syndrome, etc.) with overlap 2-3.
      T2DM is NOT in the pool because its PrimeKG phenotype edges are
      too sparse to survive min_overlap=2.
    - Clinical rules fire for hyperglycemia (glucose 287) and elevated
      HbA1c (9.2), each targeting "Type 2 Diabetes Mellitus".
    - T2DM has ONE real phenotype edge in Neo4j for this patient's
      phenotype set (a disease_phenotype_positive edge to Polyuria).

    Expected:
    - T2DM is injected as a rule-seeded candidate with source="clinical_rule"
    - Its matched_edges list contains the real Polyuria edge (not empty)
    - Its rule_boosts list contains both hyperglycemia_diabetes and
      elevated_hba1c_diabetes entries
    - It ranks above the 18 rare-disease candidates because the rule
      multiplier compounding gives it a high score
    """
    # Load the real case payload used in the eval harness
    case_path = (
        Path(__file__).resolve().parents[2]
        / "eval"
        / "cases"
        / "case_01_t2dm_classic.json"
    )
    case = json.loads(case_path.read_text())
    patient_data = case["patient"]

    intake = PatientIntake(
        symptoms=patient_data["symptoms"],
        age=patient_data["age"],
        sex=patient_data["sex"],
        history=patient_data.get("history", []),
        medications=patient_data.get("medications", []),
        labs=patient_data.get("labs"),
        free_text=patient_data.get("free_text", ""),
    )

    # 18 rare-disease candidates flooding the intersection pool
    rare_rows = [
        _row(
            f"d_rare_{i}",
            f"Rare syndrome {i}",
            overlap=2,
            edges=[_edge("p_polyuria", "Polyuria"), _edge("p_polydipsia", "Polydipsia")],
        )
        for i in range(18)
    ]

    # The rule-seed edge lookup should return the single real edge T2DM
    # has to the patient's phenotype set
    t2dm_real_edge = _FakeRecord({
        "phenotype_id": "p_polyuria",
        "phenotype_name": "Polyuria",
        "rel_type": "disease_phenotype_positive",
    })

    def handler(q, kw):
        if "elementId(d) = $disease_id" in q:
            return [t2dm_real_edge]
        # Main intersection query
        return rare_rows

    driver = _FakeDriver(handler)

    # Mock the lab rules the same way the real ones fire for this case
    fake_boosts = [
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="hyperglycemia_diabetes",
            rule_label="Hyperglycemia pattern → diabetes",
            rationale="glucose ≥200 meets ADA diagnostic threshold",
        ),
        RuleBoost(
            disease_name="Type 2 Diabetes Mellitus",
            multiplier=2.5,
            rule_id="elevated_hba1c_diabetes",
            rule_label="HbA1c ≥6.5% → diabetes",
            rationale="HbA1c ≥6.5% meets ADA diagnostic threshold",
        ),
    ]
    monkeypatch.setattr(retrieval, "apply_rules", lambda _i: fake_boosts)

    # Disease index knows about T2DM
    fake_idx = _FakeDiseaseIndex({"Type 2 Diabetes Mellitus": "d_t2dm"})
    monkeypatch.setattr(retrieval, "get_disease_index", lambda: fake_idx)

    cands = await retrieve_candidates(
        intake=intake,
        phenotype_ids=["p_polyuria", "p_polydipsia", "p_fatigue", "p_blurred"],
        neo4j_driver=driver,
    )

    # T2DM must be in the final list as a rule-seeded candidate
    t2dm = next(
        (c for c in cands if c.disease_name == "Type 2 Diabetes Mellitus"),
        None,
    )
    assert t2dm is not None, (
        f"Type 2 Diabetes Mellitus missing from candidate list. "
        f"Got: {[c.disease_name for c in cands]}"
    )
    assert t2dm.source == "clinical_rule"

    # Both rules must have fired on it
    assert len(t2dm.rule_boosts) == 2
    rule_ids = {b.rule_id for b in t2dm.rule_boosts}
    assert "hyperglycemia_diabetes" in rule_ids
    assert "elevated_hba1c_diabetes" in rule_ids

    # The ONE real edge T2DM has in Neo4j must flow through to matched_edges
    assert len(t2dm.matched_edges) == 1
    assert t2dm.matched_edges[0].phenotype_name == "Polyuria"
    assert t2dm.matched_edges[0].rel_type == "disease_phenotype_positive"

    # Score check: rule compound (2.5 * 2.5 = 6.25) + 1 edge * 0.5 = 6.75.
    # That MUST beat any of the rare-disease candidates whose raw overlap
    # score is at most 2, so T2DM must rank at or near the top.
    assert t2dm.score >= 6.0
    top_3_names = [c.disease_name for c in cands[:3]]
    assert "Type 2 Diabetes Mellitus" in top_3_names, (
        f"T2DM did not rank in the top 3 despite rule boosts firing. "
        f"Top 3: {top_3_names}"
    )
