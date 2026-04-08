"""ICD-10 → PrimeKG Mapping Builder.

PrimeKG uses MONDO disease IDs. Synthea generates ICD-10 codes.
This script builds the mapping table via MONDO SSSOM mappings.

Usage:
    python -m services.ingestion.build_icd_mapping \
        --mondo-sssom data/mondo_mappings.sssom.tsv \
        --neo4j-uri neo4j://localhost:7687 \
        --neo4j-password <password>
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/icd_mondo_mapping.json")


def load_sssom(path: Path) -> pd.DataFrame:
    """Load MONDO SSSOM TSV mappings file.

    SSSOM format: subject_id | predicate_id | object_id | ...
    We want rows where object_id starts with ICD10: or ICD10CM:
    """
    logger.info("Loading SSSOM from %s", path)

    # Skip comment lines (start with #)
    df = pd.read_csv(path, sep="\t", comment="#", low_memory=False)
    logger.info("Raw SSSOM rows: %d", len(df))

    # Filter to ICD-10 mappings
    icd_mask = df["object_id"].str.startswith("ICD10", na=False)
    df = df[icd_mask].copy()
    logger.info("ICD-10 mapping rows: %d", len(df))

    return df


def build_mapping(
    sssom_df: pd.DataFrame,
    neo4j_driver,
) -> list[dict]:
    """Build ICD-10 → MONDO → PrimeKG node mapping."""

    # Get all Disease nodes from Neo4j with their source IDs
    disease_map: dict[str, dict] = {}
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (d:Disease)
            RETURN elementId(d) AS neo4j_id, d.name AS name,
                   d.primekg_id AS primekg_id, d.source AS source
            """
        )
        for record in result:
            # PrimeKG diseases may have MONDO IDs in their source
            disease_map[str(record["primekg_id"])] = {
                "neo4j_id": record["neo4j_id"],
                "name": record["name"],
                "primekg_id": record["primekg_id"],
                "source": record["source"],
            }

    logger.info("Disease nodes in Neo4j: %d", len(disease_map))

    # Build mapping: ICD-10 → MONDO → PrimeKG
    mappings: list[dict] = []
    matched = 0
    unmatched = 0

    for _, row in sssom_df.iterrows():
        mondo_id = row["subject_id"]  # e.g., "MONDO:0005015"
        icd_code = row["object_id"]  # e.g., "ICD10CM:E11"

        # Clean ICD code
        icd_clean = icd_code.replace("ICD10CM:", "").replace("ICD10:", "")

        # Try to find matching PrimeKG disease
        # PrimeKG uses numeric MONDO IDs
        mondo_numeric = mondo_id.replace("MONDO:", "").lstrip("0")

        primekg_disease = disease_map.get(mondo_numeric)

        entry = {
            "icd10_code": icd_clean,
            "mondo_id": mondo_id,
            "mapping_confidence": "automated",
        }

        if primekg_disease:
            entry["primekg_node_id"] = primekg_disease["neo4j_id"]
            entry["disease_name"] = primekg_disease["name"]
            entry["primekg_id"] = primekg_disease["primekg_id"]
            matched += 1
        else:
            entry["primekg_node_id"] = None
            entry["disease_name"] = None
            entry["mapping_confidence"] = "unmapped"
            unmatched += 1

        mappings.append(entry)

    logger.info("Mapping complete: %d matched, %d unmapped", matched, unmatched)
    return mappings


def save_mapping(mappings: list[dict], output_path: Path) -> None:
    """Save mapping to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(mappings, f, indent=2)
    logger.info("Saved mapping to %s (%d entries)", output_path, len(mappings))

    # Print coverage stats
    total = len(mappings)
    mapped = sum(1 for m in mappings if m["primekg_node_id"] is not None)
    unmapped = total - mapped
    print(f"\n=== ICD-10 → PrimeKG Mapping Coverage ===")
    print(f"  Total ICD-10 codes:  {total}")
    print(f"  Mapped to PrimeKG:   {mapped} ({100 * mapped / total:.1f}%)")
    print(f"  Unmapped:            {unmapped} ({100 * unmapped / total:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ICD-10 → PrimeKG mapping")
    parser.add_argument(
        "--mondo-sssom", type=Path, required=True,
        help="Path to MONDO SSSOM TSV file",
    )
    parser.add_argument("--neo4j-uri", default="neo4j://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))

    sssom_df = load_sssom(args.mondo_sssom)
    mappings = build_mapping(sssom_df, driver)
    save_mapping(mappings, args.output)

    driver.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
