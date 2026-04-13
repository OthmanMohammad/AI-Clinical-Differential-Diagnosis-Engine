"""Verify ingestion — run after loading PrimeKG + Qdrant.

Checks node counts, edge counts, sample traversals, and Qdrant collection.

Usage:
    python -m services.ingestion.verify_ingestion
"""

from __future__ import annotations

import argparse
import logging
import sys

from neo4j import GraphDatabase
from qdrant_client import QdrantClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def verify_neo4j(driver) -> bool:
    """Verify Neo4j has the expected data."""
    ok = True

    with driver.session() as session:
        # Node counts
        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC"
        )
        print("\n=== Neo4j Node Counts ===")
        total_nodes = 0
        for record in result:
            print(f"  {record['label']}: {record['cnt']}")
            total_nodes += record["cnt"]
        print(f"  TOTAL: {total_nodes}")

        if total_nodes < 100:
            logger.error("Too few nodes: %d (expected 10k+)", total_nodes)
            ok = False

        # Edge counts
        result = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt ORDER BY cnt DESC"
        )
        print("\n=== Neo4j Edge Counts ===")
        total_edges = 0
        for record in result:
            print(f"  {record['type']}: {record['cnt']}")
            total_edges += record["cnt"]
        print(f"  TOTAL: {total_edges}")

        if total_edges < 100:
            logger.error("Too few edges: %d (expected 100k+)", total_edges)
            ok = False

        # Sample traversal
        print("\n=== Sample 2-Hop Traversal (from first Disease) ===")
        result = session.run(
            """
            MATCH (d:Disease)
            WITH d LIMIT 1
            MATCH (d)-[r1]->(h1)-[r2]->(h2)
            RETURN d.name AS start, type(r1) AS r1, h1.name AS hop1,
                   type(r2) AS r2, h2.name AS hop2
            LIMIT 5
            """
        )
        for record in result:
            print(
                f"  {record['start']} --[{record['r1']}]--> "
                f"{record['hop1']} --[{record['r2']}]--> {record['hop2']}"
            )

    return ok


def verify_qdrant(client: QdrantClient, collection: str = "medical_entities") -> bool:
    """Verify Qdrant collection has data."""
    ok = True

    try:
        info = client.get_collection(collection)
        print(f"\n=== Qdrant Collection: {collection} ===")
        print(f"  Points: {info.points_count}")
        print(f"  Status: {info.status}")

        if info.points_count < 100:
            logger.error("Too few points: %d (expected 10k+)", info.points_count)
            ok = False

        # Sample search
        from fastembed import TextEmbedding
        embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        test_embedding = list(embedder.embed(["chest pain"]))[0].tolist()

        results = client.search(
            collection_name=collection,
            query_vector=test_embedding,
            limit=5,
        )
        print("\n=== Sample Search: 'chest pain' ===")
        for r in results:
            print(f"  {r.payload.get('name', '?')} (score: {r.score:.3f})")

    except Exception as exc:
        logger.error("Qdrant verification failed: %s", exc)
        ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ingestion")
    parser.add_argument("--neo4j-uri", default="neo4j://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--qdrant-api-key", default="")
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    qdrant = QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key or None)

    neo4j_ok = verify_neo4j(driver)
    qdrant_ok = verify_qdrant(qdrant)

    driver.close()

    print("\n=== Verification Summary ===")
    print(f"  Neo4j:  {'PASS' if neo4j_ok else 'FAIL'}")
    print(f"  Qdrant: {'PASS' if qdrant_ok else 'FAIL'}")

    if not (neo4j_ok and qdrant_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
