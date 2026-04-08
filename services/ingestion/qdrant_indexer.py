"""Qdrant Indexer — embed PrimeKG nodes and upload to Qdrant Cloud.

Embeds all Disease + Symptom + Phenotype nodes from Neo4j using fastembed,
then uploads to Qdrant Cloud free tier.

Usage:
    python -m services.ingestion.qdrant_indexer
"""

from __future__ import annotations

import argparse
import logging

from fastembed import TextEmbedding
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COLLECTION_NAME = "medical_entities"
BATCH_SIZE = 100


def fetch_nodes(driver, labels: list[str]) -> list[dict]:
    """Fetch nodes from Neo4j for embedding."""
    nodes = []
    with driver.session() as session:
        for label in labels:
            result = session.run(
                f"""
                MATCH (n:{label})
                RETURN elementId(n) AS id, n.name AS name, n.type AS type,
                       labels(n)[0] AS label
                """
            )
            for record in result:
                if record["name"]:
                    nodes.append({
                        "neo4j_id": record["id"],
                        "name": record["name"],
                        "type": record["type"] or record["label"],
                        "label": record["label"],
                    })
    logger.info("Fetched %d nodes from Neo4j", len(nodes))
    return nodes


def embed_and_upload(
    nodes: list[dict],
    qdrant: QdrantClient,
    model_name: str = "BAAI/bge-small-en-v1.5",
) -> None:
    """Embed node names and upload to Qdrant."""
    logger.info("Loading embedding model: %s", model_name)
    embedder = TextEmbedding(model_name=model_name)

    # Get embedding dimension
    test_emb = list(embedder.embed(["test"]))[0]
    dim = len(test_emb)
    logger.info("Embedding dimension: %d", dim)

    # Create or recreate collection
    try:
        qdrant.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    logger.info("Created Qdrant collection: %s", COLLECTION_NAME)

    # Embed and upload in batches
    texts = [n["name"] for n in nodes]
    all_embeddings = list(tqdm(embedder.embed(texts), total=len(texts), desc="Embedding"))

    points = []
    for i, (node, embedding) in enumerate(zip(nodes, all_embeddings)):
        points.append(
            PointStruct(
                id=i,
                vector=embedding.tolist(),
                payload={
                    "neo4j_id": node["neo4j_id"],
                    "name": node["name"],
                    "type": node["type"],
                    "label": node["label"],
                },
            )
        )

    # Upload in batches
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant.upsert(collection_name=COLLECTION_NAME, points=batch)
        if (i + BATCH_SIZE) % 1000 < BATCH_SIZE:
            logger.info("Uploaded %d/%d points", min(i + BATCH_SIZE, len(points)), len(points))

    logger.info("Upload complete: %d points", len(points))


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed PrimeKG nodes → Qdrant")
    parser.add_argument("--neo4j-uri", default="neo4j://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--qdrant-api-key", default="")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    args = parser.parse_args()

    neo4j_driver = GraphDatabase.driver(
        args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)
    )

    qdrant = QdrantClient(
        url=args.qdrant_url,
        api_key=args.qdrant_api_key or None,
    )

    # Fetch Disease, Symptom, and Phenotype nodes for embedding
    nodes = fetch_nodes(neo4j_driver, ["Disease", "Symptom", "Phenotype"])

    embed_and_upload(nodes, qdrant, model_name=args.model)

    neo4j_driver.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
