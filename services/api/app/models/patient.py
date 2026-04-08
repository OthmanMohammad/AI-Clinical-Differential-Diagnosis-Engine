"""Patient intake data models — Pydantic v2 with clinical validation ranges."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Vitals(BaseModel):
    """Vital signs with clinically plausible ranges."""

    temperature_c: float | None = Field(default=None, ge=30.0, le=45.0)
    heart_rate: int | None = Field(default=None, ge=20, le=300)
    systolic_bp: int | None = Field(default=None, ge=50, le=300)
    diastolic_bp: int | None = Field(default=None, ge=20, le=200)
    spo2: float | None = Field(default=None, ge=50.0, le=100.0)
    respiratory_rate: int | None = Field(default=None, ge=4, le=60)


class PatientIntake(BaseModel):
    """Clinical intake form — validated input for the diagnosis pipeline."""

    symptoms: list[str] = Field(min_length=1, max_length=20)
    age: int = Field(ge=0, le=130)
    sex: Literal["male", "female", "other"]
    history: list[str] = Field(default_factory=list, max_length=10)
    medications: list[str] = Field(default_factory=list, max_length=20)
    vitals: Vitals | None = None
    labs: dict[str, float] | None = None
    free_text: str = Field(default="", max_length=2000)

    def combined_text(self) -> str:
        """Merge symptoms + free text for NLP processing."""
        return ". ".join(self.symptoms) + ". " + self.free_text
