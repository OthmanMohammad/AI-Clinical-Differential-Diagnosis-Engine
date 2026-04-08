"""Tests for Pydantic models — Gate 2.2 (schema validation)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.diagnosis import DiagnosisItem, DifferentialDiagnosis, DiagnosisResponse
from app.models.patient import PatientIntake, Vitals


class TestVitals:
    def test_valid_vitals(self):
        v = Vitals(temperature_c=37.0, heart_rate=72, systolic_bp=120, diastolic_bp=80)
        assert v.temperature_c == 37.0

    def test_temperature_too_low(self):
        with pytest.raises(ValidationError):
            Vitals(temperature_c=29.0)

    def test_temperature_too_high(self):
        with pytest.raises(ValidationError):
            Vitals(temperature_c=46.0)

    def test_heart_rate_bounds(self):
        with pytest.raises(ValidationError):
            Vitals(heart_rate=301)

    def test_spo2_bounds(self):
        with pytest.raises(ValidationError):
            Vitals(spo2=101.0)

    def test_all_none(self):
        v = Vitals()
        assert v.temperature_c is None
        assert v.heart_rate is None


class TestPatientIntake:
    def test_valid_intake(self, basic_intake):
        assert len(basic_intake.symptoms) == 3
        assert basic_intake.age == 35

    def test_empty_symptoms_rejected(self):
        with pytest.raises(ValidationError):
            PatientIntake(symptoms=[], age=30, sex="male")

    def test_too_many_symptoms(self):
        with pytest.raises(ValidationError):
            PatientIntake(symptoms=["s"] * 21, age=30, sex="male")

    def test_age_bounds(self):
        with pytest.raises(ValidationError):
            PatientIntake(symptoms=["headache"], age=-1, sex="male")
        with pytest.raises(ValidationError):
            PatientIntake(symptoms=["headache"], age=131, sex="male")

    def test_invalid_sex(self):
        with pytest.raises(ValidationError):
            PatientIntake(symptoms=["headache"], age=30, sex="alien")

    def test_free_text_max_length(self):
        with pytest.raises(ValidationError):
            PatientIntake(
                symptoms=["headache"], age=30, sex="male",
                free_text="x" * 2001,
            )

    def test_combined_text(self, basic_intake):
        text = basic_intake.combined_text()
        assert "joint pain" in text
        assert "butterfly rash" in text


class TestDiagnosisModels:
    def test_valid_diagnosis_item(self):
        item = DiagnosisItem(
            disease_name="Lupus",
            confidence=0.8,
            supporting_evidence=["evidence 1"],
            graph_path=["Symptom", "Disease"],
        )
        assert item.confidence == 0.8

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            DiagnosisItem(
                disease_name="Test",
                confidence=1.5,
                supporting_evidence=["e"],
            )

    def test_empty_evidence_rejected(self):
        with pytest.raises(ValidationError):
            DiagnosisItem(
                disease_name="Test",
                confidence=0.5,
                supporting_evidence=[],
            )

    def test_valid_differential(self, sample_llm_output):
        dd = DifferentialDiagnosis.model_validate(sample_llm_output)
        assert len(dd.diagnoses) == 2

    def test_response_has_disclaimer(self):
        resp = DiagnosisResponse(diagnoses=[])
        assert "AI clinical decision support" in resp.disclaimer
