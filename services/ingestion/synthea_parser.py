"""Synthea FHIR JSON → Eval Cases Parser.

Parses Synthea-generated FHIR bundles into structured eval cases
for the evaluation pipeline.

Usage:
    python -m services.ingestion.synthea_parser --synthea-dir synthea_output/fhir
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("eval/cases")


def parse_fhir_bundle(bundle_path: Path) -> dict | None:
    """Parse a single Synthea FHIR bundle into an eval case."""
    with open(bundle_path) as f:
        bundle = json.load(f)

    entries = bundle.get("entry", [])
    if not entries:
        return None

    patient = None
    conditions: list[dict] = []
    medications: list[str] = []
    observations: list[dict] = []

    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")

        if rtype == "Patient":
            patient = {
                "name": _extract_name(resource),
                "birth_date": resource.get("birthDate", ""),
                "gender": resource.get("gender", "other"),
            }

        elif rtype == "Condition":
            code = resource.get("code", {})
            coding = code.get("coding", [{}])[0]
            conditions.append({
                "display": coding.get("display", ""),
                "icd_code": coding.get("code", ""),
                "system": coding.get("system", ""),
                "onset": resource.get("onsetDateTime", ""),
                "clinical_status": (
                    resource.get("clinicalStatus", {})
                    .get("coding", [{}])[0]
                    .get("code", "active")
                ),
            })

        elif rtype == "MedicationRequest":
            med_code = (
                resource.get("medicationCodeableConcept", {})
                .get("coding", [{}])[0]
                .get("display", "")
            )
            if med_code:
                medications.append(med_code)

        elif rtype == "Observation":
            obs_code = resource.get("code", {}).get("coding", [{}])[0]
            value = resource.get("valueQuantity", {})
            if obs_code.get("display") and value.get("value") is not None:
                observations.append({
                    "name": obs_code["display"],
                    "value": value["value"],
                    "unit": value.get("unit", ""),
                })

    if not patient or not conditions:
        return None

    # Use active conditions as the "expected" diagnoses
    active_conditions = [c for c in conditions if c["clinical_status"] == "active"]
    if not active_conditions:
        active_conditions = conditions[:3]

    # Build eval case
    age = _calc_age(patient["birth_date"])

    return {
        "patient": {
            "age": age,
            "sex": _normalize_sex(patient["gender"]),
            "symptoms": [c["display"] for c in active_conditions[:5]],
            "history": [
                c["display"] for c in conditions
                if c["clinical_status"] != "active"
            ][:5],
            "medications": list(set(medications))[:10],
            "labs": {
                obs["name"]: obs["value"]
                for obs in observations[:10]
            },
        },
        "expected_diagnoses": [c["display"] for c in active_conditions],
        "icd_codes": [c["icd_code"] for c in active_conditions if c["icd_code"]],
        "mapping_confidence": "automated",
        "source_file": bundle_path.name,
    }


def _extract_name(patient_resource: dict) -> str:
    """Extract patient name from FHIR resource."""
    names = patient_resource.get("name", [])
    if names:
        given = " ".join(names[0].get("given", []))
        family = names[0].get("family", "")
        return f"{given} {family}".strip()
    return "Unknown"


def _calc_age(birth_date: str) -> int:
    """Calculate approximate age from birth date."""
    if not birth_date:
        return 40  # default
    try:
        from datetime import date

        year = int(birth_date[:4])
        return date.today().year - year
    except (ValueError, IndexError):
        return 40


def _normalize_sex(gender: str) -> str:
    """Normalize FHIR gender to our model's sex field."""
    mapping = {"male": "male", "female": "female"}
    return mapping.get(gender.lower(), "other")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Synthea FHIR → eval cases")
    parser.add_argument(
        "--synthea-dir", type=Path, required=True,
        help="Directory containing Synthea FHIR JSON bundles",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-cases", type=int, default=200)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    bundles = sorted(args.synthea_dir.glob("*.json"))
    logger.info("Found %d FHIR bundles", len(bundles))

    cases: list[dict] = []
    for bundle_path in bundles[:args.max_cases * 2]:  # process extra in case some are invalid
        case = parse_fhir_bundle(bundle_path)
        if case:
            cases.append(case)
        if len(cases) >= args.max_cases:
            break

    logger.info("Parsed %d valid eval cases", len(cases))

    # Save individual cases
    for i, case in enumerate(cases):
        case_path = args.output_dir / f"case_{i:04d}.json"
        with open(case_path, "w") as f:
            json.dump(case, f, indent=2)

    # Save summary
    summary_path = args.output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {
                "total_cases": len(cases),
                "icd_codes_present": sum(1 for c in cases if c["icd_codes"]),
                "mapping_confidence_dist": {
                    "automated": sum(
                        1 for c in cases if c["mapping_confidence"] == "automated"
                    ),
                },
            },
            f,
            indent=2,
        )

    logger.info("Saved %d cases to %s", len(cases), args.output_dir)


if __name__ == "__main__":
    main()
