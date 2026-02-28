import os
import logging
from core.config import qdrant_client, COLLECTION_NAME

logger = logging.getLogger("Sleuth.VectorStore")

def index_evidence_to_qdrant():
    """Reads the evidence folder and stores documents as vectors in Qdrant."""
    base_path = "data/demo_data/evidence"
    documents = []
    metadata = []
    ids = []
    
    doc_id = 1
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(".txt"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(content)
                    metadata.append({"filename": filepath, "source": file})
                    ids.append(doc_id)
                    doc_id += 1

    if not documents:
        logger.warning("No documents found to index.")
        return

    logger.info(f"Indexing {len(documents)} documents into Qdrant...")
    
    # Qdrant's add() automatically handles embedding generation using fastembed!
    qdrant_client.add(
        collection_name=COLLECTION_NAME,
        documents=documents,
        metadata=metadata,
        ids=ids
    )
    logger.info("Indexing complete.")

def search_evidence(inv_id, entity, variance):
    """Performs a semantic vector search for relevant evidence."""
    # We craft a search query that looks for the semantic meaning of the discrepancy
    search_query = f"Explanation or notice regarding invoice {inv_id}, entity {entity}, or an amount of {abs(variance)}"
    
    logger.info(f"Querying Qdrant: '{search_query}'")
    
    # Check if collection exists first
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        logger.warning("Collection not found. Indexing files first...")
        index_evidence_to_qdrant()

    # Retrieve the top 3 most semantically similar documents
    results = qdrant_client.query(
        collection_name=COLLECTION_NAME,
        query_text=search_query,
        limit=3 
    )
    
    relevant_evidence = []
    for hit in results:
        # We only pass documents that have a reasonable similarity score
        # (FastEmbed scores usually range between 0.5 and 1.0 for good matches)
        if hit.score > 0.50: 
            relevant_evidence.append(f"--- SOURCE FILE: {hit.metadata['filename']} ---\n{hit.document}")
            logger.info(f"Vector Match Found: {hit.metadata['filename']} (Score: {hit.score:.2f})")
            
    return relevant_evidence