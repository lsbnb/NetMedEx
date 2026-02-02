from __future__ import annotations

"""
Chat system for conversational analysis of PubMed abstracts using RAG

This module manages chat sessions and coordinates between the RAG system
and LLM to provide contextualized responses.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import re

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents a single chat message"""

    role: str  # "user" or "assistant"
    content: str
    sources: list[str] | None = None  # PMIDs for assistant messages
    timestamp: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "role": self.role,
            "content": self.content,
            "sources": self.sources,
            "timestamp": self.timestamp,
        }


class ChatSession:
    """Manages a conversation with RAG-augmented context"""

    def __init__(self, rag_system, llm_client, graph_retriever=None, max_history: int = 10):
        """
        Initialize chat session.

        Args:
            rag_system: AbstractRAG instance
            llm_client: LLM client for chat
            graph_retriever: GraphRetriever instance (optional)
            max_history: Maximum conversation history to retain
        """
        self.rag = rag_system
        self.llm = llm_client
        self.graph_retriever = graph_retriever
        self.max_history = max_history
        self.history: list[ChatMessage] = []

        # System prompt for biomedical context
        self.system_prompt = """You are a helpful biomedical research assistant analyzing scientific literature.

You have access to two types of context:
1. Scientific Abstracts (Text): Unstructured details selected by the user.
2. Knowledge Graph (Structure): Structured entity relationships and paths.

Your task is to answer questions by SYNTHESIZING these two sources.
- Use Graph Structure to identify logical connections and multi-hop relationships.
- Use Abstracts to provide specific experimental evidence and context.

Guidelines:
1. Always base your answers on the provided context.
2. Cite specific PMIDs when making claims using the format: [PMID:XXXXXXXX]. You can find PMIDs in both the Graph Structure (e.g., "[type [PMID:123]]") and Abstracts.
3. If the context doesn't contain relevant information, say so clearly.
4. Be concise but informative.
5. Use scientific terminology appropriately.
6. Highlight key findings and relationships between entities.
7. If multiple papers support a claim, cite all of them.

Format your responses clearly and include PMID citations like this: [PMID:12345678]"""

    def send_message(self, user_message: str, top_k: int = 5) -> dict[str, Any]:
        """
        Process user message and generate AI response.

        Args:
            user_message: User's question
            top_k: Number of abstracts to retrieve for context

        Returns:
            Dictionary with response and metadata
        """
        try:
            # Add user message to history
            user_msg = ChatMessage(role="user", content=user_message)
            self.history.append(user_msg)

            # 1. Retrieve Text Context (RAG)
            # Optimization: If we have a small number of documents (<= 20),
            # just use all of them instead of vector search. This handles
            # "summarize all" queries much better.
            total_docs = len(self.rag.documents)
            if total_docs <= 20:
                logger.info(f"Small document set ({total_docs}), using all abstracts for context")
                pmids_used = list(self.rag.documents.keys())
                context_parts = []
                for pmid in pmids_used:
                    doc = self.rag.documents[pmid]
                    context_parts.append(
                        f"PMID: {pmid}\nTitle: {doc.title}\nAbstract: {doc.abstract}\n"
                    )
                text_context = "\n---\n\n".join(context_parts)
            else:
                # Use vector search for larger sets
                text_context, pmids_used = self.rag.get_context(user_message, top_k=top_k)

            # 2. Retrieve Graph Context (Structure)
            graph_context = ""
            if self.graph_retriever:
                logger.info("Retrieving graph context...")
                relevant_nodes = self.graph_retriever.find_relevant_nodes(user_message)
                if relevant_nodes:
                    graph_context = self.graph_retriever.get_subgraph_context(relevant_nodes)
                    logger.info(f"Found {len(relevant_nodes)} relevant nodes in graph")
                else:
                    logger.info("No relevant nodes found in graph query")

            # Build conversation history for LLM
            messages = self._build_messages(user_message, text_context, graph_context)

            # Call LLM
            logger.info(f"Sending chat request with {len(pmids_used)} context documents")
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=messages,
                temperature=0.3,  # Lower temperature for factual responses
                max_tokens=1000,
            )

            assistant_content = response.choices[0].message.content.strip()

            # Parse citations from response to filter sources
            # Matches identifiers like: PMID:123456, [PMID:123456], PMID: 123456
            cited_pmids = set(re.findall(r"PMID:?\s*(\d+)", assistant_content, re.IGNORECASE))

            # Filter pmids_used to only include those actually cited
            final_sources = [p for p in pmids_used if p in cited_pmids]

            # Create assistant message with sources
            assistant_msg = ChatMessage(
                role="assistant", content=assistant_content, sources=final_sources
            )
            self.history.append(assistant_msg)

            # Trim history if needed
            self._trim_history()

            logger.info("Chat response generated successfully")

            return {
                "success": True,
                "message": assistant_content,
                "sources": final_sources,
                "context_count": len(pmids_used),
            }

        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Sorry, I encountered an error processing your request.",
            }

    def _build_messages(
        self, user_message: str, text_context: str, graph_context: str = ""
    ) -> list[dict]:
        """Build message list for LLM API call"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add recent conversation history (excluding current message)
        for msg in self.history[-(self.max_history - 1) :]:
            if msg.role != "system":  # Don't include system messages
                messages.append({"role": msg.role, "content": msg.content})

        # Add current message with Hybrid RAG context
        current_message = f"""Context 1: Knowledge Graph Structure (Logic & Paths):
{graph_context if graph_context else "No specific structural context found."}

---

Context 2: Scientific Abstracts (Details & Evidence):
{text_context}

---

User question: {user_message}

Please answer based on the context provided above."""

        messages.append({"role": "user", "content": current_message})

        return messages

    def _trim_history(self):
        """Trim conversation history to max length"""
        if len(self.history) > self.max_history:
            # Keep the most recent messages
            self.history = self.history[-self.max_history :]
            logger.debug(f"Trimmed chat history to {self.max_history} messages")

    def get_history(self) -> list[dict]:
        """Get conversation history as list of dictionaries"""
        return [msg.to_dict() for msg in self.history]

    def clear(self):
        """Clear conversation history"""
        self.history.clear()
        logger.info("Chat history cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the chat session"""
        return {
            "message_count": len(self.history),
            "user_messages": sum(1 for msg in self.history if msg.role == "user"),
            "assistant_messages": sum(1 for msg in self.history if msg.role == "assistant"),
            "indexed_pmids": len(self.rag.get_all_pmids()) if self.rag else 0,
        }
