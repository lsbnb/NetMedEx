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
    content: str  # compressed for history (assistant); full text for user
    sources: list[str] | None = None  # PMIDs for assistant messages
    timestamp: str | None = None
    msg_id: str | None = None
    full_content: str | None = None  # full uncompressed assistant response for export

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

    # Maximum characters stored per assistant message in the rolling history window.
    _HISTORY_ASSISTANT_MAX_CHARS = 1400
    # Budget for the accumulated memory buffer (all aged-out pairs, compressed).
    _MEMORY_BUFFER_MAX_CHARS = 1800
    # Characters kept per aged-out pair when compressing into memory buffer.
    _MEMORY_ENTRY_MAX_CHARS = 250

    def __init__(
        self,
        rag_system,
        llm_client,
        graph_retriever=None,
        max_history: int = 3,
        topic: str = "biomedical research",
    ):
        """
        Initialize chat session.

        Args:
            rag_system: AbstractRAG instance
            llm_client: LLM client for chat
            graph_retriever: GraphRetriever instance (optional)
            max_history: Number of conversation PAIRS (user+assistant) to keep in the
                rolling history window.  Older pairs are compressed into memory_buffer
                rather than discarded, so the session retains long-term continuity.
            topic: Research topic for the assistant (default: "biomedical research")
        """
        self.rag = rag_system
        self.llm = llm_client
        self.graph_retriever = graph_retriever
        self.max_history = max_history
        self.topic = topic
        self.history: list[ChatMessage] = []
        # Accumulated compressed summaries of conversation pairs that have aged out
        # of the rolling window.  Injected as a system message on every turn so the
        # LLM retains long-term awareness without a growing token cost.
        self.memory_buffer: list[str] = []

        # system_prompt is the core ROLE, OPERATIONAL RULES and OUTPUT STRUCTURE.
        self.system_prompt = """### ROLE
You are a highly specialized biomedical evidence reasoning agent focusing on {TOPIC}. Your primary task is to directly, precisely, and exclusively answer the user's current query using the provided PubMed CONTEXT. 

**CRITICAL ANSWER DIRECTIVE**:
- You must focus your entire response on addressing the specific question asked by the user in the latest message.
- Do NOT provide a general overview or repeat previous general summaries of the topic unless specifically asked.
- Every layer of your response (Layer 1, Layer 2, Layer 3, and Layer 4) must be customized and tailored to answer the user's specific question. Do not list findings or paths from the context that are unrelated to the query.

**CONSISTENCY DIRECTIVE**:
- In Layer 1, you MUST process and cite ALL PMIDs provided in the CONTEXT, listed in ascending PMID order. Do NOT skip or omit any PMID that is relevant to the query.
- Maintain a fixed, reproducible analytical structure: always cover direct evidence first (Layer 1), then associations (Layer 2), then causal hypotheses (Layer 3), then summary (Layer 4).
- Do NOT selectively choose which PMIDs to emphasize based on stylistic preference — cover ALL of them in Layer 1 before drawing inferences in Layers 2 and 3.

Synthesize relevant information from the context using a strict three-layer reasoning framework that cleanly separates direct evidence, association inference, and causal mechanism hypotheses.

---

### CORE PRINCIPLES
1. **Never hallucinate PMIDs.** Only cite PMIDs that appear explicitly in the CONTEXT.
2. **Never convert co-occurrence into regulation.** Entities appearing in the same paper are NOT necessarily causal.
3. **Edge-level citation.** Attach the supporting PMID at the edge/claim level: `[PMID]`, not only at the end of a paragraph.
4. **Strict layer separation.** Direct literature evidence, graph-based association, and causal hypotheses must NEVER be mixed within the same section.
5. **Causal language restriction.** Words such as *causes / drives / prevents / inhibits / activates / upregulates / downregulates* are ONLY permitted in **Layer 3**, and only when the edge polarity is supported by the CONTEXT.
6. **Speculative language mandate.** Layers 2 and 3 must use: *may / might / potentially / is consistent with / suggests*.
7. **Species distinction.** Label every finding as **Human** (clinical/patient data) or **Animal/In vitro** (mouse, rat, zebrafish, cell line). Do NOT generalise animal findings as human facts.
8. **No external knowledge.** All claims must trace back to the provided CONTEXT. If CONTEXT is insufficient, state so explicitly.
9. **Follow-up question specificity.** When answering a follow-up or suggested question (e.g. drilling down into a mechanism, clinical implication, or validation method):
   - You MUST focus exclusively on the specific entities, pathways, or validation actions asked in the follow-up question.
   - Do NOT repeat general overviews, background context, or unrelated findings from previous turns.
   - Every layer (Layer 1, Layer 2, Layer 3, and Layer 4) must be filtered to show only the information directly relevant to the current follow-up question. If a layer lacks relevant evidence, skip it or state "No relevant evidence for this specific question in the context."

---

### LANGUAGE RULE
- **CRITICAL**: Respond entirely in **{LANGUAGE}** — every word, every header, every sub-label. Hard requirement.
- Begin with `<thinking_english>... internal synthesis and PMID mapping ...</thinking_english>`. This block is automatically hidden.
- After the thinking block, write the ENTIRE response in **{LANGUAGE}**.
- **If {LANGUAGE} is English**: keep ALL section headers and sub-labels in English exactly as written in the OUTPUT STRUCTURE below. Do NOT use any Chinese, Japanese, or Korean text.
- **If {LANGUAGE} is not English**: translate ALL section headers AND ALL bold sub-labels according to the tables below. Do NOT mix languages.

**Section header translations (non-English only):**
  - **Traditional Chinese**: "直接文獻證據", "關聯推論 / 推測假說", "因果生物機制假說", "整合摘要", "建議問題"
  - **Japanese**: "直接的文献エビデンス", "関連推論 / 推測仮説", "因果メカニズム仮説", "統合サマリー", "推奨フォローアップ質問"
  - **Korean**: "직접 문헌 증거", "연관 추론 / 추론 가설", "인과 메커니즘 가설", "통합 요약", "권장 후속 질문"

**Sub-label translations (non-English only):**
  - **Traditional Chinese**: 假說、圖譜路徑、每條邊的證據、路徑信心度、推測原因、意義、機制主張、因果鏈、證據表、因果信心度、最弱環節、替代解釋、可測試預測、建議驗證方式、直接支持的內容？、推論的內容？、機制上合理的假說？
  - **Japanese**: 仮説、グラフパス、各エッジの証拠、パス信頼度、推測の理由、示唆、機序的主張、因果連鎖、証拠表、因果信頼度、最弱リンク、代替説明、検証可能な予測、推奨検証方法、直接支持された内容は？、推論された内容は？、機序的に妥当な仮説は？
  - **Korean**: 가설、그래프 경로、엣지별 증거、경로 신뢰도、추측 이유、시사점、기전적 주장、인과 연쇄、증거 표、인과 신뢰도、가장 약한 연결、대안적 설명、검증 가능한 예측、권장 검증 방법、직접 지지된 내용은?、추론된 내용은?、기전적으로 타당한 가설은?

---

### OUTPUT STRUCTURE

## Layer 1 — Evidence-Based Answer

List only conclusions directly supported by PubMed abstracts in the CONTEXT that are relevant to answering the user's question.
- Every claim format: {entity A} → {relation} → {entity B} [PMID]
- Use bullet points or a Markdown table for ≥ 3 items; include a brief functional description per item.
- Label each finding **[Human]** or **[Animal/In vitro]**.
- Do NOT include causal language unless the paper itself provides intervention evidence (knockdown, overexpression, CRISPR, etc.).
- If evidence only shows co-occurrence or weak association, state it explicitly.

## Layer 2 — Association / Speculative Inference

**REQUIRED** when the CONTEXT contains Knowledge Graph Structure paths (Latent Network Mechanisms) relevant to the user's question. Also include text-based speculative inferences from the abstracts that address the query.

For each 2-hop path, output one structured block:

**Hypothesis:** {Entity A} may potentially be associated with {Entity C}

**Graph Path:** {Entity A} → {intermediate node} → {Entity C}

**Evidence per edge:**
- {Entity A} → {Node B}: [PMID:xxxxx], relation: {relation type}
- {Node B} → {Entity C}: [PMID:yyyyy], relation: {relation type}
(If an edge lacks a PMID, write: "no direct literature support — confidence reduced")

**Path Confidence:** {0.00–1.00}

**Why speculative:** {e.g., no direct A→C PMID; edges are co-occurrence not mechanistic; single-paper evidence}

**Implication:** {What this association may suggest for the research question}

Rules for this layer:
- Use ONLY: *may / might / potentially / is consistent with / suggests*
- Do NOT use: *causes / drives / prevents / inhibits / activates* — those belong in Layer 3.
- Never use placeholder labels "EntityA / EntityB / EntityC" — always write the real biological names.

## Layer 3 — Causal Biomedical Mechanism

**Include ONLY when** the Knowledge Graph Structure contains directional, mechanistic edges relevant to the user's question (e.g., upregulates, inhibits, activates, suppresses, promotes). **Skip this layer entirely** if no relevant causal edges exist; instead note: "Current evidence is insufficient to form a causal mechanism hypothesis relevant to the query — only association-level inference is supported."

For each mechanistically plausible causal hypothesis:

**Mechanistic Claim:** {Entity A} may influence {Entity C} via {pathway / process}

**Causal Chain:**
{Entity A} --[{relation}, polarity: {+/-/unknown}, PMID:{xxxx}]--> {Node B} --[{relation}, polarity: {+/-/unknown}, PMID:{yyyy}]--> {Entity C}

**Evidence Table:**
| Edge | Relation | Polarity | PMID | Confidence |
|------|----------|----------|------|------------|
| {A → B} | {relation} | {+ / - / unknown} | {PMID} | {high/medium/low} |
| {B → C} | {relation} | {+ / - / unknown} | {PMID} | {high/medium/low} |

**Causal Confidence:** {0.00–1.00}

**Weakest Link:** {Which edge is least supported and why}

**Alternative Explanations:** {Possible non-causal explanations: confounding, co-expression, tissue-specific effects}

**Testable Prediction:** {What experimental result would confirm this mechanism}

**Suggested Validation:** {qPCR / knockdown / overexpression / CRISPR / reporter assay / animal model / single-cell validation}

Rules for this layer:
- This is a "mechanistically plausible hypothesis", NOT proven causation.
- If polarity is unknown, write "unknown" — do not guess.
- If direction is ambiguous, move the path to Layer 2 instead.
- Do NOT claim proven causation unless the CONTEXT contains explicit intervention evidence.

## Layer 4 — Final Integrated Summary

Three short paragraphs (2–3 sentences each) that directly and concisely answer the user's question based on the evidence presented above. **Every factual sentence must include its supporting PMID(s) inline.**
1. **What is directly supported?** Summarise the key Layer 1 findings that address the user's query with PMIDs [PMID].
2. **What is inferred?** Summarise the Layer 2 speculative inferences that address the user's query; reference the key PMIDs per edge [PMID].
3. **What is mechanistically plausible?** Summarise the Layer 3 causal mechanism hypotheses that address the user's query (or state "insufficient data for a causal mechanism hypothesis" if Layer 3 was skipped). Include causal PMIDs where available [PMID].

## Layer 5 — Suggested Follow-up Questions

Generate exactly 3 questions that help the user **explore different sub-topics** of the evidence. Each question MUST:
1. Name a **specific biological entity, gene, pathway, or PMID** cited in THIS response — do NOT use generic placeholders like "X" or "Y".
2. Target a **distinct biological sub-domain** so that each question would retrieve a DIFFERENT subset of literature:
   - Q1: Focus on a **specific molecular mechanism or signaling pathway** (e.g., a gene, protein complex, or enzymatic step named in Layer 1 or Layer 2).
   - Q2: Focus on a **specific clinical finding or patient population** (e.g., a disease subtype, biomarker, or therapeutic strategy mentioned in the context).
   - Q3: Focus on a **specific experimental gap** — name the exact causal edge or graph path from Layer 2/3 that lacks direct evidence, and ask what experiment would resolve it.

**Critical Rules:**
- NEVER use abstract placeholders. Every question must contain at least one real biological name from the CONTEXT (gene, protein, drug, pathway, cell type, species).
- Each question must be answerable by a *different* subset of PubMed abstracts — if two questions would retrieve the same papers, rewrite one.
- Do NOT restate or rephrase the original user query.
- Questions must be specific enough that a PubMed keyword search on them would return distinct results.

**RIGID FORMAT — no bullets, no numbering prefix:**
[Q1: Question 1 text]
[Q2: Question 2 text]
[Q3: Question 3 text]
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

            # Detect internal bootstrap triggers to auto-skip translation.
            # All internal calls from auto_initialize_chat use the [INTERNAL_BOOTSTRAP] sentinel.
            is_internal = user_message.strip().startswith("[INTERNAL_BOOTSTRAP]")

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

            # Always use vector search so each question retrieves docs ranked by
            # similarity to that specific query.  For small collections the search
            # returns all docs anyway, but in query-relevant order rather than a
            # fixed weight-based order that would be identical every turn.
            search_k = min(top_k, 5) if is_local else top_k
            if total_docs <= search_k:
                # Small collection: use vector search relevance order (most relevant first)
                # so the LLM receives documents ranked by their similarity to the user's query.
                # Consistency across similar queries is achieved by temperature=0 and the
                # CONSISTENCY DIRECTIVE in the system prompt, NOT by fixing document order.
                logger.info(
                    f"Document set ({total_docs}) ≤ k({search_k}); using query-relevance ordered rich formatting"
                )
                _, pmids_used = self.rag.get_context(search_query, top_k=search_k)

                context_parts = []
                for rank, pmid in enumerate(pmids_used, start=1):
                    doc = self.rag.documents.get(pmid)
                    if doc is None:
                        continue
                    priority_label = f"Relevance #{rank} (Impact Score: {doc.weight:.2f})"

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
                # Large collection: standard vector search
                text_context, pmids_used = self.rag.get_context(search_query, top_k=search_k)

            # 2. Retrieve Graph Context (Structure)
            graph_context = ""
            twohop_paths = []
            if self.graph_retriever:
                logger.info("Retrieving graph context...")
                relevant_nodes = focus_nodes if focus_nodes is not None else self.graph_retriever.find_relevant_nodes(search_query)
                if relevant_nodes:
                    graph_context, twohop_paths = self.graph_retriever.get_subgraph_context_with_paths(relevant_nodes, query=search_query)
                    logger.info(f"Found {len(relevant_nodes)} relevant nodes in graph, {len(twohop_paths)} paths")
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
                        temperature=0,
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
                    temperature=0,
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

            # Parse citations from response to filter sources.
            # Catch all formats the LLM uses:
            #   PMID:123456 / PMID: 123456 / PMID 123456
            #   [PMID:123456] / [123456] (bare 7-10 digit number in brackets)
            cited_pmids = set(
                re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", assistant_content)
            ) | set(
                re.findall(r"\[(\d{7,10})\]", assistant_content)
            )

            # Filter pmids_used to only include those actually cited
            final_sources = [p for p in pmids_used if p in cited_pmids]

            history_content = self._compress_for_history(assistant_content)

            assistant_msg = ChatMessage(
                role="assistant",
                content=history_content,
                sources=final_sources,
                full_content=assistant_content,
            )
            self.history.append(assistant_msg)
            self._trim_history()

            logger.info("Chat response generated successfully")

            return {
                "success": True,
                "message": assistant_content,
                "sources": final_sources,
                "pmids_used": pmids_used,
                "context_count": len(pmids_used),
                "user_msg": user_msg,
                "assistant_msg": assistant_msg,
                "twohop_paths": twohop_paths,
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

        # Inject long-term memory buffer (compressed earlier turns) as a system message
        # so the LLM can reference prior findings even after they've left the rolling window.
        memory_text = self._render_memory_buffer()
        if memory_text:
            messages.append({"role": "system", "content": memory_text})

        # Add recent conversation history (all stored pairs; already trimmed to max_history pairs)
        last_added_content = None
        for msg in self.history:
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
[Instruction: Focus exclusively on answering this specific question. Do not provide general overviews or repeat previous summaries of the topic.]
*Assistant:*"""

        messages.append({"role": "user", "content": current_message})

        return messages

    def _compress_for_history(self, content: str) -> str:
        """Compress an assistant response for history storage.

        Strips structural formatting introduced by the 5-layer prompt as well as
        visual/heavy sections, retaining primarily factual biomedical text with
        PMID citations.  Truncates to _HISTORY_ASSISTANT_MAX_CHARS so that token
        growth across multi-turn conversations stays bounded.  The RAG context for
        each new turn is always re-fetched fresh, so heavy formatting has no value
        in history.
        """
        text = content

        # 1. Remove <thinking_english> internal reasoning blocks
        text = re.sub(
            r"<thinking_english>[\s\S]*?</thinking_english>", "", text, flags=re.IGNORECASE
        )

        # 2. Remove mermaid diagrams
        text = re.sub(r"```mermaid[\s\S]*?```", "", text)

        # 3. Remove suggested-question lines in BOTH formats:
        #    Bracketed:  [Q1: …] [Q2: …] [Q3: …]
        #    Bare:       Q1: text  Q2: text  Q3: text  (from Q1 onward to end of section)
        text = re.sub(r"\[Q\d+:.*?\]", "", text, flags=re.DOTALL)
        # Bare format: strip from first bare "Q1:" (not preceded by "[") to end of section
        text = re.sub(r"(?<!\[)\bQ1\s*:.*", "", text, flags=re.IGNORECASE | re.DOTALL)

        # 4. Remove layer/section headers produced by the 5-layer prompt
        #    Matches: ## Layer 1 — …, ## Finding 1, ## Association Hypothesis 1, etc.
        text = re.sub(
            r"^#{1,3}\s*(?:Layer\s+\d+|Finding\s+\d+|Association\s+Hypothesis\s+\d+|"
            r"Causal\s+Mechanism\s+Hypothesis\s+\d+)[^\n]*\n?",
            "",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # 5. Remove Markdown table rows (lines starting and ending with |)
        text = re.sub(r"^\|[^\n]+\|[ \t]*\n?", "", text, flags=re.MULTILINE)

        # 6. Remove structured bold sub-labels that are pure formatting noise
        _LABEL_PATTERN = (
            r"\*\*(?:"
            r"Why speculative|Path Confidence|Mechanistic Claim|Causal Confidence|"
            r"Weakest Link|Testable Prediction|Suggested Validation|Alternative Explanations|"
            r"Evidence per edge|Graph Path|Hypothesis|Implication|Causal Chain|"
            r"Evidence Table|Directionality|Polarity|Causal Chain|"
            r"What is directly supported|What is inferred|What is mechanistically plausible"
            r")[^*\n]*\*\*[^\n]*\n?"
        )
        text = re.sub(_LABEL_PATTERN, "", text, flags=re.IGNORECASE)

        # 7. Collapse excessive blank lines and spaces
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text).strip()

        # 8. Collect all PMIDs from original content before truncation
        all_cited = sorted(set(
            re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", content)
        ) | set(
            re.findall(r"\[(\d{7,10})\]", content)
        ))

        # 9. Truncate at a sentence boundary within the char budget
        if len(text) > self._HISTORY_ASSISTANT_MAX_CHARS:
            cutoff = text[: self._HISTORY_ASSISTANT_MAX_CHARS].rfind(". ")
            if cutoff < self._HISTORY_ASSISTANT_MAX_CHARS // 2:
                cutoff = self._HISTORY_ASSISTANT_MAX_CHARS
            text = text[: cutoff + 1].strip() + " [...]"

        # 10. Append PMID summary so truncation never loses citation context
        if all_cited:
            pmid_line = f"\n[Cited PMIDs: {', '.join(all_cited[:15])}]"
            # Only append if not all PMIDs already appear in the compressed text
            present = set(re.findall(r"\d{7,10}", text))
            if not set(all_cited).issubset(present):
                text = text + pmid_line

        return text

    # ------------------------------------------------------------------
    # Memory buffer helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_sentences(text: str, max_chars: int) -> str:
        """Return leading text up to max_chars, breaking at the last sentence end."""
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars].rfind(". ")
        if cut < max_chars // 2:
            cut = max_chars
        return text[: cut + 1].strip()

    def _pair_to_memory_entry(self, user_msg: ChatMessage, asst_msg: ChatMessage) -> str:
        """Compress a conversation pair into a single memory entry line."""
        # User side: just the question text (strip template wrapper if present)
        q_raw = user_msg.content
        # Strip the CONTEXT/TASK wrapper that _build_messages injects
        task_marker = "### TASK"
        if task_marker in q_raw:
            q_raw = q_raw.split(task_marker, 1)[1]
        q_raw = re.sub(r"\*User:\*\s*", "", q_raw).split("*Assistant:*")[0].strip()
        q_text = q_raw[:120].strip()
        if len(q_raw) > 120:
            q_text += "…"

        # Assistant side: already compressed; take the first substantive sentences
        a_raw = asst_msg.content
        # Strip markdown headers and bullets for a cleaner summary line
        a_lines = [
            re.sub(r"^[#\*\-\•\s]+", "", ln).strip()
            for ln in a_raw.splitlines()
            if len(ln.strip()) > 20 and not ln.strip().startswith("[")
        ]
        a_text = self._first_sentences(" ".join(a_lines), self._MEMORY_ENTRY_MAX_CHARS)

        return f"Q: {q_text}\nA: {a_text}"

    def _update_memory_buffer(self, entry: str) -> None:
        """Append entry to memory_buffer, trimming oldest entries if over budget."""
        self.memory_buffer.append(entry)
        # Drop oldest entries until total chars fits within budget
        while sum(len(e) for e in self.memory_buffer) > self._MEMORY_BUFFER_MAX_CHARS:
            self.memory_buffer.pop(0)

    def _render_memory_buffer(self) -> str:
        """Render memory_buffer as a system message string, or empty string if empty."""
        if not self.memory_buffer:
            return ""
        entries = "\n\n".join(
            f"[Turn {i + 1}]\n{e}" for i, e in enumerate(self.memory_buffer)
        )
        return f"### Long-term Conversation Memory (earlier turns, compressed)\n{entries}"

    def _trim_history(self):
        """Sliding-window trim: pairs that fall out are compressed into memory_buffer."""
        max_messages = self.max_history * 2  # each pair = 1 user + 1 assistant
        while len(self.history) > max_messages:
            # Pop the oldest pair (user then assistant)
            if len(self.history) >= 2 and self.history[0].role == "user" and self.history[1].role == "assistant":
                old_user = self.history.pop(0)
                old_asst = self.history.pop(0)
                entry = self._pair_to_memory_entry(old_user, old_asst)
                self._update_memory_buffer(entry)
                logger.debug("Compressed 1 conversation pair into memory buffer")
            else:
                # Misaligned — just drop the oldest message
                self.history.pop(0)
        logger.debug(
            f"History: {len(self.history)} messages, memory buffer: {len(self.memory_buffer)} entries"
        )

    def get_history(self) -> list[dict]:
        """Get conversation history as list of dictionaries"""
        return [msg.to_dict() for msg in self.history]

    def clear(self):
        """Clear conversation history and memory buffer"""
        self.history.clear()
        self.memory_buffer.clear()
        logger.info("Chat history and memory buffer cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the chat session"""
        return {
            "message_count": len(self.history),
            "user_messages": sum(1 for msg in self.history if msg.role == "user"),
            "assistant_messages": sum(1 for msg in self.history if msg.role == "assistant"),
            "indexed_pmids": len(self.rag.get_all_pmids()) if self.rag else 0,
        }
