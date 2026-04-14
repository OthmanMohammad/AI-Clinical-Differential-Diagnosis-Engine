"""GET /api/v1/metadata/* — client-facing reference data.

Serves the medical term set for frontend autocomplete. This is essentially
a proxy around the data/medical_terms.json file produced by ingestion.
"""

from __future__ import annotations

import json
from functools import lru_cache

import structlog
from fastapi import APIRouter, HTTPException

from app.config import DATA_DIR

logger = structlog.get_logger()

router = APIRouter(tags=["metadata"])


@lru_cache(maxsize=1)
def _load_medical_terms() -> list[str]:
    path = DATA_DIR / "medical_terms.json"
    if not path.exists():
        logger.warning("medical_terms_missing", path=str(path))
        return []
    with open(path) as f:
        data: list[str] = json.load(f)
    logger.info("medical_terms_loaded", count=len(data))
    return data


@router.get(
    "/metadata/medical-terms",
    summary="PrimeKG medical term set",
    description=(
        "Returns the flat list of PrimeKG node names extracted during "
        "ingestion. Used by the frontend for symptom autocomplete."
    ),
)
async def medical_terms() -> list[str]:
    terms = _load_medical_terms()
    if not terms:
        raise HTTPException(
            status_code=503,
            detail="Medical term set not available. Run ingestion first.",
        )
    return terms
