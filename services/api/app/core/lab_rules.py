"""Clinical lab + demographic rule engine.

Loads rules from data/clinical_rules.yaml at module import and exposes
a pure function `apply_rules(intake)` that returns a list of disease-
name boosts with their provenance.

Design constraints:

* **Rules as data, not code.** Edits are made to the YAML file, not
  to Python. The loader validates schema at startup and raises
  ClinicalRuleError on bad input.

* **Rules never invent diagnoses.** The retrieval pipeline applies
  rule boosts ONLY as score multipliers on candidates that already
  came from the graph-based phenotype intersection query. If the
  graph query returns fewer than N candidates, rules are allowed to
  fall back to seeding — but any rule-only seed is tagged with
  `source=clinical_rule` so the LLM knows it's a heuristic, not a
  graph-backed retrieval.

* **No physician validation.** Every rule in the YAML file is marked
  `clinically_validated: false` and the loader refuses to load any
  rule where that field is `true` (to prevent someone from silently
  flipping the bit without review).

Public API:
    load_rules(path)                  -> list[ClinicalRule]
    apply_rules(intake, rules=None)   -> list[RuleBoost]
    RULES                              (module-level cache, lazy-loaded)

The YAML schema is documented at the top of data/clinical_rules.yaml.
"""

from __future__ import annotations

import logging
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import DATA_DIR
from app.models.patient import PatientIntake

logger = logging.getLogger(__name__)

# Comparison operators allowed in rule conditions.
_OPS: dict[str, Any] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


class ClinicalRuleError(Exception):
    """Raised when a rule file fails schema validation."""


@dataclass(frozen=True)
class DiseaseBoost:
    """A single disease boost produced by one rule."""

    disease_name: str
    multiplier: float
    rationale: str


@dataclass(frozen=True)
class ClinicalRule:
    """Compiled representation of one rule from the YAML file."""

    id: str
    label: str
    description: str
    when: dict
    boosts: tuple[DiseaseBoost, ...]
    source: str
    last_reviewed: str

    def matches(self, intake: PatientIntake) -> bool:
        """Return True if this rule fires on the given intake.

        The rule's `when` block is a conjunction: ALL listed conditions
        must evaluate True for the rule to match. This is deliberately
        strict — rules are heuristics, and a lenient OR would produce
        too many false positives on partially-matching patients.
        """
        when = self.when or {}

        # Lab conditions
        lab_conds = when.get("labs") or {}
        if lab_conds:
            labs = intake.labs or {}
            for lab_name, cond in lab_conds.items():
                val = labs.get(lab_name)
                if val is None:
                    return False
                op_name = cond.get("op", ">")
                threshold = cond.get("value")
                op = _OPS.get(op_name)
                if op is None or threshold is None:
                    return False
                if not op(float(val), float(threshold)):
                    return False

        # Age
        age_cond = when.get("age")
        if age_cond:
            op = _OPS.get(age_cond.get("op", ">="))
            threshold = age_cond.get("value")
            if op is None or threshold is None:
                return False
            if not op(intake.age, threshold):
                return False

        # Sex
        sex = when.get("sex")
        if sex and intake.sex != sex:
            return False

        # History any-of
        hist_any = when.get("history_contains") or []
        if hist_any:
            intake_hist = " ".join(intake.history).lower()
            if not any(kw.lower() in intake_hist for kw in hist_any):
                return False

        # Symptoms any-of
        sym_any = when.get("symptoms_contains_any") or []
        if sym_any:
            intake_sym = " ".join(intake.symptoms).lower()
            if not any(kw.lower() in intake_sym for kw in sym_any):
                return False

        return True


@dataclass
class RuleBoost:
    """One rule's contribution to a candidate disease's score.

    Emitted by `apply_rules` and consumed by `retrieval.py`. One intake
    can produce multiple RuleBoosts against the same disease (e.g.
    both the hyperglycemia rule AND the HbA1c rule fire for T2DM);
    retrieval.py compounds them with _combine_boosts.
    """

    disease_name: str
    multiplier: float
    rule_id: str
    rule_label: str
    rationale: str


# Module-level cache (loaded lazily on first apply_rules call).
_rules_cache: list[ClinicalRule] | None = None
_rules_source_path: Path | None = None


def load_rules(path: Path | None = None) -> list[ClinicalRule]:
    """Load and validate rules from the YAML file.

    Raises ClinicalRuleError on schema violations. Called once at
    startup via the module-level cache in apply_rules; tests may
    call it directly with a fixture path.
    """
    if path is None:
        path = DATA_DIR / "clinical_rules.yaml"
    if not path.exists():
        logger.warning("clinical_rules_file_missing path=%s", path)
        return []

    with open(path) as f:
        doc = yaml.safe_load(f) or {}

    if doc.get("version") != 1:
        raise ClinicalRuleError(f"{path}: unsupported version {doc.get('version')!r}; expected 1")

    raw_rules = doc.get("rules") or []
    compiled: list[ClinicalRule] = []
    seen_ids: set[str] = set()

    for idx, raw in enumerate(raw_rules):
        rid = raw.get("id", f"<anon-{idx}>")
        if rid in seen_ids:
            raise ClinicalRuleError(f"{path}: duplicate rule id '{rid}'")
        seen_ids.add(rid)

        # Safety net: we refuse to silently accept rules that claim
        # clinical validation. Flip this explicitly only when a real
        # clinician has signed off.
        if raw.get("clinically_validated") is True:
            raise ClinicalRuleError(
                f"{path}: rule '{rid}' has clinically_validated=true but this "
                "repository does not yet accept physician-validated rules. "
                "Remove the flag or set it to false."
            )

        boosts_raw = raw.get("boosts") or []
        if not boosts_raw:
            raise ClinicalRuleError(f"{path}: rule '{rid}' has no boosts")

        boosts: list[DiseaseBoost] = []
        for b in boosts_raw:
            name = b.get("name")
            mult = b.get("multiplier")
            if not isinstance(name, str) or not name:
                raise ClinicalRuleError(f"{path}: rule '{rid}' boost missing name")
            if not isinstance(mult, (int, float)) or mult <= 0:
                raise ClinicalRuleError(
                    f"{path}: rule '{rid}' boost '{name}' has invalid multiplier {mult!r}"
                )
            boosts.append(
                DiseaseBoost(
                    disease_name=name,
                    multiplier=float(mult),
                    rationale=str(b.get("rationale", "")),
                )
            )

        compiled.append(
            ClinicalRule(
                id=str(rid),
                label=str(raw.get("label", rid)),
                description=str(raw.get("description", "")),
                when=raw.get("when") or {},
                boosts=tuple(boosts),
                source=str(raw.get("source", "")),
                last_reviewed=str(raw.get("last_reviewed", "")),
            )
        )

    logger.info("clinical_rules_loaded count=%d path=%s", len(compiled), path)
    return compiled


def get_rules() -> list[ClinicalRule]:
    """Lazy-load the module-level rule cache."""
    global _rules_cache, _rules_source_path
    if _rules_cache is None:
        path = DATA_DIR / "clinical_rules.yaml"
        _rules_source_path = path
        _rules_cache = load_rules(path)
    return _rules_cache


def reset_cache() -> None:
    """Test hook — clears the module-level cache so a fresh file is read."""
    global _rules_cache, _rules_source_path
    _rules_cache = None
    _rules_source_path = None


def apply_rules(
    intake: PatientIntake,
    rules: list[ClinicalRule] | None = None,
) -> list[RuleBoost]:
    """Apply all loaded rules against a patient intake.

    Args:
        intake: Validated PatientIntake.
        rules: Optional pre-loaded rule list (used by tests). If None,
               uses the module-level cached rules.

    Returns:
        A list of RuleBoost objects, one per (matched_rule × boosted_disease)
        combination. The list may contain duplicate disease names when
        multiple rules fire for the same diagnosis — retrieval.py combines
        them with a single aggregation step.
    """
    if rules is None:
        rules = get_rules()

    out: list[RuleBoost] = []
    for rule in rules:
        if not rule.matches(intake):
            continue
        for boost in rule.boosts:
            out.append(
                RuleBoost(
                    disease_name=boost.disease_name,
                    multiplier=boost.multiplier,
                    rule_id=rule.id,
                    rule_label=rule.label,
                    rationale=boost.rationale,
                )
            )

    if out:
        logger.info(
            "clinical_rules_applied matches=%d unique_diseases=%d",
            len(out),
            len({b.disease_name.lower() for b in out}),
        )

    return out
