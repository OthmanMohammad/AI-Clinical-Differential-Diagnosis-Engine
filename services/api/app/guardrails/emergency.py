"""Gate 2.1 — Emergency Detector.

medspaCy for negation/context detection + hardcoded emergency patterns.
Runs on every request before any LLM call. Must be fast, deterministic, always available.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from spacy.language import Language

from app.config import DATA_DIR
from app.models.diagnosis import EmergencyResult
from app.observability.metrics import EMERGENCY_TRIGGERS, GATE_TRIGGERS

if TYPE_CHECKING:
    from app.models.patient import PatientIntake

logger = structlog.get_logger()

# Emergency patterns — clinically validated, hardcoded, deterministic
EMERGENCY_PATTERNS = [
    {
        "name": "cardiac_emergency",
        "primary": [
            "chest pain", "chest tightness", "chest pressure", "crushing chest",
        ],
        "secondary": [
            "shortness of breath", "left arm pain", "jaw pain",
            "cold sweat", "diaphoresis", "nausea",
        ],
        "min_primary": 1,
        "min_secondary": 1,
    },
    {
        "name": "stroke",
        "primary": [
            "facial drooping", "arm weakness", "leg weakness",
            "slurred speech", "sudden numbness",
        ],
        "secondary": [
            "sudden onset", "worst headache", "vision loss",
            "confusion", "difficulty walking",
        ],
        "min_primary": 1,
        "min_secondary": 1,
    },
    {
        "name": "meningitis",
        "primary": [
            "severe headache", "neck stiffness", "nuchal rigidity",
        ],
        "secondary": [
            "fever", "photophobia", "altered mental status", "petechial rash",
        ],
        "min_primary": 1,
        "min_secondary": 2,
    },
    {
        "name": "anaphylaxis",
        "primary": [
            "throat swelling", "airway compromise", "angioedema",
            "difficulty breathing",
        ],
        "secondary": [
            "hives", "urticaria", "wheezing", "allergic reaction",
            "recent exposure",
        ],
        "min_primary": 1,
        "min_secondary": 1,
    },
    {
        "name": "pulmonary_embolism",
        "primary": [
            "sudden shortness of breath", "pleuritic chest pain",
        ],
        "secondary": [
            "leg swelling", "recent surgery", "immobility",
            "hemoptysis", "tachycardia",
        ],
        "min_primary": 1,
        "min_secondary": 1,
    },
    {
        "name": "suicidal_ideation",
        "primary": [
            "want to die", "kill myself", "suicidal", "end my life",
            "self-harm", "suicide",
        ],
        "secondary": [],
        "min_primary": 1,
        "min_secondary": 0,
    },
]

# Module-level NLP pipeline — initialized once at import
_nlp: Language | None = None


def _load_nlp() -> Language:
    """Build the medspaCy pipeline with EntityRuler + ConText."""
    import medspacy

    nlp = medspacy.load(enable=["sentencizer", "context"])

    # Add EntityRuler before ConText so entities are tagged before negation
    ruler = nlp.add_pipe("entity_ruler", before="medspacy_context")

    patterns: list[dict] = []

    # Load PrimeKG medical terms if available
    terms_path = DATA_DIR / "medical_terms.json"
    if terms_path.exists():
        with open(terms_path) as f:
            medical_terms: list[str] = json.load(f)
        for term in medical_terms:
            patterns.append({"label": "MEDICAL", "pattern": term.lower()})
        logger.info("entity_ruler_loaded_primekg", count=len(medical_terms))

    # Load symptom synonyms if available
    synonyms_path = DATA_DIR / "symptom_synonyms.json"
    if synonyms_path.exists():
        with open(synonyms_path) as f:
            synonym_map: dict[str, list[str]] = json.load(f)
        for canonical, variants in synonym_map.items():
            patterns.append({"label": "MEDICAL", "pattern": canonical.lower()})
            for variant in variants:
                patterns.append({"label": "MEDICAL", "pattern": variant.lower()})
        logger.info("entity_ruler_loaded_synonyms", count=len(synonym_map))

    # Always load emergency keywords as patterns
    for pattern_def in EMERGENCY_PATTERNS:
        for kw in pattern_def["primary"] + pattern_def["secondary"]:
            patterns.append({"label": "MEDICAL", "pattern": kw.lower()})

    ruler.add_patterns(patterns)
    logger.info("nlp_pipeline_ready", total_patterns=len(patterns))
    return nlp


def get_nlp() -> Language:
    """Get or initialize the NLP pipeline (lazy singleton)."""
    global _nlp
    if _nlp is None:
        _nlp = _load_nlp()
    return _nlp


def preload_nlp() -> None:
    """Eagerly load the NLP pipeline. Call this at app startup so the
    first request doesn't pay the ~30 second model load cost."""
    if _nlp is None:
        logger.info("preloading_nlp_pipeline")
        get_nlp()
        logger.info("nlp_pipeline_preloaded")


def extract_affirmed_concepts(text: str) -> set[str]:
    """Return only medical concepts that are affirmed —
    not negated, not historical, not hypothetical."""
    nlp = get_nlp()
    doc = nlp(text.lower())

    affirmed: set[str] = set()
    for ent in doc.ents:
        is_negated = getattr(ent._, "is_negated", False)
        is_historical = getattr(ent._, "is_historical", False)
        is_hypothetical = getattr(ent._, "is_hypothetical", False)

        if not is_negated and not is_historical and not is_hypothetical:
            affirmed.add(ent.text.lower())

    return affirmed


def check_emergency(intake: PatientIntake) -> EmergencyResult:
    """Run emergency detection on patient intake.

    Combines structured symptoms with free text, applies negation detection
    via medspaCy, then checks affirmed concepts against emergency patterns.
    """
    combined_text = intake.combined_text()
    affirmed = extract_affirmed_concepts(combined_text)

    # Also add structured symptoms directly (they bypass NLP — user explicitly selected them)
    for symptom in intake.symptoms:
        affirmed.add(symptom.lower())

    logger.debug("emergency_check", affirmed_count=len(affirmed), affirmed=list(affirmed)[:10])

    for pattern in EMERGENCY_PATTERNS:
        primary_hits = sum(
            1 for kw in pattern["primary"]
            if any(kw in concept for concept in affirmed)
        )
        secondary_hits = sum(
            1 for kw in pattern["secondary"]
            if any(kw in concept for concept in affirmed)
        )

        if (
            primary_hits >= pattern["min_primary"]
            and secondary_hits >= pattern["min_secondary"]
        ):
            EMERGENCY_TRIGGERS.labels(pattern_name=pattern["name"]).inc()
            GATE_TRIGGERS.labels(gate_name="emergency", result="triggered").inc()

            logger.warning(
                "emergency_detected",
                pattern=pattern["name"],
                primary_hits=primary_hits,
                secondary_hits=secondary_hits,
            )

            return EmergencyResult(
                triggered=True,
                pattern_name=pattern["name"],
                message=(
                    "This describes a potential medical emergency. "
                    "Call emergency services (911) immediately. "
                    "Do not rely on this tool for emergency medical decisions."
                ),
            )

    GATE_TRIGGERS.labels(gate_name="emergency", result="passed").inc()
    return EmergencyResult(triggered=False)
