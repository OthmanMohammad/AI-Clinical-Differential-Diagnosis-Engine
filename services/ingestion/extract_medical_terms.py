"""Extract Medical Terms from PrimeKG nodes.

Extracts all unique node names from Neo4j → data/medical_terms.json.
Used by Gate 2.3 (medical relevance check) at API startup.

Usage:
    python -m services.ingestion.extract_medical_terms
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/medical_terms.json")


def extract_terms(driver) -> list[str]:
    """Extract all unique node names from Neo4j."""
    terms: set[str] = set()

    with driver.session() as session:
        result = session.run(
            """
            MATCH (n)
            WHERE n.name IS NOT NULL
            RETURN DISTINCT toLower(n.name) AS name
            """
        )
        for record in result:
            name = record["name"].strip()
            if name and len(name) >= 2:
                terms.add(name)

    logger.info("Extracted %d unique medical terms", len(terms))
    return sorted(terms)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract medical terms from Neo4j")
    parser.add_argument("--neo4j-uri", default="neo4j://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    terms = extract_terms(driver)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(terms, f, indent=2)

    logger.info("Saved %d terms to %s", len(terms), args.output)
    driver.close()


if __name__ == "__main__":
    main()
