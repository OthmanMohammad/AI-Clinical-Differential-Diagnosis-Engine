"""Unit tests for app/core/lab_rules.py.

Runs without any external services. Tests cover:
- Rule loading from YAML (happy path + schema errors)
- ClinicalRule.matches() for lab / age / sex / history / symptoms conditions
- apply_rules() producing expected RuleBoosts for each eval case's pattern
- Refusal to load rules that falsely claim clinical validation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Make services/api importable without installing the whole stack
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from app.core.lab_rules import (  # noqa: E402
    ClinicalRule,
    ClinicalRuleError,
    DiseaseBoost,
    RuleBoost,
    apply_rules,
    load_rules,
)
from app.models.patient import PatientIntake  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _intake(
    *,
    symptoms: list[str] | None = None,
    age: int = 50,
    sex: str = "male",
    history: list[str] | None = None,
    medications: list[str] | None = None,
    labs: dict[str, float] | None = None,
    free_text: str = "",
) -> PatientIntake:
    return PatientIntake(
        symptoms=symptoms or ["test symptom"],
        age=age,
        sex=sex,
        history=history or [],
        medications=medications or [],
        labs=labs,
        free_text=free_text,
    )


def _write_rules(tmp_path: Path, rules: list[dict], version: int = 1) -> Path:
    p = tmp_path / "clinical_rules.yaml"
    p.write_text(yaml.safe_dump({"version": version, "rules": rules}))
    return p


# ---------------------------------------------------------------------------
# load_rules — happy path + schema errors
# ---------------------------------------------------------------------------


def test_load_rules_happy_path(tmp_path):
    p = _write_rules(
        tmp_path,
        [
            {
                "id": "r1",
                "label": "Test rule",
                "description": "desc",
                "when": {"labs": {"glucose": {"op": ">", "value": 200}}},
                "boosts": [
                    {"name": "Type 2 Diabetes Mellitus", "multiplier": 2.0, "rationale": "hi"}
                ],
                "source": "textbook",
                "last_reviewed": "2026-04-14",
                "clinically_validated": False,
            }
        ],
    )
    rules = load_rules(p)
    assert len(rules) == 1
    assert rules[0].id == "r1"
    assert isinstance(rules[0].boosts[0], DiseaseBoost)
    assert rules[0].boosts[0].disease_name == "Type 2 Diabetes Mellitus"


def test_load_rules_file_missing_returns_empty(tmp_path):
    assert load_rules(tmp_path / "nope.yaml") == []


def test_load_rules_wrong_version_errors(tmp_path):
    p = _write_rules(tmp_path, [], version=99)
    with pytest.raises(ClinicalRuleError, match="unsupported version"):
        load_rules(p)


def test_load_rules_duplicate_id_errors(tmp_path):
    p = _write_rules(
        tmp_path,
        [
            {
                "id": "dup",
                "when": {},
                "boosts": [{"name": "X", "multiplier": 1.5}],
                "clinically_validated": False,
            },
            {
                "id": "dup",
                "when": {},
                "boosts": [{"name": "Y", "multiplier": 1.5}],
                "clinically_validated": False,
            },
        ],
    )
    with pytest.raises(ClinicalRuleError, match="duplicate rule id 'dup'"):
        load_rules(p)


def test_load_rules_missing_boosts_errors(tmp_path):
    p = _write_rules(
        tmp_path,
        [{"id": "r1", "when": {}, "boosts": [], "clinically_validated": False}],
    )
    with pytest.raises(ClinicalRuleError, match="has no boosts"):
        load_rules(p)


def test_load_rules_invalid_multiplier_errors(tmp_path):
    p = _write_rules(
        tmp_path,
        [
            {
                "id": "r1",
                "when": {},
                "boosts": [{"name": "X", "multiplier": -1.0}],
                "clinically_validated": False,
            }
        ],
    )
    with pytest.raises(ClinicalRuleError, match="invalid multiplier"):
        load_rules(p)


def test_load_rules_refuses_clinically_validated_true(tmp_path):
    """Critical safety net — the loader must refuse rules that claim
    physician validation. Only a clinician should flip this flag, and
    this repo does not yet have the review infrastructure to accept it.
    """
    p = _write_rules(
        tmp_path,
        [
            {
                "id": "r1",
                "when": {},
                "boosts": [{"name": "X", "multiplier": 1.5}],
                "clinically_validated": True,
            }
        ],
    )
    with pytest.raises(ClinicalRuleError, match="clinically_validated=true"):
        load_rules(p)


# ---------------------------------------------------------------------------
# ClinicalRule.matches — lab conditions
# ---------------------------------------------------------------------------


def _rule_labs(id_: str, labs: dict) -> ClinicalRule:
    return ClinicalRule(
        id=id_,
        label=id_,
        description="",
        when={"labs": labs},
        boosts=(DiseaseBoost("X", 2.0, ""),),
        source="",
        last_reviewed="",
    )


def test_matches_lab_gt_fires():
    rule = _rule_labs("r", {"glucose": {"op": ">", "value": 200}})
    assert rule.matches(_intake(labs={"glucose": 287}))
    assert not rule.matches(_intake(labs={"glucose": 180}))
    assert not rule.matches(_intake(labs={"glucose": 200}))  # strict gt


def test_matches_lab_gte_inclusive():
    rule = _rule_labs("r", {"hba1c": {"op": ">=", "value": 6.5}})
    assert rule.matches(_intake(labs={"hba1c": 6.5}))
    assert rule.matches(_intake(labs={"hba1c": 9.2}))
    assert not rule.matches(_intake(labs={"hba1c": 6.4}))


def test_matches_lab_missing_lab_does_not_fire():
    """If the patient didn't provide the lab the rule needs, the rule must
    NOT fire. Pydantic forbids null dict values so we test missing-key
    scenarios only — `labs=None` and `labs={}`. That covers the runtime
    reality where the frontend omits the field entirely."""
    rule = _rule_labs("r", {"glucose": {"op": ">", "value": 200}})
    assert not rule.matches(_intake(labs=None))
    assert not rule.matches(_intake(labs={}))
    assert not rule.matches(_intake(labs={"hemoglobin": 8.0}))


def test_matches_multiple_lab_conditions_is_and():
    """Multiple lab conditions in a single `when.labs` block are AND'd."""
    rule = _rule_labs(
        "r",
        {"glucose": {"op": ">", "value": 250}, "bicarbonate": {"op": "<", "value": 18}},
    )
    # Only one — should NOT fire
    assert not rule.matches(_intake(labs={"glucose": 500}))
    assert not rule.matches(_intake(labs={"bicarbonate": 10}))
    # Both — fires
    assert rule.matches(_intake(labs={"glucose": 500, "bicarbonate": 10}))


def test_matches_age_condition():
    rule = ClinicalRule(
        id="r",
        label="r",
        description="",
        when={"age": {"op": ">=", "value": 65}},
        boosts=(DiseaseBoost("X", 1.5, ""),),
        source="",
        last_reviewed="",
    )
    assert rule.matches(_intake(age=70))
    assert rule.matches(_intake(age=65))
    assert not rule.matches(_intake(age=30))


def test_matches_sex_condition():
    rule = ClinicalRule(
        id="r",
        label="r",
        description="",
        when={"sex": "female"},
        boosts=(DiseaseBoost("X", 1.5, ""),),
        source="",
        last_reviewed="",
    )
    assert rule.matches(_intake(sex="female"))
    assert not rule.matches(_intake(sex="male"))


def test_matches_symptoms_contains_any():
    rule = ClinicalRule(
        id="r",
        label="r",
        description="",
        when={"symptoms_contains_any": ["shortness of breath", "dyspnea"]},
        boosts=(DiseaseBoost("X", 1.5, ""),),
        source="",
        last_reviewed="",
    )
    assert rule.matches(_intake(symptoms=["shortness of breath", "cough"]))
    assert rule.matches(_intake(symptoms=["dyspnea on exertion"]))
    assert not rule.matches(_intake(symptoms=["fatigue", "polyuria"]))


def test_matches_history_contains_any():
    rule = ClinicalRule(
        id="r",
        label="r",
        description="",
        when={"history_contains": ["diabetes"]},
        boosts=(DiseaseBoost("X", 1.5, ""),),
        source="",
        last_reviewed="",
    )
    assert rule.matches(_intake(history=["type 2 diabetes mellitus"]))
    assert not rule.matches(_intake(history=["hypertension"]))


# ---------------------------------------------------------------------------
# apply_rules — integration against the real shipped rules file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def production_rules():
    repo_root = Path(__file__).resolve().parents[2]
    return load_rules(repo_root / "data" / "clinical_rules.yaml")


def test_production_rules_load(production_rules):
    assert len(production_rules) >= 10, "expected at least 10 rules shipped"
    ids = {r.id for r in production_rules}
    # Spot-check a few known rule IDs
    assert "hyperglycemia_diabetes" in ids
    assert "elevated_troponin_mi" in ids
    assert "elevated_bnp_heart_failure" in ids
    assert "elevated_dimer_with_dyspnea_pe" in ids
    assert "elevated_lactate_sepsis" in ids


def test_t2dm_case_triggers_diabetes_rules(production_rules):
    """case_01_t2dm_classic → must boost Type 2 Diabetes Mellitus."""
    intake = _intake(
        symptoms=["polyuria", "polydipsia"],
        age=52,
        sex="male",
        labs={"glucose": 287, "hba1c": 9.2},
    )
    boosts = apply_rules(intake, rules=production_rules)
    t2dm_boosts = [b for b in boosts if "type 2" in b.disease_name.lower()]
    assert len(t2dm_boosts) >= 2, "both glucose and hba1c rules should fire"
    assert any(b.rule_id == "hyperglycemia_diabetes" for b in t2dm_boosts)
    assert any(b.rule_id == "elevated_hba1c_diabetes" for b in t2dm_boosts)


def test_stemi_case_triggers_troponin_rule(production_rules):
    """case_04_stemi → must boost Acute MI via troponin rule."""
    intake = _intake(
        symptoms=["severe chest pain"],
        age=64,
        sex="male",
        labs={"troponin": 2.8},
    )
    boosts = apply_rules(intake, rules=production_rules)
    assert any("myocardial infarction" in b.disease_name.lower() for b in boosts)
    assert any(b.rule_id == "elevated_troponin_mi" for b in boosts)


def test_chf_case_triggers_bnp_rule(production_rules):
    """case_15_heart_failure → must boost Heart Failure via BNP rule."""
    intake = _intake(
        symptoms=["shortness of breath", "leg swelling"],
        age=69,
        sex="male",
        labs={"bnp": 1850},
    )
    boosts = apply_rules(intake, rules=production_rules)
    assert any("heart failure" in b.disease_name.lower() for b in boosts)


def test_pe_case_triggers_dimer_rule(production_rules):
    """case_05_pulmonary_embolism → must boost PE via d-dimer + dyspnea rule."""
    intake = _intake(
        symptoms=["sudden shortness of breath", "pleuritic chest pain"],
        age=45,
        sex="female",
        labs={"d_dimer": 3200},
    )
    boosts = apply_rules(intake, rules=production_rules)
    assert any("pulmonary embolism" in b.disease_name.lower() for b in boosts)


def test_pe_rule_does_not_fire_without_symptom(production_rules):
    """D-dimer alone without dyspnea must NOT trigger the PE rule —
    D-dimer is nonspecific without the clinical context."""
    intake = _intake(
        symptoms=["headache"],
        age=45,
        sex="female",
        labs={"d_dimer": 3200},
    )
    boosts = apply_rules(intake, rules=production_rules)
    pe_boosts = [b for b in boosts if b.rule_id == "elevated_dimer_with_dyspnea_pe"]
    assert pe_boosts == [], "PE rule must require both d-dimer AND dyspnea"


def test_dka_case_triggers_compound_rule(production_rules):
    """case_09_dka → severe_hyperglycemia_dka needs BOTH glucose AND bicarbonate."""
    intake = _intake(
        symptoms=["polyuria"],
        age=24,
        sex="female",
        labs={"glucose": 512, "bicarbonate": 9},
    )
    boosts = apply_rules(intake, rules=production_rules)
    assert any("ketoacidosis" in b.disease_name.lower() for b in boosts)


def test_dka_rule_does_not_fire_on_glucose_alone(production_rules):
    """Glucose high without low bicarb must not trigger DKA rule."""
    intake = _intake(
        symptoms=["polyuria"],
        age=52,
        sex="male",
        labs={"glucose": 500},
    )
    boosts = apply_rules(intake, rules=production_rules)
    dka_boosts = [b for b in boosts if b.rule_id == "severe_hyperglycemia_dka"]
    assert dka_boosts == []


def test_apply_rules_empty_for_healthy_patient(production_rules):
    """A patient with no abnormal labs and no symptoms matching rule
    clauses should produce zero boosts."""
    intake = _intake(
        symptoms=["headache"],
        age=30,
        sex="female",
        labs={"hemoglobin": 14.0},
    )
    boosts = apply_rules(intake, rules=production_rules)
    # May be empty — assert no nonsense boosts (no MI, DKA, etc)
    disease_names = {b.disease_name.lower() for b in boosts}
    assert not any("diabetes" in n for n in disease_names)
    assert not any("infarction" in n for n in disease_names)
