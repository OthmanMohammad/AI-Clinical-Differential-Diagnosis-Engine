"""Layer 5 — LLM Reasoning via LiteLLM.

Single interface for all providers. Automatic fallback chain.
Groq (free) → Cerebras (free) → Groq small (free) → 503.
"""

from __future__ import annotations

import json
import time

import structlog
from litellm import acompletion

from app.config import get_settings
from app.observability.metrics import LLM_LATENCY

logger = structlog.get_logger()


class LLMError(Exception):
    """Raised when all LLM providers fail."""


class LLMSchemaError(Exception):
    """Raised when LLM returns unparseable JSON after retries."""


CORRECTION_PROMPT = (
    "Your previous response was not valid JSON. "
    "Return ONLY valid JSON matching the schema. No preamble, no markdown, no explanation. "
    "Just the JSON object."
)


async def call_llm(
    messages: list[dict],
    max_retries: int = 1,
) -> tuple[dict, str]:
    """Call LLM with automatic fallback chain and JSON parsing.

    Args:
        messages: System + user messages.
        max_retries: Max retries on malformed JSON (after first attempt).

    Returns:
        Tuple of (parsed_json_response, model_identifier).

    Raises:
        LLMError: All providers failed.
        LLMSchemaError: Valid response but unparseable JSON after retries.
    """
    settings = get_settings()

    for attempt in range(1 + max_retries):
        try:
            start = time.monotonic()

            response = await acompletion(
                model=settings.primary_llm,
                messages=messages,
                fallbacks=settings.fallback_llms,
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
                timeout=settings.llm_timeout,
                num_retries=1,
            )

            elapsed = time.monotonic() - start
            model_used = getattr(response, "model", settings.primary_llm)
            LLM_LATENCY.labels(model=model_used).observe(elapsed)

            raw_content = response.choices[0].message.content
            logger.info(
                "llm_call_complete",
                model=model_used,
                elapsed_ms=round(elapsed * 1000),
                tokens=getattr(response.usage, "total_tokens", 0) if response.usage else 0,
                attempt=attempt + 1,
            )

            # Parse JSON
            try:
                result = json.loads(raw_content)
                return result, model_used
            except json.JSONDecodeError as exc:
                logger.warning(
                    "llm_json_parse_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                    raw_preview=raw_content[:200],
                )
                if attempt < max_retries:
                    # Retry with correction prompt
                    messages = messages + [
                        {"role": "assistant", "content": raw_content},
                        {"role": "user", "content": CORRECTION_PROMPT},
                    ]
                    continue
                raise LLMSchemaError(
                    "LLM returned invalid JSON after retries. "
                    f"Raw output preview: {raw_content[:200]}"
                ) from exc

        except (LLMSchemaError, LLMError):
            raise
        except Exception as exc:
            logger.error(
                "llm_call_failed",
                error=str(exc),
                attempt=attempt + 1,
            )
            if attempt >= max_retries:
                raise LLMError(
                    "All inference providers unavailable. Please retry in a few minutes."
                ) from exc

    raise LLMError("LLM call exhausted all retries.")
