"""Input Guardrail Gates 2.2–2.5.

Sequential gates that run before the pipeline touches the graph or LLM.
"""

from __future__ import annotations

import json
import re
import unicodedata

import structlog

from app.config import DATA_DIR
from app.models.patient import PatientIntake
from app.observability.metrics import GATE_TRIGGERS

logger = structlog.get_logger()

# Gate 2.3 — Medical term set (loaded once at module level)
_medical_terms: set[str] | None = None


def _load_medical_terms() -> set[str]:
    """Load medical terms extracted from PrimeKG during ingestion."""
    terms_path = DATA_DIR / "medical_terms.json"
    if not terms_path.exists():
        logger.warning("medical_terms_not_found", path=str(terms_path))
        return set()
    with open(terms_path) as f:
        terms: list[str] = json.load(f)
    return {t.lower() for t in terms}


def get_medical_terms() -> set[str]:
    """Get or initialize the medical term set."""
    global _medical_terms
    if _medical_terms is None:
        _medical_terms = _load_medical_terms()
    return _medical_terms


# Gate 2.4 — Prompt injection patterns.
# Use \s* (zero or more whitespace) so attackers can't bypass with
# zero-width spaces or collapsed spacing.
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s*(all\s*)?previous\s*instructions", re.IGNORECASE),
    re.compile(r"ignore\s*(all\s*)?above\s*instructions", re.IGNORECASE),
    re.compile(r"forget\s*(your\s*)?system\s*prompt", re.IGNORECASE),
    re.compile(r"disregard\s*(all\s*)?prior", re.IGNORECASE),
    re.compile(r"new\s*instructions?\s*:", re.IGNORECASE),
    re.compile(r"DAN\s*mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"do\s*anything\s*now", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(?!a\s+clinical)", re.IGNORECASE),
    re.compile(r"system\s*:\s*you", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<<SYS>>", re.IGNORECASE),
]


class InputValidationError(Exception):
    """Raised when input fails a guardrail gate."""

    def __init__(self, gate: str, detail: str):
        self.gate = gate
        self.detail = detail
        super().__init__(f"Gate {gate}: {detail}")


def gate_medical_relevance(intake: PatientIntake) -> None:
    """Gate 2.3 — Check that input contains at least one medical term.

    Uses token-boundary matching (whole words) against PrimeKG-extracted terms.
    Rejects only clear non-medical noise (zero overlap + short free text).
    Ambiguous cases pass through.
    """
    terms = get_medical_terms()
    if not terms:
        # No term set loaded — skip gate (don't block during early dev)
        return

    all_input_tokens: set[str] = set()
    for symptom in intake.symptoms:
        all_input_tokens.update(symptom.lower().split())
    for hist in intake.history:
        all_input_tokens.update(hist.lower().split())
    for med in intake.medications:
        all_input_tokens.update(med.lower().split())
    if intake.free_text:
        all_input_tokens.update(intake.free_text.lower().split())

    # Check for any overlap with medical terms
    # Also check multi-word terms against full input strings
    full_input = intake.combined_text().lower()
    has_match = bool(all_input_tokens & terms) or any(term in full_input for term in terms)

    if not has_match:
        GATE_TRIGGERS.labels(gate_name="medical_relevance", result="rejected").inc()
        logger.info("medical_relevance_rejected", symptoms=intake.symptoms[:3])
        raise InputValidationError(
            gate="2.3",
            detail="Input does not appear to contain medical symptoms. Please describe clinical symptoms.",
        )

    GATE_TRIGGERS.labels(gate_name="medical_relevance", result="passed").inc()


def gate_prompt_injection(intake: PatientIntake) -> None:
    """Gate 2.4 — Two-layer prompt injection detection.

    Layer 1: Unicode NFKC normalization + control character stripping
    Layer 2: Regex patterns for known injection templates

    A previous revision had a third layer wrapping `guardrails-ai`'s
    DetectJailbreak inside a try/except ImportError. In practice the
    package was never configured (no hub registry, no hub token) so
    the import either failed silently or logged `Failed to read hub
    registry at /app/.guardrails/hub_registry.json` and did nothing.
    It was pure dead code + a 30 MB dependency for no added defence.
    Removed. If we ever want a real ML-based injection layer, a
    finetuned classifier or Cloudflare Turnstile is a cleaner drop-in.
    """
    # Layer 1: Sanitize
    all_text = intake.combined_text()
    normalized = unicodedata.normalize("NFKC", all_text)
    # Strip control characters except newline and tab
    sanitized = "".join(
        ch for ch in normalized
        if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )

    # Layer 2: Regex patterns
    for pattern in INJECTION_PATTERNS:
        if pattern.search(sanitized):
            GATE_TRIGGERS.labels(gate_name="prompt_injection", result="detected").inc()
            logger.warning(
                "prompt_injection_detected",
                pattern=pattern.pattern[:50],
                layer="regex",
            )
            raise InputValidationError(
                gate="2.4",
                detail="Input contains disallowed content patterns.",
            )

    GATE_TRIGGERS.labels(gate_name="prompt_injection", result="passed").inc()


def gate_token_budget(intake: PatientIntake, max_tokens: int = 4000) -> None:
    """Gate 2.5 — Approximate token budget check on input fields.

    Prevents oversized input from consuming expensive downstream resources.
    """
    all_text = intake.combined_text()
    for hist in intake.history:
        all_text += " " + hist
    for med in intake.medications:
        all_text += " " + med

    approx_tokens = len(all_text) / 4  # rough char-to-token ratio

    if approx_tokens > max_tokens:
        GATE_TRIGGERS.labels(gate_name="token_budget", result="rejected").inc()
        logger.info("token_budget_exceeded", approx_tokens=approx_tokens)
        raise InputValidationError(
            gate="2.5",
            detail=f"Input too long (~{int(approx_tokens)} tokens). Maximum is {max_tokens}.",
        )

    GATE_TRIGGERS.labels(gate_name="token_budget", result="passed").inc()


def run_input_gates(intake: PatientIntake) -> None:
    """Run all input guardrail gates (2.3–2.5) sequentially.

    Gate 2.2 (schema validation) is handled by Pydantic at the router level.
    Gate 2.1 (emergency) is handled separately and returns a result rather than raising.
    """
    gate_medical_relevance(intake)
    gate_prompt_injection(intake)
    gate_token_budget(intake)
