import os
import logging
from qdrant_client import models
from core.config import (
    openai_client,
    qdrant_client,
    COLLECTION_NAME,
    QDRANT_URL,
    QDRANT_VECTOR_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger("Sleuth.VectorStore")


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Create OpenAI embeddings that match the Qdrant Cloud collection."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


def _point_vector(embedding: list[float]):
    return {QDRANT_VECTOR_NAME: embedding}


def _ensure_collection() -> None:
    if qdrant_client.collection_exists(COLLECTION_NAME):
        return

    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            QDRANT_VECTOR_NAME: models.VectorParams(
                size=EMBEDDING_DIMENSIONS,
                distance=models.Distance.COSINE,
            )
        },
    )


def get_qdrant_status() -> dict:
    """
    Returns a health dict for the Qdrant vector store.
    {
        "reachable": bool,
        "collection_exists": bool,
        "error": str | None   -- human-readable error message
    }
    """
    try:
        # A lightweight ping: just list collections.
        qdrant_client.get_collections()
    except Exception as e:
        return {
            "reachable": False,
            "collection_exists": False,
            "error": (
                "Cannot reach Qdrant. Check QDRANT_URL and QDRANT_API_KEY. "
                f"Configured URL: {QDRANT_URL}. Detail: {type(e).__name__}."
            ),
        }

    try:
        collection_exists = qdrant_client.collection_exists(COLLECTION_NAME)
        points_count = 0
        if collection_exists:
            points_count = qdrant_client.count(
                collection_name=COLLECTION_NAME,
                exact=True,
            ).count
        return {
            "reachable": True,
            "collection_exists": collection_exists,
            "points_count": points_count,
            "collection_name": COLLECTION_NAME,
            "embedding_model": EMBEDDING_MODEL,
            "error": None if collection_exists else (
                f"Qdrant is reachable but the collection '{COLLECTION_NAME}' does not exist. "
                "Click 'Sync Evidence Locker' to index your evidence files."
            ),
        }
    except Exception as e:
        return {
            "reachable": True,
            "collection_exists": False,
            "points_count": 0,
            "collection_name": COLLECTION_NAME,
            "embedding_model": EMBEDDING_MODEL,
            "error": f"Qdrant reachable but collection check failed: {type(e).__name__}.",
        }



def index_evidence_to_qdrant():
    """Reads the evidence folder and stores documents as vectors in Qdrant."""
    base_path = "data/demo_data/evidence"
    documents = []
    payloads = []
    points = []
    
    for root, dirs, files in os.walk(base_path):
        dirs.sort()
        for file in sorted(files):
            if file.endswith(".txt"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(content)
                    payloads.append({
                        "filename": filepath,
                        "source": file,
                        "text": content,
                    })

    if not documents:
        logger.warning("No documents found to index.")
        return 0

    _ensure_collection()
    logger.info(f"Embedding and indexing {len(documents)} documents into Qdrant...")

    embeddings = _embed_texts(documents)
    for idx, (embedding, payload) in enumerate(zip(embeddings, payloads), start=1):
        points.append(
            models.PointStruct(
                id=idx,
                vector=_point_vector(embedding),
                payload=payload,
            )
        )

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )
    logger.info("Indexing complete.")
    return len(points)

def search_evidence(inv_id, entity, variance):
    """Performs a semantic vector search for relevant evidence."""
    # We craft a search query that looks for the semantic meaning of the discrepancy
    search_query = f"Explanation or notice regarding invoice {inv_id}, entity {entity}, or an amount of {abs(variance)}"
    
    logger.info(f"Querying Qdrant: '{search_query}'")
    
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        logger.warning("Collection not found. Index evidence before searching.")
        return []

    query_embedding = _embed_texts([search_query])[0]

    # Retrieve the top 3 most semantically similar documents.
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        using=QDRANT_VECTOR_NAME,
        limit=3,
        with_payload=True,
    ).points
    
    relevant_evidence = []
    for hit in results:
        payload = hit.payload or {}
        text = payload.get("text", "")
        filename = payload.get("filename", payload.get("source", "Evidence Locker"))
        if hit.score > 0.50: 
            relevant_evidence.append(f"--- SOURCE FILE: {filename} ---\n{text}")
            logger.info(f"Vector Match Found: {filename} (Score: {hit.score:.2f})")
            
    return relevant_evidence