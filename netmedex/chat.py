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

    def __init__(
        self,
        rag_system,
        llm_client,
        graph_retriever=None,
        max_history: int = 10,
        topic: str = "biomedical research",
    ):
        """
        Initialize chat session.

        Args:
            rag_system: AbstractRAG instance
            llm_client: LLM client for chat
            graph_retriever: GraphRetriever instance (optional)
            max_history: Maximum conversation history to retain
            topic: Research topic for the assistant (default: "biomedical research")
        """
        self.rag = rag_system
        self.llm = llm_client
        self.graph_retriever = graph_retriever
        self.max_history = max_history
        self.topic = topic
        self.history: list[ChatMessage] = []

        # system_prompt is the core ROLE, OPERATIONAL RULES and OUTPUT STRUCTURE
        # from the user-provided optimized prompt.
        self.system_prompt = """### ROLE
You are a highly specialized biomedical research assistant focusing on {TOPIC}. Your goal is to synthesize information from the provided PubMed CONTEXT to provide structured, evidence-based answers to the user's QUERY.

---

### OPERATIONAL RULES
1. **Evidence-Based Synthesis:**
   - Prioritize information explicitly stated in the CONTEXT.
   - Integrate findings across multiple papers to identify consensus, trends, or conflicting results.
   - Every factual claim must be followed by its corresponding citation: `[PMID]`.

2. **Comprehensive Listing (Types, Genes & Numbers):**
   - If the QUERY asks for specific categories, types, or counts (e.g., associated genes, proteins, biomarkers, or cell types), you must **exhaustively list** all relevant entities found in the CONTEXT.
   - For clarity, use **bullet points** or a **table** when listing more than 3 items.
   - Each item in the list must be accompanied by its specific `[PMID]`.

3. **Inference & Hypotheses (Grounding Only):**
   - If direct evidence is missing, you may cautiously infer or hypothesize based on patterns within the provided papers.
   - Use tentative language (e.g., "suggests," "is consistent with," "may indicate").
   - These inferences must rely *only* on the provided CONTEXT; do not use external training knowledge.

4. **Graph Path Validation (2-Hop Evidence):**
   - The CONTEXT may include multihop paths (Latent Mechanisms, e.g., A -> B -> C).
   - Treat these as *hypothetical mechanistic chains*. You must explicitly distinguish between direct links (A-B) and these derived multihop paths in your analysis.
   - Cross-verify the biological plausibility of the entire chain using the evidence provided for each individual link.
   - **MANDATORY**: For every 2-hop path present in the Knowledge Graph Structure, you MUST map each link (A→B and B→C) to supporting PMIDs found in the PubMed Abstracts. If a link lacks direct PMID support, state it explicitly as "no direct literature support found."
   - All 2-hop inference results MUST appear in the **[Translated "Hypotheses / Speculative Inference"]** section, NOT in the Evidence-Based Answer section.

5. **Species & Study-Type Distinction:**
   - You MUST distinguish between findings in Human (clinical/patient data) and Animal models (e.g., mice, rats, zebrafish, cell lines).
   - If a claim is based on an animal model, you must explicitly state it (e.g., "In murine models [PMID]," or "Observed in cell cultures [PMID]").
   - Do NOT generalize animal findings as human clinical facts without clear comparative evidence.
   - Use the metadata [Study Type: Animal/Cell-Line] if provided in the context to guide your distinction.

6. **No External Knowledge & Citation Format:**
   - If the CONTEXT is "N/A" or irrelevant, output exactly: *"The provided papers do not contain information regarding this query."*
   - Strictly avoid using internal model knowledge or databases.
   - Always place PMIDs at the end of the relevant sentence or list item: `[PMID]`.

7. **Language Rule:**
   - **CRITICAL**: Respond in **{LANGUAGE}**. This is a hard requirement.
   - **Intermediary English Synthesis**: To ensure maximum accuracy against the English PubMed context, you MUST first perform an internal reasoning step in English.
   - **Format**: Begin your response with `<thinking_english>... your internal synthesis and PMID mapping ...</thinking_english>`. This block will be automatically hidden from the user.
   - After the thinking block, provide the FINAL response and ALL headers in **{LANGUAGE}**.
   - Specifically, use these translated section headers:
     - **Traditional Chinese**: "證據分析", "假說與推論", "建議問題", "其餘推斷"
     - **Japanese**: "根拠に基づく回答", "仮説・推論", "推奨されるフォローアップの質問"
     - **Korean**: "근거 중심 답변", "가설 및 추론", "권장 후속 질문"
   - Ensure the tone remains professional and information synthesis is grounded strictly in the CONTEXT.

---

### OUTPUT STRUCTURE

Please format your response as follows:

1. **[Translated "Evidence-Based Answer"]** - A synthesized summary of findings. If listing genes, proteins, or counts, use a clear **bulleted list** (or a **Markdown table** if requested by the user) with corresponding PMIDs and brief functional descriptions for each entry.

2. **[Translated "Hypotheses / Speculative Inference"]** (**REQUIRED** when the CONTEXT contains Knowledge Graph Structure paths; otherwise include if inference is warranted)
   - **MANDATORY for 2-hop paths**: For each "Latent Network Mechanism" path (A → B → C) in the Knowledge Graph Structure, present it as a mechanistic hypothesis with:
     - The full chain clearly stated (e.g., "A may influence C via B")
     - PMID support for the A→B link and the B→C link separately
     - An explicit note if a link lacks literature support in the provided abstracts
   - Also include any additional speculative mechanisms or research directions derived from the papers. Clearly state these are not directly proven.

3. **[Translated "Suggested Follow-up Questions"]**
   - Provide exactly 3 questions.
   - **RIGID UI FORMAT (No bullets):**
     [Q1: Question 1 text]
     [Q2: Question 2 text]
     [Q3: Question 3 text]
   - Important: Do NOT use markdown lists or bullets (-, *) for these three lines.
"""
        # Compact prompt for local LLMs
        self.local_system_prompt = self.system_prompt

    @staticmethod
    def _looks_like_cjk(text: str) -> bool:
        return any(
            "\u4e00" <= c <= "\u9fff"  # CJK Unified Ideographs (Chinese/Kanji)
            or "\u3040" <= c <= "\u309f"  # Hiragana
            or "\u30a0" <= c <= "\u30ff"  # Katakana
            or "\uac00" <= c <= "\ud7af"  # Hangul syllables
            for c in text
        )

    @staticmethod
    def _is_mirna_name(name: str) -> bool:
        normalized = name.strip().lower()
        return (
            normalized.startswith("mir")
            or normalized.startswith("miR".lower())
            or normalized.startswith("microRNA".lower())
            or normalized.startswith("let-")
        )

    @staticmethod
    def _strip_generic_subtype_prefix(text: str) -> str:
        """Remove generic subtype preface lines that are often unhelpful."""
        if not text:
            return text
        cleaned = text
        # Cover plain line, markdown heading, bold wrappers, and bracketed tag variants.
        leading_patterns = [
            r"^\s*#{0,6}\s*\*{0,2}\[?\s*Detected\s+Subtype:\s*General/Glioma\s*\(Cluster\s*0\)\s*\]?\*{0,2}\s*$\n?",
            r"^\s*\[\s*Detected\s+Subtype:\s*General/Glioma\s*\(Cluster\s*0\)\s*\]\s*$\n?",
        ]
        for pattern in leading_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        return cleaned.strip()

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

    def _build_entity_listing_response(
        self, entity_kind: str, user_message: str, session_language: str = "English"
    ) -> dict[str, Any] | None:
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

        # Determine if we should use CJK headers based on either message or session language
        use_cjk = self._looks_like_cjk(user_message) or self._looks_like_cjk(session_language)

        if use_cjk:
            title = "證據分析"
            hypo = "假說與推論"
            follow = "建議問題："
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

        output_lines = []
        cited_pmids: set[str] = set()
        as_table = "table" in user_message.lower() or "表格" in user_message

        if as_table:
            if use_cjk:
                output_lines.append("| 實體名稱 | 相關 PubMed ID (PMIDs) |")
            else:
                output_lines.append("| Entity Name | Related PubMed ID (PMIDs) |")
            output_lines.append("|---|---|")

            for name, pmid_set in sorted_entities:
                pmids = sorted(pmid_set)
                shown_pmids = pmids[:3]
                cited_pmids.update(shown_pmids)
                pmid_text = (
                    ", ".join(f"PMID:{p}" for p in shown_pmids) if shown_pmids else "No PMID"
                )
                extra = f" (+{len(pmids) - 3} more)" if len(pmids) > 3 else ""
                output_lines.append(f"| {name} | {pmid_text}{extra} |")
        else:
            for name, pmid_set in sorted_entities:
                pmids = sorted(pmid_set)
                shown_pmids = pmids[:3]
                cited_pmids.update(shown_pmids)
                pmid_text = (
                    ", ".join(f"PMID:{p}" for p in shown_pmids) if shown_pmids else "No PMID"
                )
                extra = f" (+{len(pmids) - 3} more)" if len(pmids) > 3 else ""
                output_lines.append(f"- {name} [{pmid_text}{extra}]")

        assistant_content = "\n".join(
            [
                f"**{title}**",
                intro,
                *output_lines,
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
        self,
        user_message: str,
        top_k: int = 8,
        session_language: str = "English",
        skip_translation: bool = False,
        focus_nodes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Process user message and generate AI response.

        Args:
            user_message: User's question
            top_k: Number of abstracts to retrieve for context
            session_language: Language to enforce for the response
            skip_translation: Whether to skip LLM translation for query optimization
            focus_nodes: Optional list of node IDs to root the 2-hop graph traversal.
                         If provided, bypasses NLP-based relevance matching.

        Returns:
            Dictionary with response and metadata
        """
        try:
            # Add user message to history
            user_msg = ChatMessage(role="user", content=user_message)
            self.history.append(user_msg)

            entity_listing_kind = self._detect_entity_listing_request(user_message)
            if entity_listing_kind:
                listing_response = self._build_entity_listing_response(
                    entity_listing_kind, user_message, session_language
                )
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

            # English Intermediary: Translate query to English for optimal retrieval if needed
            search_query = user_message

            # Detect internal bootstrap triggers to auto-skip translation
            bootstrap_triggers = [
                "Please provide a concise initial brief for the selected abstracts",
            ]
            is_internal = any(trigger in user_message for trigger in bootstrap_triggers)

            needs_translation = (
                not skip_translation
                and not is_internal
                and (session_language != "English" or self._looks_like_cjk(user_message))
            )

            if needs_translation:
                logger.info(
                    f"Translating query to English for optimal retrieval (Language: {session_language}, CJK: {self._looks_like_cjk(user_message)})"
                )
                if hasattr(self.llm, "translate_to_english"):
                    search_query = self.llm.translate_to_english(user_message)
                    logger.info(f"Translated query: '{search_query}'")
                else:
                    logger.warning(
                        "LLM client does not support translate_to_english; using original query"
                    )
            elif is_internal:
                # Use a generic meaningful query for internal bootstrap if empty or overly structured
                search_query = self.topic
                logger.debug(
                    f"Internal bootstrap detected. Using topic '{search_query}' as retrieval query."
                )

            # 1. Retrieve Text Context (RAG)
            # Use top_k to limit context size and speed up LLM response
            total_docs = len(self.rag.documents)
            is_local = getattr(self.llm, "provider", "") == "local"
            effective_k = top_k

            if is_local:
                effective_k = min(effective_k, 5)
                logger.info("Local model detected: capping context to 5 abstracts")

            if total_docs <= effective_k:
                logger.info(
                    f"Document set ({total_docs}) smaller than k({effective_k}), using subset of abstracts"
                )
                # Sort by weight (citation-normalized) descending
                sorted_docs = sorted(
                    self.rag.documents.values(), key=lambda d: d.weight, reverse=True
                )
                pmids_used = [doc.pmid for doc in sorted_docs[:effective_k]]

                context_parts = []
                for rank, pmid in enumerate(pmids_used, start=1):
                    doc = self.rag.documents[pmid]
                    priority_label = f"Priority #{rank} (Impact Score: {doc.weight:.2f})"

                    # Detect Species Study Type
                    study_type = "Human/General"
                    if hasattr(doc, "entities") and doc.entities:
                        non_human_species = [
                            e.get("name") for e in doc.entities
                            if e.get("type") == "Species" and e.get("mesh") != "MESH:D006801"
                        ]
                        if non_human_species:
                            study_type = f"Animal Model/In vitro (Target: {', '.join(non_human_species[:2])})"

                    part = [
                        f"PMID: {pmid} [{priority_label}] [Study Type: {study_type}]",
                        f"Title: {doc.title}",
                        f"Abstract: {doc.abstract}",
                    ]

                    # Include structured semantic relationships if available
                    if hasattr(doc, "edges") and doc.edges:
                        unique_rels = set()
                        for edge in doc.edges:
                            source = edge.get("source", "Unknown")
                            target = edge.get("target", "Unknown")
                            rels = edge.get("relations", ["associated"])
                            for r in rels:
                                unique_rels.add(f"- {source} --[{r}]--> {target}")
                        if unique_rels:
                            part.append("Structural Relationships (Extracted):")
                            part.extend(sorted(unique_rels)[:15])

                    context_parts.append("\n".join(part))
                text_context = "\n---\n\n".join(context_parts)
            else:
                # Use vector search for larger sets - cap top_k for local
                search_k = min(top_k, 5) if is_local else top_k
                text_context, pmids_used = self.rag.get_context(search_query, top_k=search_k)

            # 2. Retrieve Graph Context (Structure)
            graph_context = ""
            if self.graph_retriever:
                logger.info("Retrieving graph context...")
                relevant_nodes = focus_nodes if focus_nodes is not None else self.graph_retriever.find_relevant_nodes(search_query)
                if relevant_nodes:
                    graph_context = self.graph_retriever.get_subgraph_context(relevant_nodes, query=search_query)
                    logger.info(f"Found {len(relevant_nodes)} relevant nodes in graph")
                else:
                    logger.info("No relevant nodes found in graph query")

            # Build conversation history for LLM
            messages = self._build_messages(
                user_message, text_context, graph_context, session_language, ""
            )

            # Call LLM - use unified helper so Gemini uses its HTTP path
            logger.info(
                f"Sending chat request with {len(pmids_used)} context documents to {getattr(self.llm, 'provider', 'unknown')} LLM"
            )
            start_time = datetime.now()
            # Bootstrap summaries should be fast; keep token/time budget tighter.
            chat_max_tokens = 1400 if is_internal else 4000
            chat_timeout = 90.0 if is_internal else 300.0
            assistant_content = None
            if hasattr(self.llm, "chat_completion_text"):
                try:
                    assistant_content = self.llm.chat_completion_text(
                        messages=messages,
                        temperature=0.3,
                        max_tokens=chat_max_tokens,
                        timeout=chat_timeout,
                    )
                    duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"LLM Response received in {duration:.2f}s")
                    if assistant_content is not None and not isinstance(assistant_content, str):
                        logger.warning(
                            "chat_completion_text returned non-string content; falling back to SDK call"
                        )
                        assistant_content = None
                except Exception as e:
                    err = str(e).lower()
                    is_transient = any(
                        token in err
                        for token in (
                            "timed out",
                            "timeout",
                            "connection",
                            "rate limit",
                            "429",
                        )
                    )
                    # Avoid a second long wait on flaky providers during bootstrap.
                    if is_internal or is_transient:
                        raise
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

            # 6. Intermediary Reasoning Chain Filter
            # Strip internal <thinking_english> block before returning to user
            assistant_content = re.sub(
                r"<thinking_english>.*?</thinking_english>",
                "",
                assistant_content,
                flags=re.IGNORECASE | re.DOTALL,
            ).strip()

            # Guardrail: remove generic subtype prefix noise (common with some models).
            assistant_content = self._strip_generic_subtype_prefix(assistant_content)

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
        subtype_context: str = "",
    ) -> list[dict]:
        """Build message list for LLM API call"""
        provider = getattr(self.llm, "provider", "openai")
        is_local = provider == "local"

        system_content = self.local_system_prompt if is_local else self.system_prompt
        # Populate {TOPIC} and {LANGUAGE}
        system_content = system_content.replace("{TOPIC}", self.topic)
        system_content = system_content.replace("{LANGUAGE}", session_language)

        messages = [{"role": "system", "content": system_content}]

        # Add recent conversation history (excluding current message)
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

        # Add current message with structure-reinforced context
        context_str = (
            f"{subtype_context}\n"
            f"Knowledge Graph Structure:\n{graph_context}\n\n"
            f"PubMed Abstracts:\n{text_context}"
        )
        if not text_context.strip() and not graph_context.strip():
            context_str = "N/A"

        current_message = f"""### CONTEXT
{context_str}

---

### TASK
*User:* {user_message}
*Assistant:*"""

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
