"""Shared DiseaseIndex — in-process cache of Neo4j Disease nodes.

Problem this module exists to solve
-----------------------------------

Two different layers of the pipeline need a snapshot of all diseases in
the graph:

1. `guardrails/output_validator.py` — the hallucination gate, which
   compares LLM-returned disease names against the graph to mark them
   verified or not.
2. `core/retrieval.py` — the new retrieval layer, which needs to
   resolve rule-based boost names ("Type 2 Diabetes Mellitus") back to
   Neo4j element IDs so the graph subgraph expansion can include them.

Before this module existed, the hallucination gate cached its own
`(name, token_set)` list with a 5-minute TTL inside output_validator.py.
Bolting a second duplicate cache onto retrieval.py would create two
independent TTLs drifting against each other, a textbook way to ship
a "sometimes the gate knows about a disease but retrieval doesn't"
race condition.

One singleton, loaded lazily at startup, refreshed on a shared TTL,
consumed by both layers.

Thread-safety note
------------------

We use an asyncio.Lock around the load path so concurrent requests
don't trigger multiple Neo4j fetches during the first miss. All
reads are lock-free (the cache is replaced atomically on refresh).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = structlog.get_logger()


# Stopwords match the set used by the hallucination gate — keep them in
# sync or Jaccard matching drifts between the two layers.
_MATCH_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "in", "on", "with", "to", "for",
    "by", "at", "from", "as", "is", "be", "type", "syndrome", "disease",
    "disorder", "condition",
})


def _meaningful_tokens(name: str) -> frozenset[str]:
    """Strip stopwords + tokenize for fuzzy disease matching."""
    raw = re.findall(r"[a-zA-Z0-9]+", name.lower())
    return frozenset(t for t in raw if t not in _MATCH_STOPWORDS and len(t) > 1)


# Default refresh interval (seconds). 5 minutes is the same as the old
# inline cache — the graph is read-only in production so this is plenty.
DEFAULT_TTL = 300.0


@dataclass(frozen=True)
class DiseaseRecord:
    """One disease node as it appears in the shared index."""

    element_id: str       # Neo4j elementId — used by the retrieval layer
    name: str             # canonical Neo4j name field
    name_lower: str       # pre-lowered for O(1) case-insensitive lookup
    tokens: frozenset[str]  # meaningful tokens for Jaccard matching


class DiseaseIndex:
    """Async singleton cache of Neo4j Disease nodes.

    Access pattern:

        idx = get_disease_index()
        records = await idx.all(driver)                    # cached list
        record = await idx.find_by_name(driver, "Type 2 Diabetes Mellitus")
        records = await idx.find_by_names(driver, ["Sepsis", "Septic Shock"])

    The cache is built lazily on the first `all()` call and refreshed
    whenever TTL expires. Tests can call `reset()` to force a reload.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._records: list[DiseaseRecord] = []
        self._by_name_lower: dict[str, DiseaseRecord] = {}
        self._loaded_at: float = 0.0

    # -----------------------------------------------------------------
    # Loading
    # -----------------------------------------------------------------

    async def _load(self, driver: AsyncDriver) -> None:
        """Fetch all Disease nodes from Neo4j and rebuild the caches."""
        logger.info("disease_index_loading")
        start = time.monotonic()
        records: list[DiseaseRecord] = []
        by_name_lower: dict[str, DiseaseRecord] = {}

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Disease)
                WHERE d.name IS NOT NULL
                RETURN elementId(d) AS id, d.name AS name
                """
            )
            async for record in result:
                name = record.get("name")
                if not name:
                    continue
                name_lower = name.lower()
                tokens = _meaningful_tokens(name)
                rec = DiseaseRecord(
                    element_id=record["id"],
                    name=name,
                    name_lower=name_lower,
                    tokens=tokens,
                )
                records.append(rec)
                # Note: if two diseases share a lowered name, last wins.
                # This is intentional and matches the old fuzzy behaviour.
                by_name_lower[name_lower] = rec

        self._records = records
        self._by_name_lower = by_name_lower
        self._loaded_at = time.monotonic()
        elapsed_ms = round((self._loaded_at - start) * 1000)
        logger.info(
            "disease_index_loaded", count=len(records), elapsed_ms=elapsed_ms
        )

    async def _ensure_loaded(self, driver: AsyncDriver) -> None:
        """Load on first use or when TTL has expired."""
        now = time.monotonic()
        if self._records and (now - self._loaded_at) < self._ttl:
            return
        async with self._lock:
            # Double-check after acquiring the lock
            now = time.monotonic()
            if self._records and (now - self._loaded_at) < self._ttl:
                return
            await self._load(driver)

    # -----------------------------------------------------------------
    # Read API
    # -----------------------------------------------------------------

    async def all(self, driver: AsyncDriver) -> list[DiseaseRecord]:
        """Return all diseases in the index."""
        await self._ensure_loaded(driver)
        return self._records

    async def find_by_name(
        self, driver: AsyncDriver, name: str
    ) -> DiseaseRecord | None:
        """Exact-name lookup (case-insensitive)."""
        await self._ensure_loaded(driver)
        return self._by_name_lower.get(name.lower())

    async def find_by_names(
        self,
        driver: AsyncDriver,
        names: list[str],
    ) -> list[DiseaseRecord]:
        """Bulk exact-name lookup. Returns records for each name that
        matches; names with no match are silently dropped.
        """
        await self._ensure_loaded(driver)
        hits: list[DiseaseRecord] = []
        for n in names:
            rec = self._by_name_lower.get(n.lower())
            if rec is not None:
                hits.append(rec)
        return hits

    async def preload(self, driver: AsyncDriver) -> None:
        """Eagerly warm the cache at app startup."""
        try:
            await self._ensure_loaded(driver)
        except Exception as exc:  # noqa: BLE001
            logger.warning("disease_index_preload_failed", error=str(exc))

    def reset(self) -> None:
        """Test hook — clear all state so the next call reloads."""
        self._records = []
        self._by_name_lower = {}
        self._loaded_at = 0.0


# Module-level singleton
_instance: DiseaseIndex | None = None


def get_disease_index() -> DiseaseIndex:
    """Return (or create) the process-wide DiseaseIndex singleton."""
    global _instance
    if _instance is None:
        _instance = DiseaseIndex()
    return _instance


def reset_disease_index() -> None:
    """Test hook — drop the singleton entirely."""
    global _instance
    _instance = None
