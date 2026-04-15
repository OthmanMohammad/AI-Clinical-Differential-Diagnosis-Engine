"""Layer 3 — Graph RAG retrieval (Tier 2 rewrite).

This module replaces the old "vector search → flat graph traversal" flow
with a structural retrieval pipeline that actually uses the knowledge
graph the way knowledge graphs are meant to be used.

Architecture
------------

    PatientIntake
         │
         ▼
┌─────────────────────────────────────────────────┐
│ 1. Phenotype extraction                         │
│    - medspaCy/entity_ruler NER on user text     │
│    - vector search on symptom names in Qdrant   │
│    - output: list of Phenotype element IDs      │
│      matched from the patient's symptoms        │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ 2. Phenotype intersection (Cypher)              │
│    MATCH (d:Disease)-[:disease_phenotype_*]->   │
│          (p:Phenotype)                          │
│    WHERE p ∈ patient_phenotypes                 │
│    GROUP BY d                                   │
│    ORDER BY count(DISTINCT p) DESC              │
│                                                 │
│    Output: [(disease_id, overlap_count,         │
│              matched_edges, name)]              │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ 3. Lab/demographic rule fusion                  │
│    - apply_rules(intake) → list of RuleBoosts   │
│    - multiply score of matching candidates      │
│    - if candidate pool < N, seed extra          │
│      candidates from rules (flagged             │
│      source='clinical_rule')                    │
└──────────────────────────┬──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│ 4. Final ranked Candidate list                  │
│    Each candidate carries its per-candidate     │
│    matched edges so the context builder can     │
│    serialize evidence per-diagnosis.            │
└─────────────────────────────────────────────────┘

Why this shape
--------------

The old pipeline's biggest failure mode was "diagnose T2DM with
empty graph_path because vector search seeded on Phenotype:polydipsia
and graph traversal flooded the LLM context with rare diseases that
also have polydipsia." The fix is twofold:

1. Structural retrieval — ask Neo4j which diseases have the MOST
   overlap with the patient's symptoms, not which diseases are
   reachable within 2 hops of an arbitrary seed.
2. Per-candidate evidence attribution — return the matched edges
   alongside each candidate so the prompt can say "Diagnosis X matches
   symptoms a,b,c via edges e1,e2,e3" instead of dumping a flat
   subgraph and asking the LLM to figure it out.

Non-goals
---------

This module does NOT expand the graph further (no "1-hop outward from
top candidates"). That's the job of the subgraph_expand helper in
graph_traversal.py, which runs AFTER retrieval.py settles the ranked
candidate list. Keeping the two steps separate means retrieval.py is
purely a candidate-selection algorithm with a clean contract, and
graph_traversal.py is purely a context-enrichment step.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

import structlog

from app.core.lab_rules import RuleBoost, apply_rules
from app.observability.metrics import NEO4J_LATENCY
from app.services.disease_index import DiseaseRecord, get_disease_index

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from app.models.patient import PatientIntake

logger = structlog.get_logger()


# Minimum number of phenotype matches for a disease to qualify as a
# graph-sourced candidate. 2 catches the common case ("disease must share
# at least two of the patient's symptoms") while rejecting noise from
# singletons with incidental overlap.
DEFAULT_MIN_OVERLAP = 2

# Maximum number of graph-sourced candidates returned per query. The LLM
# context budget can't hold more than a few dozen — larger lists just
# get truncated downstream.
DEFAULT_CANDIDATE_LIMIT = 20

# Threshold below which we allow rule-based seeding to fire as a
# fallback. If the phenotype intersection returns fewer than this many
# candidates, rules can inject fresh seeds flagged as rule-only.
DEFAULT_FALLBACK_MIN = 3


@dataclass
class MatchedEdge:
    """One edge connecting a patient phenotype to a candidate disease."""

    phenotype_id: str
    phenotype_name: str
    rel_type: str      # e.g. "disease_phenotype_positive"


@dataclass
class Candidate:
    """One candidate disease in the ranked retrieval output.

    `matched_edges` is populated for graph-sourced candidates; it's
    empty for rule-only fallback candidates (those carry their
    evidence in `rule_boosts` instead).

    `score` is the final combined score after rule boosts have been
    applied. It's not normalized — the LLM context builder can use
    it for ordering and nothing else depends on it being in [0,1].
    """

    disease_id: str              # Neo4j elementId
    disease_name: str            # human-readable name
    overlap_count: int           # number of patient phenotypes matched
    score: float                 # combined final score
    matched_edges: list[MatchedEdge] = field(default_factory=list)
    rule_boosts: list[RuleBoost] = field(default_factory=list)
    source: str = "graph"        # "graph" | "clinical_rule"


class RetrievalError(Exception):
    """Raised when retrieval fails catastrophically (no phenotypes found,
    Neo4j error, etc). Caller should short-circuit the pipeline."""


# ---------------------------------------------------------------------------
# Phenotype intersection Cypher
# ---------------------------------------------------------------------------

# Returns one row per disease, with the list of matched edges nested
# inside. LIMIT is applied AFTER grouping so we don't materialise the
# full expansion.
#
# Notes:
#   * The relationship WHERE clause lives INSIDE the MATCH pattern
#     predicate (not a separate WHERE) so Neo4j uses the relationship
#     type index directly.
#   * We return `elementId(d)` and `elementId(r)` for later expansion.
#   * `overlap_count` is what we sort on — diseases sharing more of
#     the patient's symptoms rank first.
#   * This is one query, one session, bounded memory.
PHENOTYPE_INTERSECTION_QUERY = """
MATCH (d:Disease)-[r]->(p:Phenotype)
WHERE elementId(p) IN $phenotype_ids
  AND type(r) IN ['disease_phenotype_positive', 'disease_phenotype_negative']
WITH d,
     collect(DISTINCT {
       phenotype_id: elementId(p),
       phenotype_name: p.name,
       rel_type: type(r),
       rel_id: elementId(r)
     }) AS matched_edges,
     count(DISTINCT p) AS overlap
WHERE overlap >= $min_overlap
RETURN
  elementId(d) AS disease_id,
  d.name       AS disease_name,
  overlap      AS overlap_count,
  matched_edges
ORDER BY overlap DESC, d.name ASC
LIMIT $limit
"""


# ---------------------------------------------------------------------------
# Cache: phenotype set → query result
# ---------------------------------------------------------------------------
#
# Different patients with the same symptoms hit Neo4j with an identical
# intersection query. Cache by sorted tuple of phenotype IDs + parameters.
# The cache is small (LRU 256 entries) and in-process; if the PrimeKG
# data is re-ingested we restart the container which clears it.

@lru_cache(maxsize=256)
def _intersection_cache_key(
    phenotype_ids_sorted: tuple[str, ...],
    min_overlap: int,
    limit: int,
) -> tuple[str, ...]:
    return phenotype_ids_sorted  # only used for the cache key


_intersection_results: dict[
    tuple[tuple[str, ...], int, int], list[Candidate]
] = {}


def _clear_intersection_cache() -> None:
    """Test hook."""
    _intersection_cache_key.cache_clear()
    _intersection_results.clear()


# ---------------------------------------------------------------------------
# Graph-sourced candidates
# ---------------------------------------------------------------------------


async def _graph_candidates(
    phenotype_ids: list[str],
    neo4j_driver: AsyncDriver,
    min_overlap: int,
    limit: int,
) -> list[Candidate]:
    """Run the phenotype-intersection query and return ranked candidates.

    Cached by (sorted phenotype ID tuple, min_overlap, limit) so repeat
    queries from different patients with the same symptom set are free.
    """
    if not phenotype_ids:
        return []

    key = (tuple(sorted(phenotype_ids)), min_overlap, limit)
    cached = _intersection_results.get(key)
    if cached is not None:
        logger.debug("retrieval_cache_hit", candidates=len(cached))
        return [
            # Cache stores Candidate objects; copy them so callers can
            # freely mutate score/rule_boosts without polluting the cache.
            Candidate(
                disease_id=c.disease_id,
                disease_name=c.disease_name,
                overlap_count=c.overlap_count,
                score=c.score,
                matched_edges=list(c.matched_edges),
                rule_boosts=[],
                source=c.source,
            )
            for c in cached
        ]

    start = time.monotonic()
    candidates: list[Candidate] = []

    async with neo4j_driver.session() as session:
        result = await session.run(
            PHENOTYPE_INTERSECTION_QUERY,
            phenotype_ids=phenotype_ids,
            min_overlap=min_overlap,
            limit=limit,
        )
        async for record in result:
            edges_raw = record["matched_edges"] or []
            matched_edges = [
                MatchedEdge(
                    phenotype_id=e["phenotype_id"],
                    phenotype_name=e["phenotype_name"],
                    rel_type=e["rel_type"],
                )
                for e in edges_raw
            ]
            overlap = int(record["overlap_count"])
            candidates.append(
                Candidate(
                    disease_id=record["disease_id"],
                    disease_name=record["disease_name"],
                    overlap_count=overlap,
                    # Initial score is the overlap count. Rule boosts
                    # multiply this value.
                    score=float(overlap),
                    matched_edges=matched_edges,
                    source="graph",
                )
            )

    elapsed = time.monotonic() - start
    NEO4J_LATENCY.observe(elapsed)
    logger.info(
        "retrieval_graph_query",
        phenotypes=len(phenotype_ids),
        candidates=len(candidates),
        elapsed_ms=round(elapsed * 1000),
    )

    # Store a reference copy in the cache. Consumers mutate their own
    # copies via the return path above.
    _intersection_results[key] = [
        Candidate(
            disease_id=c.disease_id,
            disease_name=c.disease_name,
            overlap_count=c.overlap_count,
            score=c.score,
            matched_edges=list(c.matched_edges),
            rule_boosts=[],
            source=c.source,
        )
        for c in candidates
    ]
    # LRU bookkeeping
    _intersection_cache_key(key[0], key[1], key[2])

    return candidates


# ---------------------------------------------------------------------------
# Rule fusion
# ---------------------------------------------------------------------------


def _apply_rule_boosts(
    candidates: list[Candidate],
    rule_boosts: list[RuleBoost],
) -> dict[str, list[RuleBoost]]:
    """Apply score boosts from matched rules to existing candidates.

    Mutates `candidates` in place: for every candidate whose name matches
    a rule boost (case-insensitive), multiply `score` by the rule's
    multiplier and append the boost to `rule_boosts`.

    Returns a dict mapping lowercased disease name → list of boosts
    that did NOT land on any existing candidate. Those are the
    candidates for fallback seeding in `_seed_from_rules`.
    """
    by_name_lower: dict[str, Candidate] = {
        c.disease_name.lower(): c for c in candidates
    }

    unmatched: dict[str, list[RuleBoost]] = {}
    for boost in rule_boosts:
        target = by_name_lower.get(boost.disease_name.lower())
        if target is not None:
            target.score *= boost.multiplier
            target.rule_boosts.append(boost)
        else:
            unmatched.setdefault(boost.disease_name.lower(), []).append(boost)

    return unmatched


async def _seed_from_rules(
    unmatched_boosts: dict[str, list[RuleBoost]],
    neo4j_driver: AsyncDriver,
    existing_ids: set[str],
) -> list[Candidate]:
    """Fallback seeding: turn unmatched rule boosts into rule-only
    candidates, looking up each disease in the shared DiseaseIndex
    to get its element_id.

    Only called when the graph-sourced candidate pool is too small
    to form a useful differential. Any candidate produced here is
    flagged `source="clinical_rule"` so the LLM prompt can surface
    the distinction.
    """
    if not unmatched_boosts:
        return []

    idx = get_disease_index()
    seeds: list[Candidate] = []
    for name_lower, boosts in unmatched_boosts.items():
        # The boost stores the canonical name; look up the case-insensitive
        # match in the disease index.
        lookup_name = boosts[0].disease_name
        rec = await idx.find_by_name(neo4j_driver, lookup_name)
        if rec is None:
            logger.debug(
                "rule_seed_disease_not_in_graph",
                disease_name=lookup_name,
            )
            continue
        if rec.element_id in existing_ids:
            continue  # already covered by a graph candidate
        # Combine multiplier from all boosts for the same disease.
        combined = 1.0
        for b in boosts:
            combined *= b.multiplier
        seeds.append(
            Candidate(
                disease_id=rec.element_id,
                disease_name=rec.name,
                overlap_count=0,
                score=combined,
                matched_edges=[],
                rule_boosts=boosts,
                source="clinical_rule",
            )
        )
    if seeds:
        logger.info(
            "rule_fallback_seeds", count=len(seeds),
            names=[s.disease_name for s in seeds],
        )
    return seeds


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def retrieve_candidates(
    intake: "PatientIntake",
    phenotype_ids: list[str],
    neo4j_driver: "AsyncDriver",
    *,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    fallback_min: int = DEFAULT_FALLBACK_MIN,
) -> list[Candidate]:
    """Run the full retrieval pipeline and return a ranked candidate list.

    Args:
        intake: Validated patient data. Used for lab/demographic rules.
        phenotype_ids: Neo4j element IDs of phenotype nodes matching
            the patient's symptoms, as produced by vector search or
            medspaCy resolution.
        neo4j_driver: Async Neo4j driver.
        min_overlap: Minimum phenotype match count for a graph candidate.
        limit: Max graph-sourced candidates.
        fallback_min: If graph returns fewer than this many, allow
            rule-based fallback seeding.

    Returns:
        A score-descending list of Candidate objects. Each candidate
        carries its matched_edges (for graph-sourced) and rule_boosts
        (for any rule that fired on it) — the LLM prompt consumes both
        as per-candidate evidence.

    Raises:
        RetrievalError if no candidates could be produced at all.
    """
    # 1. Graph query
    graph_candidates = await _graph_candidates(
        phenotype_ids=phenotype_ids,
        neo4j_driver=neo4j_driver,
        min_overlap=min_overlap,
        limit=limit,
    )

    # 2. Compute rule boosts
    rule_boosts = apply_rules(intake)

    # 3. Apply boosts to graph candidates, collect unmatched
    unmatched = _apply_rule_boosts(graph_candidates, rule_boosts)

    # 4. Fallback seeding if graph pool is too thin
    all_candidates = list(graph_candidates)
    if len(all_candidates) < fallback_min and unmatched:
        existing_ids = {c.disease_id for c in all_candidates}
        rule_seeds = await _seed_from_rules(
            unmatched_boosts=unmatched,
            neo4j_driver=neo4j_driver,
            existing_ids=existing_ids,
        )
        all_candidates.extend(rule_seeds)

    if not all_candidates:
        raise RetrievalError(
            "No retrieval candidates — graph intersection and rule fallback "
            "both produced empty sets. Check phenotype extraction upstream."
        )

    # 5. Sort by final score descending, stable
    all_candidates.sort(key=lambda c: (-c.score, c.disease_name))

    logger.info(
        "retrieval_complete",
        total=len(all_candidates),
        from_graph=sum(1 for c in all_candidates if c.source == "graph"),
        from_rules=sum(1 for c in all_candidates if c.source == "clinical_rule"),
        top_score=all_candidates[0].score if all_candidates else 0,
        top_name=all_candidates[0].disease_name if all_candidates else "",
    )

    return all_candidates
