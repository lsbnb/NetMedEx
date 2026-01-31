from __future__ import annotations

"""
RAG (Retrieval-Augmented Generation) System for PubMed Abstracts

This module provides a RAG system that indexes PubMed abstracts into a vector database
and enables semantic search for relevant context during chat conversations.
"""

import logging
from dataclasses import dataclass
from typing import Any

from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


@dataclass
class AbstractDocument:
    """Represents a PubMed abstract as a RAG document"""

    pmid: str
    title: str
    abstract: str
    entities: list[dict[str, str]]  # Entity metadata from graph
    edges: list[dict[str, Any]]  # Edge information


class AbstractRAG:
    """RAG system for indexing and retrieving PubMed abstracts"""

    def __init__(self, llm_client, collection_name: str = "abstracts"):
        """
        Initialize the RAG system.

        Args:
            llm_client: LLM client with embeddings capability
            collection_name: Name for the vector database collection
        """
        self.llm_client = llm_client
        self.collection_name = collection_name
        self.documents: dict[str, AbstractDocument] = {}
        self.collection = None
        self._initialized = False

        try:
            import chromadb
            from chromadb.config import Settings

            # Initialize ChromaDB with ephemeral storage (in-memory for now)
            # Use a fresh client for each RAG instance to avoid cross-session pollution
            self.client = chromadb.Client(
                Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )

            # Setup embedding function if API key is available
            self.embedding_fn = None
            if self.llm_client.api_key and self.llm_client.api_key != "local-dummy-key":
                self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.llm_client.api_key,
                    model_name="text-embedding-3-small",  # Optimal for speed/cost
                )
                logger.info("OpenAI Embedding Function initialized")
            elif self.llm_client.base_url:
                # For local LLMs, we might need a different approach or fall back to default
                # ChromaDB's default uses Sentence Transformers locally
                logger.info("Local LLM detected, using ChromaDB default embeddings")

            logger.info("ChromaDB client initialized")
        except ImportError:
            logger.error("ChromaDB not installed. Please install: pip install chromadb")
            raise

    def index_abstracts(self, abstracts: list[AbstractDocument], progress_callback=None) -> int:
        """
        Index abstracts into the vector database.

        Args:
            abstracts: List of AbstractDocument objects to index
            progress_callback: Optional callback(message) for progress updates

        Returns:
            Number of documents indexed
        """
        if not abstracts:
            logger.warning("No abstracts to index")
            return 0

        try:
            # Reset collection if exists
            if self._initialized:
                self.client.reset()

            # Create new collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "PubMed abstracts for RAG"},
                embedding_function=self.embedding_fn,
            )

            # Prepare documents for indexing
            documents_text = []
            metadatas = []
            ids = []

            for doc in abstracts:
                # Combine title and abstract for better context
                full_text = f"{doc.title}\n\n{doc.abstract}"
                documents_text.append(full_text)

                # Store metadata
                metadatas.append(
                    {
                        "pmid": doc.pmid,
                        "title": doc.title,
                        "entity_count": str(len(doc.entities)),
                        "edge_count": str(len(doc.edges)),
                    }
                )

                ids.append(f"pmid_{doc.pmid}")

                # Store full document for retrieval
                self.documents[doc.pmid] = doc

            if progress_callback:
                progress_callback(f"Indexing {len(abstracts)} abstracts...")

            # Use OpenAI embeddings through ChromaDB's embedding function
            # ChromaDB will automatically handle the embedding
            self.collection.add(documents=documents_text, metadatas=metadatas, ids=ids)

            self._initialized = True
            logger.info(f"Indexed {len(abstracts)} abstracts successfully")

            if progress_callback:
                progress_callback(f"✅ Indexed {len(abstracts)} abstracts")

            return len(abstracts)

        except Exception as e:
            logger.error(f"Error indexing abstracts: {e}")
            raise

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """
        Search for relevant abstracts.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of (pmid, relevance_score) tuples
        """
        if not self._initialized or self.collection is None:
            logger.warning("RAG system not initialized")
            return []

        try:
            results = self.collection.query(query_texts=[query], n_results=top_k)

            # Extract PMIDs and scores
            pmid_scores = []
            if results["ids"] and results["distances"]:
                for doc_id, distance in zip(
                    results["ids"][0], results["distances"][0], strict=True
                ):
                    pmid = doc_id.replace("pmid_", "")
                    # Convert distance to similarity score (lower distance = higher similarity)
                    # ChromaDB uses L2 distance, so we invert it
                    similarity = 1.0 / (1.0 + distance)
                    pmid_scores.append((pmid, similarity))

            logger.info(f"Found {len(pmid_scores)} relevant abstracts for query")
            return pmid_scores

        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

    def get_context(self, query: str, top_k: int = 5) -> tuple[str, list[str]]:
        """
        Get formatted context for LLM prompt.

        Args:
            query: User query
            top_k: Number of abstracts to retrieve

        Returns:
            Tuple of (formatted_context, list of PMIDs used)
        """
        results = self.search(query, top_k=top_k)

        if not results:
            return "No relevant abstracts found.", []

        context_parts = []
        pmids_used = []

        for pmid, score in results:
            if pmid in self.documents:
                doc = self.documents[pmid]
                context_parts.append(
                    f"PMID: {pmid} (Relevance: {score:.2f})\n"
                    f"Title: {doc.title}\n"
                    f"Abstract: {doc.abstract}\n"
                )
                pmids_used.append(pmid)

        context = "\n---\n\n".join(context_parts)
        return context, pmids_used

    def get_document(self, pmid: str) -> AbstractDocument | None:
        """Get a specific document by PMID"""
        return self.documents.get(pmid)

    def get_all_pmids(self) -> list[str]:
        """Get list of all indexed PMIDs"""
        return list(self.documents.keys())

    def clear(self):
        """Clear the RAG system"""
        if self.client:
            self.client.reset()
        self.documents.clear()
        self.collection = None
        self._initialized = False
        logger.info("RAG system cleared")
