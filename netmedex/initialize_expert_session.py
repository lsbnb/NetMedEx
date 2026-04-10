import os
import json
import logging
from netmedex.pubtator_parser import PubTatorIO
from netmedex.rag import AbstractRAG

# Configure paths for the pediatric expert edition
SESSION_DIR = "/home/cylin/NetMedEx/data/pediatric_10k"
JSON_PATH = os.path.join(SESSION_DIR, "pubtator.json")
CHROMA_PATH = os.path.join(SESSION_DIR, "chroma")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_pediatric_10k():
    if not os.path.exists(JSON_PATH):
        logger.error(f"Data missing at {JSON_PATH}")
        return

    logger.info("Initializing Pediatric 10k Expert Session...")

    # 1. Load Collection
    collection = PubTatorIO.parse(JSON_PATH)
    logger.info(f"Loaded {len(collection.articles)} articles for indexing.")

    # 2. Initialize RAG with persistent storage in the session dir
    # We use the session-specific chroma path to keep it isolated
    rag = AbstractRAG(persist_directory=CHROMA_PATH)
    
    # 3. Add to index if not already present
    # Check if we have documents indexed
    indexed_pmids = rag.get_all_pmids()
    if len(indexed_pmids) < len(collection.articles):
        logger.info(f"Indexing {len(collection.articles)} abstracts. This might take a few minutes...")
        # Add articles to RAG
        for article in collection.articles:
            rag.add_article(article)
        logger.info("Indexing complete.")
    else:
        logger.info("10k index already exists and is healthy.")

if __name__ == "__main__":
    initialize_pediatric_10k()
