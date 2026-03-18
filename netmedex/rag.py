from __future__ import annotations

"""
RAG (Retrieval-Augmented Generation) System for PubMed Abstracts

This module provides a RAG system that indexes PubMed abstracts into a vector database
and enables semantic search for relevant context during chat conversations.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Maximum tokens allowed per embedding request (OpenAI limit is 300k; use 250k as buffer)
_MAX_TOKENS_PER_BATCH = 250_000


def _count_tokens(text: str) -> int:
    """Return an approximate token count for *text* using tiktoken when available.

    Falls back to a simple word-count heuristic (÷0.75) if tiktoken is not
    installed so the function never raises an ImportError at runtime.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Rough heuristic: ~0.75 words per token on average
        return int(len(text.split()) / 0.75) + 1


def _build_token_batches(
    documents_text: list[str],
    metadatas: list[dict],
    ids: list[str],
    max_tokens: int = _MAX_TOKENS_PER_BATCH,
) -> list[tuple[list[str], list[dict], list[str]]]:
    """Split documents into batches that each stay under *max_tokens* tokens.

    Returns a list of (texts, metadatas, ids) tuples ready to be passed to
    ``collection.add()``.
    """
    batches: list[tuple[list[str], list[dict], list[str]]] = []
    cur_texts: list[str] = []
    cur_metas: list[dict] = []
    cur_ids: list[str] = []
    cur_tokens = 0

    for text, meta, doc_id in zip(documents_text, metadatas, ids):
        tokens = _count_tokens(text)
        if cur_tokens + tokens > max_tokens and cur_texts:
            batches.append((cur_texts, cur_metas, cur_ids))
            cur_texts, cur_metas, cur_ids = [], [], []
            cur_tokens = 0
        cur_texts.append(text)
        cur_metas.append(meta)
        cur_ids.append(doc_id)
        cur_tokens += tokens

    if cur_texts:
        batches.append((cur_texts, cur_metas, cur_ids))

    return batches


@dataclass
class AbstractDocument:
    """Represents a PubMed abstract as a RAG document"""

    pmid: str
    title: str
    abstract: str
    entities: list[dict[str, str]]  # Entity metadata from graph
    edges: list[dict[str, Any]]  # Edge information
    weight: float = 1.0  # Citation-based weight


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

            # Standardize to ChromaDB default embeddings for all providers.
            # This avoids provider-specific embedding endpoint compatibility issues.
            self.embedding_fn = None
            logger.info("Using ChromaDB default embeddings")

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
                        "weight": str(doc.weight),
                    }
                )

                ids.append(f"pmid_{doc.pmid}")

                # Store full document for retrieval
                self.documents[doc.pmid] = doc

            if progress_callback:
                progress_callback(f"Indexing {len(abstracts)} abstracts...")

            # Split into token-aware batches to respect the 300k tokens/request limit.
            batches = _build_token_batches(documents_text, metadatas, ids)
            total_batches = len(batches)
            logger.info(
                f"Splitting {len(abstracts)} abstracts into {total_batches} batch(es) "
                f"(max {_MAX_TOKENS_PER_BATCH:,} tokens each)"
            )

            try:
                for batch_idx, (batch_texts, batch_metas, batch_ids) in enumerate(
                    batches, start=1
                ):
                    logger.info(
                        f"Sending batch {batch_idx}/{total_batches} "
                        f"({len(batch_texts)} docs) to vector store..."
                    )
                    self.collection.add(
                        documents=batch_texts,
                        metadatas=batch_metas,
                        ids=batch_ids,
                    )
                    if progress_callback:
                        progress_callback(
                            f"Indexed batch {batch_idx}/{total_batches} "
                            f"({len(batch_texts)} abstracts)..."
                        )
            except Exception as e:
                raise e

            self._initialized = True
            logger.info(
                f"Indexed {len(abstracts)} abstracts successfully in {total_batches} batch(es)"
            )

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

                    # Apply weight boost if available
                    weight = 1.0
                    doc = self.documents.get(pmid)
                    if doc:
                        weight = doc.weight

                    # Hybrid score: semantic similarity boosted by citation weight
                    hybrid_score = similarity * weight
                    pmid_scores.append((pmid, hybrid_score))

            # Sort by hybrid score descending
            pmid_scores.sort(key=lambda x: x[1], reverse=True)

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
