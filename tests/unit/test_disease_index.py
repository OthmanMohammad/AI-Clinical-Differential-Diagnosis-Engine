"""Unit tests for app/services/disease_index.py.

Uses a fake AsyncDriver to test caching behaviour without needing a
running Neo4j. Validates:
- Lazy loading on first call
- TTL-based refresh
- Lock prevents concurrent double-loads
- find_by_name / find_by_names exact-name lookup
- Tokenization matches output_validator's expectations
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.services.disease_index import (  # noqa: E402
    DiseaseIndex,
    DiseaseRecord,
    _meaningful_tokens,
    get_disease_index,
    reset_disease_index,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRecord:
    def __init__(self, eid: str, name: str):
        self._data = {"id": eid, "name": name}

    def __getitem__(self, k):
        return self._data[k]

    def get(self, k, default=None):
        return self._data.get(k, default)


class _FakeAsyncResult:
    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        return _FakeAsyncResult._Iter(self._records)

    class _Iter:
        def __init__(self, records):
            self._it = iter(records)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration


class _FakeSession:
    def __init__(self, records):
        self._records = records
        self.run_count = 0

    async def run(self, query, **kwargs):
        self.run_count += 1
        return _FakeAsyncResult(self._records)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def __init__(self, records):
        self._records = records
        self.session_count = 0
        self.last_session: _FakeSession | None = None

    def session(self):
        self.session_count += 1
        self.last_session = _FakeSession(self._records)
        return self.last_session


def _fake_records():
    return [
        _FakeRecord("e1", "Type 2 Diabetes Mellitus"),
        _FakeRecord("e2", "Pulmonary Embolism"),
        _FakeRecord("e3", "Acute Myocardial Infarction"),
        _FakeRecord("e4", "Iron Deficiency Anemia"),
    ]


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def test_meaningful_tokens_matches_output_validator_behaviour():
    tokens = _meaningful_tokens("Type 2 Diabetes Mellitus")
    # Lower-cased, stopword-stripped ("type" is a stopword here, same as
    # the old output_validator logic).
    assert "2" not in tokens  # Single-char filter drops it (matches old behavior)
    assert "diabetes" in tokens
    assert "mellitus" in tokens


# ---------------------------------------------------------------------------
# Loading + caching
# ---------------------------------------------------------------------------


@pytest.fixture
def idx():
    return DiseaseIndex(ttl_seconds=60)


@pytest.fixture
def fake_driver():
    return _FakeDriver(_fake_records())


@pytest.mark.asyncio
async def test_all_loads_on_first_call(idx, fake_driver):
    recs = await idx.all(fake_driver)
    assert len(recs) == 4
    assert all(isinstance(r, DiseaseRecord) for r in recs)
    assert fake_driver.session_count == 1


@pytest.mark.asyncio
async def test_all_uses_cache_on_second_call(idx, fake_driver):
    await idx.all(fake_driver)
    await idx.all(fake_driver)
    await idx.all(fake_driver)
    assert fake_driver.session_count == 1  # still only one Neo4j call


@pytest.mark.asyncio
async def test_find_by_name_case_insensitive(idx, fake_driver):
    rec = await idx.find_by_name(fake_driver, "type 2 diabetes mellitus")
    assert rec is not None
    assert rec.name == "Type 2 Diabetes Mellitus"
    assert rec.element_id == "e1"


@pytest.mark.asyncio
async def test_find_by_name_returns_none_for_unknown(idx, fake_driver):
    assert await idx.find_by_name(fake_driver, "Wolfram Syndrome") is None


@pytest.mark.asyncio
async def test_find_by_names_bulk_lookup(idx, fake_driver):
    hits = await idx.find_by_names(
        fake_driver,
        ["Pulmonary Embolism", "Acute Myocardial Infarction", "Never Seen"],
    )
    assert len(hits) == 2
    assert {h.name for h in hits} == {"Pulmonary Embolism", "Acute Myocardial Infarction"}


@pytest.mark.asyncio
async def test_find_by_names_empty_list(idx, fake_driver):
    hits = await idx.find_by_names(fake_driver, [])
    assert hits == []


@pytest.mark.asyncio
async def test_reset_forces_reload(idx, fake_driver):
    await idx.all(fake_driver)
    assert fake_driver.session_count == 1
    idx.reset()
    await idx.all(fake_driver)
    assert fake_driver.session_count == 2


@pytest.mark.asyncio
async def test_ttl_expiry_triggers_reload():
    idx = DiseaseIndex(ttl_seconds=0.01)  # very short TTL
    driver = _FakeDriver(_fake_records())
    await idx.all(driver)
    assert driver.session_count == 1
    await asyncio.sleep(0.05)  # let TTL expire
    await idx.all(driver)
    assert driver.session_count == 2


@pytest.mark.asyncio
async def test_concurrent_loads_only_fire_neo4j_once(idx, fake_driver):
    """The internal lock must prevent a thundering herd."""
    async with asyncio.TaskGroup() as tg:
        for _ in range(10):
            tg.create_task(idx.all(fake_driver))
    assert fake_driver.session_count == 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_disease_index_returns_same_instance():
    reset_disease_index()
    a = get_disease_index()
    b = get_disease_index()
    assert a is b


def test_reset_disease_index_returns_new_instance():
    reset_disease_index()
    a = get_disease_index()
    reset_disease_index()
    b = get_disease_index()
    assert a is not b
