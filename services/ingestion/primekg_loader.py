"""PrimeKG → Neo4j Loader.

Loads the curated clinical subset of PrimeKG into Neo4j AuraDB Free.
Filters to ~30k nodes, ~200k edges that fit within AuraDB Free limits
(200k nodes, 400k relationships).

Usage:
    python -m services.ingestion.primekg_loader --primekg-path data/primekg.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Node types to keep — clinically relevant for differential diagnosis.
#
# IMPORTANT: these are the raw strings used in PrimeKG's `x_type` / `y_type`
# columns, which are NOT always the same as the short names used in the
# `relation` column. Specifically PrimeKG labels phenotype nodes with the
# type "effect/phenotype", even though relations involving them use the
# short name ("disease_phenotype_positive", etc.). Using "phenotype" here
# would silently drop every phenotype node and every disease-phenotype
# edge during the node type filter — which is exactly what happened on
# the first ingest.
ALLOWED_NODE_TYPES = {
    "disease",
    "drug",
    "gene/protein",
    "effect/phenotype",
}

# Edge types to keep — clinically relevant relationships
ALLOWED_EDGE_TYPES = {
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "disease_protein",
    "drug_protein",
    "disease_disease",
    "phenotype_phenotype",
}

# Neo4j label mapping (PrimeKG raw type → clean Neo4j label).
# The keys MUST match ALLOWED_NODE_TYPES exactly.
NODE_LABEL_MAP = {
    "disease": "Disease",
    "drug": "Drug",
    "gene/protein": "Gene",
    "effect/phenotype": "Phenotype",
}

BATCH_SIZE = 2000


def load_primekg_csv(path: Path) -> pd.DataFrame:
    """Load the PrimeKG CSV file."""
    logger.info("Loading PrimeKG from %s", path)
    df = pd.read_csv(path, low_memory=False)
    logger.info("Raw PrimeKG: %d edges", len(df))
    return df


def filter_subset(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to the clinical core subset."""
    # Filter edge types
    df = df[df["relation"].isin(ALLOWED_EDGE_TYPES)].copy()
    logger.info("After edge type filter: %d edges", len(df))

    # Filter node types
    df = df[
        df["x_type"].isin(ALLOWED_NODE_TYPES) & df["y_type"].isin(ALLOWED_NODE_TYPES)
    ].copy()
    logger.info("After node type filter: %d edges", len(df))

    return df


def extract_nodes(df: pd.DataFrame) -> pd.DataFrame:
    """Extract unique nodes from edges."""
    source_nodes = df[["x_index", "x_type", "x_name", "x_source"]].rename(
        columns={"x_index": "id", "x_type": "type", "x_name": "name", "x_source": "source"}
    )
    target_nodes = df[["y_index", "y_type", "y_name", "y_source"]].rename(
        columns={"y_index": "id", "y_type": "type", "y_name": "name", "y_source": "source"}
    )
    nodes = pd.concat([source_nodes, target_nodes]).drop_duplicates(subset=["id"])
    logger.info("Unique nodes: %d", len(nodes))
    return nodes


def create_constraints(driver) -> None:
    """Create uniqueness constraints for each node label."""
    with driver.session() as session:
        for label in NODE_LABEL_MAP.values():
            try:
                session.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.primekg_id IS UNIQUE"
                )
                logger.info("Constraint created for %s", label)
            except Exception as exc:
                logger.warning("Constraint for %s: %s", label, exc)


def load_nodes(driver, nodes: pd.DataFrame) -> None:
    """Load nodes into Neo4j in batches."""
    for node_type, group in nodes.groupby("type"):
        label = NODE_LABEL_MAP.get(node_type, "Entity")
        records = group.to_dict("records")

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            with driver.session() as session:
                session.run(
                    f"""
                    UNWIND $batch AS row
                    MERGE (n:{label} {{primekg_id: row.id}})
                    SET n.name = row.name, n.source = row.source, n.type = '{node_type}'
                    """,
                    batch=batch,
                )
            logger.info(
                "Loaded %s nodes: %d/%d", label, min(i + BATCH_SIZE, len(records)), len(records)
            )


def load_edges(driver, df: pd.DataFrame) -> None:
    """Load edges into Neo4j in batches, grouped by (relation, source_type,
    target_type) so the MATCH clauses can specify a label and use the
    per-label uniqueness index directly.

    Without labels in the MATCH, Neo4j has to probe every label's
    primekg_id index for each lookup, which makes ingestion ~100x
    slower. With labels, each lookup is O(1).
    """
    total_loaded = 0
    total_edges = len(df)

    # Group by (relation, src_type, tgt_type) so we can emit queries with
    # the right labels on each side. A single edge type can connect pairs
    # of different types (e.g. disease_protein links Disease <-> Gene).
    grouped = df.groupby(["relation", "x_type", "y_type"])

    with driver.session() as session:
        for (rel_type, src_type, tgt_type), group in grouped:
            src_label = NODE_LABEL_MAP.get(src_type, "Entity")
            tgt_label = NODE_LABEL_MAP.get(tgt_type, "Entity")
            records = group[["x_index", "y_index"]].to_dict("records")
            logger.info(
                "Loading edges: %s (%s -> %s, %d edges)",
                rel_type, src_label, tgt_label, len(records),
            )

            # Compile the query once per group — reused across batches.
            query = (
                "UNWIND $batch AS row "
                f"MATCH (a:{src_label} {{primekg_id: row.x_index}}) "
                f"MATCH (b:{tgt_label} {{primekg_id: row.y_index}}) "
                f"MERGE (a)-[:{rel_type}]->(b)"
            )

            for i in range(0, len(records), BATCH_SIZE):
                batch = records[i : i + BATCH_SIZE]
                session.run(query, batch=batch)
                total_loaded += len(batch)

                if total_loaded % 20000 < BATCH_SIZE:
                    logger.info(
                        "Loaded edges: %d/%d (current: %s)",
                        total_loaded, total_edges, rel_type,
                    )

    logger.info("All edges loaded: %d", total_loaded)


def print_summary(driver) -> None:
    """Print ingestion summary."""
    with driver.session() as session:
        result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count")
        print("\n=== Node Counts ===")
        for record in result:
            print(f"  {record['label']}: {record['count']}")

        result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count")
        print("\n=== Edge Counts ===")
        for record in result:
            print(f"  {record['type']}: {record['count']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load PrimeKG subset into Neo4j")
    parser.add_argument("--primekg-path", type=Path, required=True, help="Path to primekg.csv")
    parser.add_argument("--neo4j-uri", default="neo4j://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()

    if not args.primekg_path.exists():
        logger.error("PrimeKG file not found: %s", args.primekg_path)
        sys.exit(1)

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))

    if args.clear:
        logger.warning("Clearing all existing data...")
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    df = load_primekg_csv(args.primekg_path)
    df = filter_subset(df)
    nodes = extract_nodes(df)

    logger.info("Creating constraints...")
    create_constraints(driver)

    logger.info("Loading nodes...")
    load_nodes(driver, nodes)

    logger.info("Loading edges...")
    load_edges(driver, df)

    print_summary(driver)
    driver.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
