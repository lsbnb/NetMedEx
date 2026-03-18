from __future__ import annotations

"""
Chat system for conversational analysis of PubMed abstracts using RAG

This module manages chat sessions and coordinates between the RAG system
and LLM to provide contextualized responses.
"""

import logging
import re
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
    msg_id: str | None = None

    def __post_init__(self):
        import uuid

        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.msg_id is None:
            self.msg_id = f"msg-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "role": self.role,
            "content": self.content,
            "sources": self.sources,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
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
        self.system_prompt = """You are a specialized Biomedical Expert and Research Assistant. Your goal is to provide high-quality, clinical-grade analysis of scientific literature.

You have access to a Hybrid RAG system combining:
1. **Knowledge Graph**: Structural links and entity paths connecting concepts.
2. **Textual RAG**: Deep context from relevant PubMed abstracts.

---

### OPERATING PROTOCOL

1.  **Hierarchical Structuring (CRITICAL)**:
    - Use `## Evidence-Based Answer` for findings directly stated in the context with PMID citations.
    - Use `## Hypotheses / Speculative Inference` for identifying patterns, mechanisms, or gaps when direct evidence is partial.
    - Use `### ` for sub-sections or specific PMID-based studies.

2.  **Authoritative Reasoning**:
    - Synthesize observations across multiple papers.
    - If papers A and B mention a drug and a gene respectively, and the graph shows a link, explain the structural connection as a pathway hypothesis.

3.  **Strict Language Adherence**:
    - Respond in the language of the query (e.g., Traditional Chinese if asked in Traditional Chinese).

4.  **No Outside Knowledge**:
    - Rely ONLY on the provided context. If the answer isn't there, say: "The provided literature does not contain information relevant to this query."

5.  **Citations**:
    - Cite PMIDs (e.g., [PMID: 156...]) for EVERY factual claim.

---

### OUTPUT STRUCTURE

You MUST structure every response into the following sections. **Translate the section headers into the same language as your response.**

**Evidence-Based Answer**
- Summarize what the papers directly state that is relevant to the query, with PMID citations.

**Hypotheses / Speculative Inference** (Include even if short)
- Based on the patterns in the papers, propose possible mechanisms or explanations that are consistent with but not directly proven by the text.
- **CRITICAL:** You MUST explicitly cite the specific PMIDs that form the basis of your hypothesis (e.g., "This hypothesis is supported by findings in PMID: 123456").

**Suggested Questions:** (Mandatory)
- Provide 3 brief follow-up questions for the user to explore further.
- Format these as a bulleted list.

---

### 🚨 LANGUAGE RULE (CRITICAL) 🚨

- **STRICT LANGUAGE MATCHING**: Respond in the EXACT SAME language as the user's query (e.g., Traditional Chinese if asked in Traditional Chinese).
- This applies to ALL parts of the response, including section headers and suggested questions.
"""
        # Compact prompt for local LLMs with smaller context windows
        self.local_system_prompt = """You are a Biomedical Research Assistant. 
Rely ONLY on the provided context (PMIDs provided below).
1. Respond in the language of the query.
2. Structure: 
   ## Evidence: What papers state. Cite [PMID: XXX].
   ## Hypotheses: What is suggested.
   ## Follow-up: 3 questions.
3. Cite PMIDs for EVERY factual claim.
"""

    @staticmethod
    def _looks_like_cjk(text: str) -> bool:
        return any("\u4e00" <= c <= "\u9fff" for c in text)

    @staticmethod
    def _is_mirna_name(name: str) -> bool:
        normalized = name.strip().lower()
        return (
            normalized.startswith("mir")
            or normalized.startswith("miR".lower())
            or normalized.startswith("microRNA".lower())
            or normalized.startswith("let-")
        )

    def _detect_entity_listing_request(self, user_message: str) -> str | None:
        query = user_message.lower()
        listing_terms = [
            "list",
            "enumerate",
            "show all",
            "what are",
            "which are",
            "有哪些",
            "列出",
            "清單",
            "全部",
        ]
        if not any(term in query for term in listing_terms):
            return None
        if "mirna" in query or "microRNA".lower() in query or "miRNA".lower() in query:
            return "mirna"
        if "mrna" in query:
            return "mrna"
        return None

    def _build_entity_listing_response(self, entity_kind: str, user_message: str) -> dict[str, Any] | None:
        if not self.graph_retriever or not getattr(self.graph_retriever, "graph", None):
            return None

        graph = self.graph_retriever.graph
        matches: list[tuple[str, list[str]]] = []
        for _, data in graph.nodes(data=True):
            name = str(data.get("name", "")).strip()
            node_type = str(data.get("type", "")).strip()
            pmids = sorted(str(p) for p in data.get("pmids", []))
            if node_type != "Gene" or not name:
                continue
            if entity_kind == "mirna" and self._is_mirna_name(name):
                matches.append((name, pmids))
            elif entity_kind == "mrna" and not self._is_mirna_name(name):
                matches.append((name, pmids))

        # Deduplicate by entity name while preserving PMID coverage.
        merged: dict[str, set[str]] = {}
        for name, pmids in matches:
            merged.setdefault(name, set()).update(pmids)

        sorted_entities = sorted(merged.items(), key=lambda item: item[0].lower())
        if not sorted_entities:
            return None

        if self._looks_like_cjk(user_message):
            title = "Evidence-Based Answer"
            hypo = "Hypotheses / Speculative Inference"
            follow = "Suggested Questions:"
            intro = f"在目前選取的網路中，共找到 {len(sorted_entities)} 個{entity_kind}相關實體："
            no_hypo = "這是根據目前圖譜節點直接整理出的完整清單，無需額外推論。"
            follow_lines = [
                "這些實體分別出現在哪些 PMID？",
                "哪些實體之間具有 semantic edges？",
                "是否要依 PMID 或 relation type 重新分組？",
            ]
        else:
            title = "Evidence-Based Answer"
            hypo = "Hypotheses / Speculative Inference"
            follow = "Suggested Questions:"
            intro = f"I found {len(sorted_entities)} {entity_kind}-related entities in the current selected network:"
            no_hypo = "This list is directly compiled from the current graph nodes, so no additional inference was needed."
            follow_lines = [
                "Which PMIDs mention each entity?",
                "Which of these entities are connected by semantic edges?",
                "Should I regroup them by PMID or relation type?",
            ]

        bullet_lines = []
        cited_pmids: set[str] = set()
        for name, pmid_set in sorted_entities:
            pmids = sorted(pmid_set)
            shown_pmids = pmids[:3]
            cited_pmids.update(shown_pmids)
            pmid_text = ", ".join(f"PMID:{p}" for p in shown_pmids) if shown_pmids else "No PMID"
            extra = f" (+{len(pmids) - 3} more)" if len(pmids) > 3 else ""
            bullet_lines.append(f"- {name} [{pmid_text}{extra}]")

        assistant_content = "\n".join(
            [
                f"**{title}**",
                intro,
                *bullet_lines,
                "",
                f"**{hypo}**",
                no_hypo,
                "",
                f"**{follow}**",
                *(f"- {line}" for line in follow_lines),
            ]
        ).strip()

        return {
            "content": assistant_content,
            "sources": sorted(cited_pmids),
            "context_count": len(sorted_entities),
        }

    def send_message(
        self, user_message: str, top_k: int = 5, session_language: str = "English"
    ) -> dict[str, Any]:
        """
        Process user message and generate AI response.

        Args:
            user_message: User's question
            top_k: Number of abstracts to retrieve for context
            session_language: Language to enforce for the response

        Returns:
            Dictionary with response and metadata
        """
        try:
            # Add user message to history
            user_msg = ChatMessage(role="user", content=user_message)
            self.history.append(user_msg)

            entity_listing_kind = self._detect_entity_listing_request(user_message)
            if entity_listing_kind:
                listing_response = self._build_entity_listing_response(entity_listing_kind, user_message)
                if listing_response:
                    assistant_msg = ChatMessage(
                        role="assistant",
                        content=listing_response["content"],
                        sources=listing_response["sources"],
                    )
                    self.history.append(assistant_msg)
                    return {
                        "success": True,
                        "message": assistant_msg.content,
                        "sources": assistant_msg.sources,
                        "context_count": listing_response["context_count"],
                        "user_msg": user_msg,
                        "assistant_msg": assistant_msg,
                    }

            # 1. Retrieve Text Context (RAG)
            # Optimization: If we have a small number of documents (<= 20),
            # just use all of them instead of vector search. This handles
            # "summarize all" queries much better.
            total_docs = len(self.rag.documents)
            is_local = getattr(self.llm, "provider", "") == "local"

            if total_docs <= 20:
                logger.info(f"Small document set ({total_docs}), using all abstracts for context")
                pmids_used = list(self.rag.documents.keys())
                
                # Truncate if local to save context window
                if is_local and total_docs > 8:
                    logger.info("Local model detected: capping context to 8 abstracts to preserve window")
                    pmids_used = pmids_used[:8]
                
                context_parts = []
                for pmid in pmids_used:
                    doc = self.rag.documents[pmid]
                    context_parts.append(
                        f"PMID: {pmid}\nTitle: {doc.title}\nAbstract: {doc.abstract}\n"
                    )
                text_context = "\n---\n\n".join(context_parts)
            else:
                # Use vector search for larger sets - cap top_k for local
                search_k = min(top_k, 5) if is_local else top_k
                text_context, pmids_used = self.rag.get_context(user_message, top_k=search_k)

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
            messages = self._build_messages(
                user_message, text_context, graph_context, session_language
            )

            # Call LLM - use unified helper so Gemini uses its HTTP path
            logger.info(f"Sending chat request with {len(pmids_used)} context documents")
            # Use a higher token limit for rich multi-section responses
            chat_max_tokens = 4000
            assistant_content = None
            if hasattr(self.llm, "chat_completion_text"):
                try:
                    assistant_content = self.llm.chat_completion_text(
                        messages=messages,
                        temperature=0.3,
                        max_tokens=chat_max_tokens,
                        timeout=240.0,
                    )
                    if assistant_content is not None and not isinstance(assistant_content, str):
                        logger.warning(
                            "chat_completion_text returned non-string content; falling back to SDK call"
                        )
                        assistant_content = None
                except Exception as e:
                    logger.warning(f"chat_completion_text failed, falling back to SDK call: {e}")

            if assistant_content is None and getattr(self.llm, "client", None) is not None:
                # Fallback: direct SDK call if helper is unavailable or failed
                response = self.llm.client.chat.completions.create(
                    model=self.llm.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=chat_max_tokens,
                )
                assistant_content = response.choices[0].message.content

            if assistant_content is None:
                assistant_content = ""
            assistant_content = assistant_content.strip()

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

            # Skip physical trimming to keep full history for downloads
            # self._trim_history()

            logger.info("Chat response generated successfully")

            return {
                "success": True,
                "message": assistant_content,
                "sources": final_sources,
                "context_count": len(pmids_used),
                "user_msg": user_msg,
                "assistant_msg": assistant_msg,
            }

        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Sorry, I encountered an error processing your request.",
            }

    def _build_messages(
        self,
        user_message: str,
        text_context: str,
        graph_context: str = "",
        session_language: str = "English",
    ) -> list[dict]:
        """Build message list for LLM API call"""
        provider = getattr(self.llm, "provider", "openai")
        is_local = provider == "local"
        
        system_content = self.local_system_prompt if is_local else self.system_prompt
        messages = [{"role": "system", "content": system_content}]

        # Add recent conversation history (excluding current message)
        # Prevents accidental consecutive repetition
        # Use a sliding window for context (max_history - 1)
        last_added_content = None
        history_window = (
            self.history[-(self.max_history - 1) :] if self.max_history > 0 else self.history
        )

        for msg in history_window:
            if msg.role == "system":
                continue
            if msg.content == user_message:
                continue
            if msg.content == last_added_content:
                continue

            messages.append({"role": msg.role, "content": msg.content})
            last_added_content = msg.content

        # Add current message with Hybrid RAG context
        current_message = f"""Context 1: Knowledge Graph Structure (Logic & Paths):
{graph_context if graph_context else "No specific structural context found."}

---

Context 2: Scientific Abstracts (Details & Evidence):
{text_context}

---

User question: {user_message}

Please answer based on the context provided above. 
CRITICAL RULE: You MUST respond entirely in {session_language}."""

        if is_local:
            # Append reinforcing reminder for local models
            current_message += f"\n\nREMINDER: Use {session_language}. Cite PMIDs (e.g. [PMID:123456])."

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
