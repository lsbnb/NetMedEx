from __future__ import annotations

"""
RAG System for Knowledge Graph Nodes

This module provides a specialized RAG system that indexes graph nodes (entities)
into a vector database to enable semantic search by node name/concept.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """Represents a Graph Node for RAG indexing"""

    node_id: str
    name: str
    type: str
    metadata: dict[str, Any]


class NodeRAG:
    """RAG system for indexing and retrieving Graph Nodes"""

    def __init__(
        self, llm_client, collection_name: str = "graph_nodes", persist_directory: str = None
    ):
        """
        Initialize the Node RAG system.

        Args:
            llm_client: LLM client with embeddings capability
            collection_name: Name for the vector database collection
            persist_directory: Optional directory for persistent storage
        """
        self.llm_client = llm_client
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.collection = None
        self._initialized = False

        try:
            import chromadb
            from chromadb.config import Settings

            if persist_directory:
                # Initialize persistent ChromaDB
                import os

                if not os.path.exists(persist_directory):
                    os.makedirs(persist_directory, exist_ok=True)

                self.client = chromadb.PersistentClient(
                    path=persist_directory,
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ),
                )
                logger.info(f"NodeRAG: Persistent ChromaDB initialized at {persist_directory}")
            else:
                # Initialize ChromaDB with ephemeral storage
                self.client = chromadb.Client(
                    Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    )
                )
                logger.info("NodeRAG: Ephemeral ChromaDB client initialized")

            # Standardize to ChromaDB default embeddings
            self.embedding_fn = None
        except ImportError:
            logger.error("ChromaDB not installed.")
            raise

    def index_nodes(self, nodes: list[GraphNode], progress_callback=None) -> int:
        """
        Index graph nodes into the vector database.

        Args:
            nodes: List of GraphNode objects to index
            progress_callback: Optional callback(message)

        Returns:
            Number of nodes indexed
        """
        if not nodes:
            logger.warning("No nodes to index")
            return 0

        try:
            # Create or get collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Graph nodes for semantic search"},
                embedding_function=self.embedding_fn,
            )

            # Check if already indexed (for persistent storage)
            if self.persist_directory:
                count = self.collection.count()
                if count > 0:
                    logger.info(
                        f"NodeRAG: Found {count} existing records in persistent collection. Skipping re-index."
                    )
                    self._initialized = True
                    if progress_callback:
                        progress_callback(f"✅ Loaded {count} nodes from cache")
                    return count

            # Reset collection if exists for a fresh start with the current graph (only for ephemeral)
            if not self.persist_directory and self._initialized:
                self.client.reset()
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "Graph nodes for semantic search"},
                    embedding_function=self.embedding_fn,
                )

            documents_text = []
            metadatas = []
            ids = []

            for node in nodes:
                # Embed the node name.
                # We could potentially include type or description, but name is primary.
                # Adding type helps differentiate same-named entities of different types.
                text_content = f"{node.name} ({node.type})"
                documents_text.append(text_content)

                # Store metadata
                meta = {
                    "node_id": node.node_id,
                    "name": node.name,
                    "type": node.type,
                }
                # Merge additional metadata if it's flat/compatible
                # Check for incompatible types before merging if needed.
                # For now, keep it simple.

                metadatas.append(meta)
                ids.append(f"node_{node.node_id}")

            if progress_callback:
                progress_callback(f"Indexing {len(nodes)} graph nodes...")

            try:
                self.collection.add(documents=documents_text, metadatas=metadatas, ids=ids)
            except Exception as e:
                raise e

            self._initialized = True
            logger.info(f"Indexed {len(nodes)} nodes successfully")

            if progress_callback:
                progress_callback(f"✅ Indexed {len(nodes)} nodes")

            return len(nodes)

        except Exception as e:
            logger.error(f"Error indexing nodes: {e}")
            raise

    def search_nodes(self, query: str, top_k: int = 10) -> list[tuple[str, float, dict]]:
        """
        Search for relevant nodes by semantic similarity.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of (node_id, relevance_score, metadata) tuples
        """
        if not self._initialized or self.collection is None:
            logger.warning("NodeRAG not initialized")
            return []

        try:
            results = self.collection.query(query_texts=[query], n_results=top_k)

            hits = []
            if results["ids"] and results["distances"]:
                ids = results["ids"][0]
                distances = results["distances"][0]
                metadatas = results["metadatas"][0]

                # Safe zip handling
                for doc_id, distance, meta in zip(ids, distances, metadatas):
                    node_id = doc_id.replace("node_", "")
                    # Invert distance to score
                    similarity = 1.0 / (1.0 + distance)
                    hits.append((node_id, similarity, meta))

            logger.info(f"Found {len(hits)} relevant nodes for query: '{query}'")
            return hits

        except Exception as e:
            logger.error(f"Error during node search: {e}")
            return []

    def is_indexed(self) -> bool:
        """Check if the vector collection is already populated"""
        if not self.persist_directory:
            return self._initialized
        
        try:
            # Re-initialize collection if needed
            if self.collection is None:
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "Graph nodes for semantic search"},
                    embedding_function=self.embedding_fn,
                )
            
            count = self.collection.count()
            return count > 0
        except Exception:
            return False

    def clear(self):
        """Clear the RAG system"""
        if self.client:
            self.client.reset()
        self.collection = None
        self._initialized = False
        logger.info("NodeRAG system cleared")
