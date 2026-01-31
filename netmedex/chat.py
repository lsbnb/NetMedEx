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

    def __init__(self, rag_system, llm_client, max_history: int = 10):
        """
        Initialize chat session.

        Args:
            rag_system: AbstractRAG instance
            llm_client: LLM client for chat
            max_history: Maximum conversation history to retain
        """
        self.rag = rag_system
        self.llm = llm_client
        self.max_history = max_history
        self.history: list[ChatMessage] = []

        # System prompt for biomedical context
        self.system_prompt = """You are a helpful biomedical research assistant analyzing scientific literature.

You have access to a collection of PubMed abstracts selected by the user from a knowledge graph.
Your task is to answer questions based ONLY on the information in these abstracts.

Guidelines:
1. Always base your answers on the provided abstracts.
2. Cite specific PMIDs when making claims using the format: [PMID:XXXXXXXX].
3. If the abstracts don't contain relevant information, say so clearly.
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

            # Retrieve relevant context from RAG
            context, pmids_used = self.rag.get_context(user_message, top_k=top_k)

            # Build conversation history for LLM
            messages = self._build_messages(user_message, context)

            # Call LLM
            logger.info(f"Sending chat request with {len(pmids_used)} context documents")
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=messages,
                temperature=0.3,  # Lower temperature for factual responses
                max_tokens=1000,
            )

            assistant_content = response.choices[0].message.content.strip()

            # Create assistant message with sources
            assistant_msg = ChatMessage(
                role="assistant", content=assistant_content, sources=pmids_used
            )
            self.history.append(assistant_msg)

            # Trim history if needed
            self._trim_history()

            logger.info("Chat response generated successfully")

            return {
                "success": True,
                "message": assistant_content,
                "sources": pmids_used,
                "context_count": len(pmids_used),
            }

        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Sorry, I encountered an error processing your request.",
            }

    def _build_messages(self, user_message: str, context: str) -> list[dict]:
        """Build message list for LLM API call"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add recent conversation history (excluding current message)
        for msg in self.history[-(self.max_history - 1) :]:
            if msg.role != "system":  # Don't include system messages
                messages.append({"role": msg.role, "content": msg.content})

        # Add current message with RAG context
        current_message = f"""Context (relevant abstracts):

{context}

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
