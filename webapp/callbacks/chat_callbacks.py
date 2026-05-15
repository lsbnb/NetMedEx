from __future__ import annotations

import logging
import re

import dash
from dash import ALL, Input, Output, State, dcc, html, no_update

from webapp.utils import SessionPathError, resolve_session_savepath

logger = logging.getLogger(__name__)

# Local stores for chat state (keyed by graph path)
_sessions: dict[str, dict] = {}

COMMUNITY_NODE_PATTERN = re.compile(r"^c\d+$")


def _resolve_savepath(session_data):
    return resolve_session_savepath(session_data)


def _strip_message_suggestions(messages: list) -> list:
    """Remove .message-suggestions div from all rendered message components.

    Dash serialises component trees as nested dicts. This walks the tree and
    removes any node whose className contains 'message-suggestions', so that
    only the *latest* assistant message shows its pill questions.
    """
    def _strip(node):
        if not isinstance(node, dict):
            return node
        props = node.get("props", {})
        cls = props.get("className", "") or ""
        if "message-suggestions" in cls:
            return None
        children = props.get("children")
        if isinstance(children, list):
            new_children = [c for c in (_strip(c) for c in children) if c is not None]
            if len(new_children) != len(children):
                node = {**node, "props": {**props, "children": new_children}}
        elif isinstance(children, dict):
            new_child = _strip(children)
            if new_child is None:
                node = {**node, "props": {**props, "children": []}}
            elif new_child is not children:
                node = {**node, "props": {**props, "children": new_child}}
        return node

    return [_strip(m) for m in (messages or []) if m is not None]


# Helper to extract suggested questions from AI response.
# Relies solely on the explicit [Q1:] / [Q2:] / [Q3:] markers that the system
# prompt instructs the LLM to emit.  Previous broad keyword matching (e.g.
# "追問", "建議問題" as substrings) would falsely enter the suggestion section
# inside 2-hop inference text, swallowing that content.
def parse_suggestions(content):
    if not content:
        return [], ""

    def _default_questions(text: str) -> list[str]:
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in text)
        if has_cjk:
            return [
                "哪些證據最能支持目前的核心結論",
                "哪些 PMID 提供直接機制證據",
                "下一步最值得驗證的研究假說是什麼",
            ]
        return [
            "Which evidence most strongly supports the current conclusion",
            "Which PMIDs provide direct mechanistic evidence",
            "What is the highest-priority hypothesis to validate next",
        ]

    # ── find the first [Q1: …] marker ──────────────────────────────────────
    q1_match = re.search(r"\[Q1\s*:", content, re.IGNORECASE)
    if not q1_match:
        if re.search(r"Suggested(?:\s+Follow-up)?\s+Questions?", content, re.IGNORECASE):
            return _default_questions(content), content
        return [], content          # no explicit markers → no pills, full content

    cut = q1_match.start()

    # ── remove the suggestion-section header line immediately before Q1 ────
    before = content[:cut].rstrip()
    before = re.sub(
        r"\n[^\n]*(?:建議問題|Suggested(?:\s+Follow-up)?\s+Questions?|"
        r"建議的問題|提案された質問|권장 후속 질문)[^\n]*$",
        "",
        before,
        flags=re.IGNORECASE,
    ).rstrip()

    # ── extract [Q1:…] [Q2:…] [Q3:…] ─────────────────────────────────────
    raw_qs = re.findall(
        r"\[Q\d+\s*:\s*(.*?)\]",
        content[cut:],
        re.IGNORECASE | re.DOTALL,
    )
    suggestions: list[str] = []
    seen: set[str] = set()
    for q in raw_qs:
        q = re.sub(r"\s+", " ", q).strip().rstrip("?？.!！").strip()
        if q and len(q) > 3 and q.lower() not in seen:
            suggestions.append(q)
            seen.add(q.lower())
        if len(suggestions) >= 3:
            break

    return suggestions, before


def callbacks(app):
    # Client-side callback for immediate feedback
    app.clientside_callback(
        """
        function(n_clicks) {
            if (n_clicks) {
                return [
                    {
                        "props": {"className": "bi bi-arrow-clockwise bi-spin me-2"},
                        "type": "I",
                        "namespace": "dash_html_components"
                    },
                    "Processing",
                    {
                        "props": {
                            "className": "loading-dots",
                            "children": [
                                {"props": {}, "type": "Span", "namespace": "dash_html_components"},
                                {"props": {}, "type": "Span", "namespace": "dash_html_components"},
                                {"props": {}, "type": "Span", "namespace": "dash_html_components"}
                            ]
                        },
                        "type": "Span",
                        "namespace": "dash_html_components"
                    }
                ];
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("analyze-selection-btn", "children"),
        Input("analyze-selection-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    # Show progress bar when analysis starts, hide when children revert to original
    app.clientside_callback(
        """
        function(btn_children) {
            // If children contains a spinning icon, analysis is running → show progress bar
            var isRunning = false;
            if (Array.isArray(btn_children)) {
                for (var item of btn_children) {
                    if (item && item.props && item.props.className &&
                        item.props.className.indexOf('bi-spin') !== -1) {
                        isRunning = true;
                        break;
                    }
                }
            }
            var container = document.getElementById('chat-analyze-progress-container');
            if (container) {
                container.style.display = isRunning ? 'block' : 'none';
            }
            return [window.dash_clientside.no_update, isRunning];
        }
        """,
        [
            Output("chat-analyze-status-text", "children"),
            Output("analyze-selection-btn", "disabled", allow_duplicate=True),
        ],
        Input("analyze-selection-btn", "children"),
        prevent_initial_call=True,
    )

    @app.callback(
        [
            Output("chat-node-count", "children"),
            Output("chat-edge-count", "children"),
            Output("chat-abstract-count", "children"),
            Output("analyze-selection-btn", "disabled", allow_duplicate=True),
        ],
        [
            # Use 'cy' as the ID for the actual Cytoscape component
            Input("cy", "selectedNodeData"),
            Input("cy", "selectedEdgeData"),
        ],
        prevent_initial_call=True,
    )
    def update_selection_count(selected_nodes, selected_edges):
        """
        Update selection count based on graph selection.

        Args:
            selected_nodes: List of selected node data
            selected_edges: List of selected edge data
            graph_data: Full graph data with metadata

        Returns:
            Tuple of (node_count, edge_count, abstract_count, button_disabled)
        """
        if (not selected_edges or len(selected_edges) == 0) and (
            not selected_nodes or len(selected_nodes) == 0
        ):
            return "0", "0", "0", True

        # Filter out community nodes from count
        real_selected_nodes = []
        if selected_nodes:
            for node in selected_nodes:
                # Check if it's a community node (c0, c1, etc.)
                if "id" in node and COMMUNITY_NODE_PATTERN.match(node["id"]):
                    continue
                real_selected_nodes.append(node)

        node_count = len(real_selected_nodes)
        edge_count = len(selected_edges) if selected_edges else 0

        # Extract unique PMIDs from selected edges AND nodes
        # This matches the RAG indexing logic which indexes documents from both sources
        pmids = set()
        if selected_edges:
            for edge in selected_edges:
                if "pmids" in edge:
                    edge_pmids = edge["pmids"]
                    if isinstance(edge_pmids, list):
                        pmids.update(edge_pmids)
                    elif isinstance(edge_pmids, str):
                        pmids.add(edge_pmids)

        # Also include PMIDs from selected nodes (union, not fallback)
        if real_selected_nodes:
            for node in real_selected_nodes:
                if "pmids" in node:
                    node_pmids = node["pmids"]
                    if isinstance(node_pmids, list):
                        pmids.update(node_pmids)
                    elif isinstance(node_pmids, str):
                        pmids.add(node_pmids)

        article_count = len(pmids)

        # Enable button if we have at least one article
        button_disabled = article_count == 0

        return str(node_count), str(edge_count), str(article_count), button_disabled

    @app.callback(
        [
            Output("chat-session-active", "data", allow_duplicate=True),
            Output("chat-status", "children", allow_duplicate=True),
            Output("chat-input-box", "disabled", allow_duplicate=True),
            Output("chat-send-btn", "disabled", allow_duplicate=True),
            Output("clear-chat-btn", "style", allow_duplicate=True),
            Output("chat-context-banner", "children", allow_duplicate=True),
            Output("chat-context-banner", "style", allow_duplicate=True),
            Output("chat-messages", "children", allow_duplicate=True),
            Output("suggested-question-store", "data", allow_duplicate=True),
            Output("is-new-graph", "data", allow_duplicate=True),
        ],
        [
            Input("sidebar-panel-toggle", "active_tab"),
            Input("current-session-path", "data"),
            State("is-new-graph", "data"),
        ],
        [
            State("session-language", "data"),
            State("data-input", "value"),
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
            State("google-safety-setting", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
            State("openrouter-api-key-input", "value"),
            State("openrouter-model-selector", "value"),
            State("openrouter-custom-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def auto_initialize_chat(
        current_tab,
        session_data,
        is_new_graph,
        session_language,
        search_query,
        llm_provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        llm_base_url,
        llm_model,
        openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
    ):
        """
        Automatically initialize chat with an overall summary when a new graph is loaded.
        """
        # Trigger conditions:
        # 1. User must be in the chat tab
        # 2. Graph must be newly loaded (is_new_graph)
        # 3. No existing history for this session yet
        if current_tab != "chat" or not session_data or not is_new_graph:
            raise dash.exceptions.PreventUpdate

        global _sessions
        try:
            savepath = _resolve_savepath(session_data)
        except SessionPathError:
            raise dash.exceptions.PreventUpdate
        session_key = savepath["graph"]
        if session_key in _sessions and _sessions[session_key].get("history"):
            # Already initialized for this session
            raise dash.exceptions.PreventUpdate

        logger.info(f"DEBUG: auto_initialize_chat STARTING for tab={current_tab}")

        from netmedex.chat import ChatSession
        from netmedex.graph import load_graph
        from netmedex.rag import AbstractDocument, AbstractRAG
        from webapp.llm import (
            GEMINI_OPENAI_BASE_URL,
            OPENAI_BASE_URL,
            OPENROUTER_BASE_URL,
            llm_client,
        )

        # Initialize LLM Client
        if llm_provider == "openai":
            model = (
                openai_custom_model.strip()
                if openai_model == "custom" and openai_custom_model
                else openai_model
            ) or "gpt-4o-mini"
            llm_client.initialize_client(
                provider="openai",
                api_key=openai_api_key,
                model=model,
                base_url=OPENAI_BASE_URL,
            )
        elif llm_provider == "google":
            llm_client.initialize_client(
                provider="google",
                api_key=google_api_key,
                model=google_model or "gemini-1.5-pro",
                base_url=GEMINI_OPENAI_BASE_URL,
                safety_setting=google_safety_setting or "medium",
            )
        elif llm_provider == "openrouter":
            model = (
                openrouter_custom_model.strip()
                if openrouter_model == "custom" and openrouter_custom_model
                else openrouter_model
            ) or "openai/gpt-4o-mini"
            llm_client.initialize_client(
                provider="openrouter",
                api_key=openrouter_api_key,
                model=model,
                base_url=OPENROUTER_BASE_URL,
            )
        else:
            llm_client.initialize_client(
                provider="local",
                api_key="local-dummy-key",
                base_url=llm_base_url or "http://localhost:11434/v1",
                model=llm_model,
            )

        if not llm_client.client:
            return (
                False,
                "❌ Error: LLM not configured for auto-summary.",
                True,
                True,
                {"display": "none"},
                no_update,
                {"display": "none"},
                no_update,
                no_update,
                False,
            )

        try:
            import os

            if not os.path.exists(savepath["graph"]):
                return (
                    False,
                    "⚠️ Session expired. Please perform a new search to enable Chat.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    {"display": "none"},
                    no_update,
                    no_update,
                    False,
                )

            G = load_graph(savepath["graph"])

            # Extract TOP abstracts for overall summary (Top 50 by citation/weight)
            pmid_abstracts = G.graph.get("pmid_abstract", {})
            pmid_titles = G.graph.get("pmid_title", {})
            pmid_metadata = G.graph.get("pmid_metadata", {})

            import datetime

            from netmedex.utils import calculate_citation_weight

            current_year = datetime.datetime.now().year
            documents = []

            # Sort PMIDs by weight if citation counts are available
            all_pmids = list(pmid_abstracts.keys())
            pmid_weights = []
            for pmid in all_pmids:
                meta = pmid_metadata.get(pmid, {})
                weight = calculate_citation_weight(
                    meta.get("citation_count"), meta.get("date"), current_year
                )
                pmid_weights.append((pmid, weight))

            # Sort by weight descending
            sorted_pmids = [p for p, w in sorted(pmid_weights, key=lambda x: x[1], reverse=True)]
            top_pmids = sorted_pmids[:50]  # Limit to top 50 for summary

            for pmid in top_pmids:
                title = pmid_titles.get(pmid, f"PMID {pmid}")
                abstract = pmid_abstracts.get(pmid, "")
                # We don't need edge data for the overall summary, just the abstracts
                doc = AbstractDocument(
                    pmid=pmid, title=title, abstract=abstract, entities=[], edges=[], weight=1.0
                )
                documents.append(doc)

            if not documents:
                raise ValueError("No abstracts available for summary")

            # Initialize RAG and Chat
            rag_system = AbstractRAG(llm_client)
            rag_system.index_abstracts(documents)

            # No NodeRAG or GraphRetriever for overall summary bypass (too slow/complex for initial start)
            session = ChatSession(
                rag_system,
                llm_client,
                topic=search_query if search_query else "biomedical research overview",
            )

            # Store session
            session_id = savepath["graph"]
            _sessions[session_id] = {"session": session, "rag": rag_system}

            prompt_lang = session_language if session_language else "English"
            bootstrap_prompt = (
                "Please provide a comprehensive research summary of the provided abstracts using the two-layer framework below.\n"
                "Focus on the overall field findings related to the search topic.\n"
                "Use exactly these sections:\n"
                "1. Evidence-Based Answer\n"
                "- Synthesise the main research findings directly supported by PubMed abstracts.\n"
                "- Every claim must include its PMID. Label findings as [Human] or [Animal/In vitro].\n"
                "- Do NOT use causal language (inhibits/activates/causes) unless the paper provides intervention evidence.\n"
                "2. Association / Speculative Inference\n"
                "- One or two major research trends or speculative inferences derived from the data.\n"
                "- Use may/might/potentially. State why each inference is speculative.\n"
                "3. Suggested Follow-up Questions\n"
                "- Provide exactly 3 questions.\n"
                "- **RIGID FORMAT (No bullets):**\n"
                "  [Q1: Question 1 text]\n"
                "  [Q2: Question 2 text]\n"
                "  [Q3: Question 3 text]\n"
                f"IMPORTANT: Respond in {prompt_lang} and translate all section headers accordingly.\n"
                "Keep the response professional and structured."
            )

            summary_result = session.send_message(
                bootstrap_prompt,
                session_language=session_language or "English",
                skip_translation=True,
            )

            if summary_result.get("success"):
                summary_msg = summary_result.get("assistant_msg")
                from webapp.components.chat import create_message_component

                summary_content = summary_result.get("message") or (summary_msg.content if summary_msg else "")
                suggestions, clean_content = parse_suggestions(summary_content)
                summary_component = create_message_component(
                    "assistant",
                    clean_content,
                    summary_msg.sources if summary_msg else None,
                    msg_id=summary_msg.msg_id if summary_msg else None,
                    suggestions=suggestions,
                )
                messages = [summary_component]

                # Update context banner
                context_banner = [
                    html.Div(
                        [
                            html.Span("🔍 Research Context: ", className="fw-bold"),
                            html.Span(
                                f"Overall Findings for '{search_query}'"
                                if search_query
                                else "Full Dataset Summary"
                            ),
                        ],
                        className="chat-context-query",
                    )
                ]

                return (
                    True,
                    "",
                    False,
                    False,
                    {"display": "block"},
                    context_banner,
                    {"display": "block"},
                    messages,
                    no_update,
                    False,  # Reset is-new-graph so this doesn't re-trigger
                )
            raise ValueError("LLM Summary failed")

        except Exception as e:
            logger.error(f"Error in auto_initialize_chat: {e}")
            raise dash.exceptions.PreventUpdate

    @app.callback(
        [
            Output("chat-session-active", "data", allow_duplicate=True),
            Output("chat-status", "children", allow_duplicate=True),
            Output("chat-input-box", "disabled", allow_duplicate=True),
            Output("chat-send-btn", "disabled", allow_duplicate=True),
            Output("clear-chat-btn", "style", allow_duplicate=True),
            Output("chat-context-banner", "children", allow_duplicate=True),
            Output("chat-context-banner", "style", allow_duplicate=True),
            Output("chat-messages", "children", allow_duplicate=True),
            Output("analyze-selection-btn", "children", allow_duplicate=True),
            Output("suggested-question-store", "data", allow_duplicate=True),
            Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
            Output("twohop-highlight-paths", "data", allow_duplicate=True),
        ],
        Input("analyze-selection-btn", "n_clicks"),
        [
            State("cy", "selectedNodeData"),
            State("cy", "selectedEdgeData"),
            State("current-session-path", "data"),
            State("session-language", "data"),
            State("data-input", "value"),
            State("llm-provider-selector", "value"),
            State("openai-api-key-input", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-api-key-input", "value"),
            State("google-model-selector", "value"),
            State("google-safety-setting", "value"),
            State("llm-base-url-input", "value"),
            State("llm-model-input", "value"),
            State("openrouter-api-key-input", "value"),
            State("openrouter-model-selector", "value"),
            State("openrouter-custom-model-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def initialize_chat(
        n_clicks,
        selected_nodes,
        selected_edges,
        session_data,
        session_language,
        search_query,
        llm_provider,
        openai_api_key,
        openai_model,
        openai_custom_model,
        google_api_key,
        google_model,
        google_safety_setting,
        llm_base_url,
        llm_model,
        openrouter_api_key,
        openrouter_model,
        openrouter_custom_model,
    ):
        logger.info("DEBUG: initialize_chat (MANUAL) triggered")
        global _sessions

        # Reset button content
        reset_btn = [html.I(className="bi bi-chat-dots me-2"), "Analyze Selection"]

        if not n_clicks or not (selected_edges or selected_nodes):
            raise dash.exceptions.PreventUpdate

        try:
            import os
            import time
            from netmedex.chat import ChatSession
            from netmedex.graph import load_graph
            from netmedex.rag import AbstractDocument, AbstractRAG
            from webapp.llm import (
                GEMINI_OPENAI_BASE_URL,
                OPENAI_BASE_URL,
                OPENROUTER_BASE_URL,
                llm_client,
            )

            t0 = time.time()
            logger.info("Starting Chat Analysis...")

            try:
                savepath = _resolve_savepath(session_data)
            except SessionPathError:
                return (
                    False,
                    "❌ Error: Graph session data not found.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    {"display": "none"},
                    no_update,
                    reset_btn,
                    no_update,
                    "chat",
                    [],
                )

            # Keep chat process LLM config aligned with current Advanced Settings.
            if llm_provider == "openai":
                model = (
                    openai_custom_model.strip()
                    if openai_model == "custom" and openai_custom_model
                    else openai_model
                ) or "gpt-4o-mini"
                llm_client.initialize_client(
                    provider="openai",
                    api_key=openai_api_key,
                    model=model,
                    base_url=OPENAI_BASE_URL,
                )
            elif llm_provider == "google":
                llm_client.initialize_client(
                    provider="google",
                    api_key=google_api_key,
                    model=google_model or "gemini-1.5-pro",
                    base_url=GEMINI_OPENAI_BASE_URL,
                    safety_setting=google_safety_setting or "medium",
                )
            elif llm_provider == "openrouter":
                model = (
                    openrouter_custom_model.strip()
                    if openrouter_model == "custom" and openrouter_custom_model
                    else openrouter_model
                ) or "openai/gpt-4o-mini"
                llm_client.initialize_client(
                    provider="openrouter",
                    api_key=openrouter_api_key,
                    model=model,
                    base_url=OPENROUTER_BASE_URL,
                )
            else:
                llm_client.initialize_client(
                    provider="local",
                    api_key="local-dummy-key",
                    base_url=llm_base_url or "http://localhost:11434/v1",
                    model=llm_model,
                )

            if not llm_client.client:
                return (
                    False,
                    "❌ Error: LLM not configured. Please set your API key in Advanced Settings.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    {"display": "none"},
                    no_update,
                    reset_btn,
                    no_update,
                    "chat",
                    [],
                )

            # Load the graph to get abstracts
            if not os.path.exists(savepath["graph"]):
                return (
                    False,
                    "⚠️ Session expired. Please perform a new search.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    {"display": "none"},
                    no_update,
                    reset_btn,
                    no_update,
                    "chat",
                    [],
                )

            G = load_graph(savepath["graph"])
            t_load = time.time()
            logger.info(f"Graph loaded in {t_load - t0:.2f}s")

            # Extract PMIDs and build abstract documents
            pmid_data = {}
            for edge in selected_edges:
                edge_pmids = edge.get("pmids", [])
                if isinstance(edge_pmids, str):
                    edge_pmids = [edge_pmids]

                for pmid in edge_pmids:
                    if pmid not in pmid_data:
                        pmid_data[pmid] = {"pmid": pmid, "edges": []}
                    pmid_data[pmid]["edges"].append(edge)

            # Extract PMIDs from nodes as well (to capture isolated entities)
            if selected_nodes:
                # Need to map node IDs back to graph nodes if selected_nodes doesn't have pmid info complete
                # But Cytoscape selectedNodeData should contain the data object
                for node in selected_nodes:
                    node_pmids = node.get("pmids", [])
                    if isinstance(node_pmids, str):
                        node_pmids = [node_pmids]

                    for pmid in node_pmids:
                        if pmid not in pmid_data:
                            # Nodes don't have edge data, so we leave edges empty
                            pmid_data[pmid] = {"pmid": pmid, "edges": []}

            # Get abstracts and metadata from graph
            pmid_abstracts = G.graph.get("pmid_abstract", {})
            pmid_titles = G.graph.get("pmid_title", {})
            pmid_metadata = G.graph.get("pmid_metadata", {})

            # Shared weighting utility
            import datetime

            from netmedex.utils import calculate_citation_weight

            current_year = datetime.datetime.now().year

            logger.info(f"PMIDs in selected edges: {list(pmid_data.keys())}")
            logger.info(f"Total abstracts in graph: {len(pmid_abstracts)}")

            # Build node ID → display name map so edge context uses readable names
            node_name_map = {
                str(nid): nd.get("name", str(nid))
                for nid, nd in G.nodes(data=True)
            }

            def _resolve_edge(edge: dict) -> dict:
                """Replace raw node-hash source/target with human-readable names."""
                resolved = dict(edge)
                resolved["source"] = node_name_map.get(str(edge.get("source", "")), edge.get("source", "Unknown"))
                resolved["target"] = node_name_map.get(str(edge.get("target", "")), edge.get("target", "Unknown"))
                return resolved

            # Build AbstractDocument objects
            documents = []
            for pmid, data in pmid_data.items():
                title = pmid_titles.get(pmid, f"PMID {pmid}")
                abstract = pmid_abstracts.get(pmid, "Abstract not available.")

                # Priority weighting
                meta = pmid_metadata.get(pmid, {})
                weight = calculate_citation_weight(
                    meta.get("citation_count"), meta.get("date"), current_year
                )

                doc = AbstractDocument(
                    pmid=pmid,
                    title=title,
                    abstract=abstract,
                    entities=[],
                    edges=[_resolve_edge(e) for e in data["edges"]],
                    weight=weight,
                )
                documents.append(doc)

            if not documents:
                return (
                    False,
                    "❌ No abstracts found for selected edges.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    {"display": "none"},
                    no_update,
                    reset_btn,
                    no_update,
                    "chat",
                    [],
                )

            # Initialize RAG system
            rag_system = AbstractRAG(llm_client)
            rag_system.index_abstracts(documents)
            t_rag = time.time()
            logger.info(f"Abstracts indexed in {t_rag - t_load:.2f}s")

            # Initialize Node RAG System with Persistent Cache (New in v1.1.0)
            from netmedex.node_rag import NodeRAG, GraphNode

            # Determine persistent directory based on graph path
            # Example: data/graph.pickle -> data/graph.pickle_chroma
            persist_dir = f"{savepath['graph']}_chroma"
            node_rag = NodeRAG(llm_client, persist_directory=persist_dir)

            # Check if NodeRAG is already indexed for this graph
            # Check if NodeRAG is already indexed for this graph
            # Build label→raw_node_id lookup from the pickled graph.
            # Cytoscape element source/target use stable UUIDs, which differ from
            # the raw NetworkX node IDs used inside the graph — match by name instead.
            label_to_raw_id = {
                str(data.get("name", "")).lower().strip(): nid
                for nid, data in G.nodes(data=True)
                if data.get("name")
            }

            core_node_ids = set()
            if selected_nodes:
                for n in selected_nodes:
                    if str(n.get("id", "")).startswith("c"):
                        continue  # skip community nodes
                    name_key = str(n.get("label", n.get("name", ""))).lower().strip()
                    if name_key in label_to_raw_id:
                        core_node_ids.add(label_to_raw_id[name_key])
            if selected_edges:
                for e in selected_edges:
                    for name_field in ("source_name", "target_name"):
                        name_key = str(e.get(name_field, "")).lower().strip()
                        if name_key in label_to_raw_id:
                            core_node_ids.add(label_to_raw_id[name_key])

            if not node_rag.is_indexed():
                total_nodes = len(G.nodes)
                # Optimization for large graphs: only index selected nodes + nodes in selected edges
                if total_nodes > 1000:
                    logger.info(
                        f"Large graph detected ({total_nodes} nodes). Indexing selection only for instant initialization."
                    )
                    graph_nodes = []
                    for node_id in core_node_ids:
                        if node_id in G.nodes:
                            data = G.nodes[node_id]
                            name = data.get("name", str(node_id))
                            node_type = data.get("type", "Entity")
                            graph_nodes.append(
                                GraphNode(
                                    node_id=str(node_id), name=name, type=node_type, metadata=data
                                )
                            )

                    if graph_nodes:
                        node_rag.index_nodes(graph_nodes)
                        logger.info(
                            f"Partial indexing complete: {len(graph_nodes)}/ {total_nodes} nodes indexed."
                        )
                else:
                    logger.info(
                        f"Small graph detected ({total_nodes} nodes). Building full node list..."
                    )
                    graph_nodes = []
                    for node_id, data in G.nodes(data=True):
                        # Ensure we have a name
                        name = data.get("name", str(node_id))
                        node_type = data.get("type", "Entity")
                        graph_node = GraphNode(
                            node_id=str(node_id), name=name, type=node_type, metadata=data
                        )
                        graph_nodes.append(graph_node)

                    node_rag.index_nodes(graph_nodes)
                    logger.info(f"Full indexing complete: {len(graph_nodes)} nodes indexed.")
            else:
                logger.info("NodeRAG already indexed. Skipping re-scan.")

            t_node = time.time()
            logger.info(f"Node indexing check in {t_node - t_rag:.2f}s")

            # Initialize Graph Retriever with NodeRAG
            from netmedex.graph_rag import GraphRetriever

            graph_retriever = GraphRetriever(G, node_rag=node_rag)
            logger.info("GraphRetriever initialized with full graph")

            # Initialize chat session with Hybrid RAG
            session = ChatSession(
                rag_system,
                llm_client,
                graph_retriever=graph_retriever,
                topic=search_query if search_query else "biomedical research",
            )

            # Store in global session manager
            session_id = savepath["graph"]
            _sessions[session_id] = {"session": session, "rag": rag_system}

            context_banner = [
                html.Div(
                    [
                        html.Span("🔍 Search Query: ", className="fw-bold"),
                        html.Span(search_query if search_query else "(No query text)"),
                    ],
                    className="chat-context-query",
                )
            ]

            from webapp.components.chat import create_message_component

            prompt_lang = session_language if session_language else "English"

            # Bootstrap summary: ALWAYS use English internally for faster LLM reasoning and better RAG retrieval.
            # The final response will be translated by the system_prompt or a post-processing step.
            bootstrap_prompt = (
                "Please provide a concise initial analysis of the selected abstracts using the three-layer reasoning framework.\n"
                "Use exactly these layers:\n"
                "1. Evidence-Based Answer — direct findings from abstracts, PMID per claim, label [Human] or [Animal/In vitro].\n"
                "2. Association / Speculative Inference — for each 2-hop graph path: hypothesis, graph path with named entities, PMIDs per edge, path confidence, why speculative. Use may/might/potentially only.\n"
                "3. Causal Biomedical Mechanism — ONLY if directional edges exist: mechanistic claim, causal chain with polarity, evidence table per edge, causal confidence, weakest link, testable prediction. Skip and state insufficient data if no directional edges.\n"
                "4. Final Integrated Summary — three short paragraphs: directly supported / inferred / mechanistically plausible.\n"
                "5. Suggested Follow-up Questions — RIGID FORMAT (no bullets):\n"
                "  [Q1: Question 1 text]\n"
                "  [Q2: Question 2 text]\n"
                "  [Q3: Question 3 text]\n"
                "IMPORTANT: Never mix direct evidence with speculative inference. Never hallucinate PMIDs. Never use causal language (inhibits/activates/drives) outside Layer 3.\n"
            )

            # If user is in a non-English session, append a translation instruction at the end
            if prompt_lang not in ("English", None, ""):
                bootstrap_prompt += f"\nIMPORTANT: Your ENTIRE response (including section headers, content, and suggested questions) MUST be written in {prompt_lang}. Language lock: ON."

            logger.info(
                f"Generating initial summary (internal English query, output: {prompt_lang})..."
            )
            summary_result = session.send_message(
                bootstrap_prompt,
                session_language=session_language or "English",
                skip_translation=True,  # The translation instruction is embedded in the prompt
                focus_nodes=list(core_node_ids) if core_node_ids else None,
            )
            t_sum = time.time()
            logger.info(f"Initial summary generated in {t_sum - t_node:.2f}s")
            logger.info(f"Total Analyze Selection time: {t_sum - t0:.2f}s")
            bootstrap_user = summary_result.get("user_msg")
            if bootstrap_user is not None and bootstrap_user in session.history:
                session.history.remove(bootstrap_user)

            # Extract 2-hop paths from the initial summary for Graph highlighting
            twohop_paths = summary_result.get("twohop_paths", [])
            # Store in session for subsequent messages
            _sessions[session_id]["twohop_paths"] = twohop_paths
            # Cache focus_nodes so follow-up messages reuse the same node set
            # instead of re-running find_relevant_nodes() on every turn (O(n²) risk)
            _sessions[session_id]["focus_nodes"] = list(core_node_ids) if core_node_ids else None

            if summary_result.get("success"):
                summary_msg = summary_result.get("assistant_msg")
                summary_content = summary_result.get("message") or (summary_msg.content if summary_msg else "")
                suggestions, clean_content = parse_suggestions(summary_content)
                summary_component = create_message_component(
                    "assistant",
                    clean_content,
                    summary_msg.sources if summary_msg else None,
                    msg_id=summary_msg.msg_id if summary_msg else None,
                    suggestions=suggestions,
                )
                messages = [summary_component]
            else:
                fallback_summary = (
                    "I have analyzed the current research context. Here is an overview:\n\n"
                    "- I've indexed the search results and generated a semantic knowledge graph.\n"
                    "- You can ask me questions about mechanisms, clinical findings, or therapeutic options.\n"
                    "- Mention specific entities to get detailed evidence and literature citations.\n"
                    "- Once you ask a focused question, I will provide one hypothesis tied to cited PMIDs.\n\n"
                )
                suggestions = [
                    "Which mechanisms are most strongly supported?",
                    "Which PMIDs provide direct evidence?",
                    "What are the key research gaps?",
                ]
                messages = [
                    create_message_component(
                        "assistant",
                        fallback_summary,
                        msg_id="bootstrap-msg",
                        suggestions=suggestions,
                    )
                ]

            return (
                True,
                "",
                False,  # Enable input
                False,  # Enable send button
                {"display": "block"},  # Show clear button
                context_banner,
                {"display": "block"},
                messages,
                reset_btn,
                None,  # ⚠️ FIX: Clear suggested-question-store on re-initialization
                "chat",
                twohop_paths,
            )

        except Exception as e:
            logger.error(f"Error initializing chat: {e}")
            return (
                False,
                f"❌ Error: {str(e)}",
                True,
                True,
                {"display": "none"},
                no_update,
                {"display": "none"},
                no_update,
                reset_btn,
                no_update,
                "chat",
                [],
            )

    @app.callback(
        [
            Output("chat-messages", "children", allow_duplicate=True),
            Output("modal-chat-content", "children", allow_duplicate=True),
            Output("chat-input-box", "value", allow_duplicate=True),
            Output("modal-chat-input", "value", allow_duplicate=True),
            Output("chat-processing-status", "children"),
            Output("modal-chat-processing-status", "children"),
            Output("suggested-question-store", "data", allow_duplicate=True),
            Output("chat-send-btn", "disabled", allow_duplicate=True),
            Output("modal-chat-send-btn", "disabled", allow_duplicate=True),
            Output("twohop-highlight-paths", "data", allow_duplicate=True),
        ],
        [
            Input("chat-send-btn", "n_clicks"),
            Input("modal-chat-send-btn", "n_clicks"),
            Input("suggested-question-store", "data"),
        ],
        [
            State("chat-input-box", "value"),
            State("modal-chat-input", "value"),
            State("chat-messages", "children"),
            State("session-language", "data"),
            State("chat-send-btn", "disabled"),
            State("current-session-path", "data"),
        ],
        prevent_initial_call=True,
    )
    def send_message(
        n1,
        n2,
        suggested_input,
        main_input,
        modal_input,
        current_messages,
        _session_language,
        is_disabled,
        session_data,
    ):
        """
        Process user message and get AI response.
        """
        global _sessions

        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        # Prevent double trigger if buttons are already disabled
        if is_disabled and trigger_id in ["chat-send-btn", "modal-chat-send-btn"]:
            raise dash.exceptions.PreventUpdate

        # Determine user input source
        if trigger_id == "suggested-question-store":
            user_input = suggested_input
        else:
            user_input = main_input if trigger_id == "chat-send-btn" else modal_input

        if not user_input or not user_input.strip():
            raise dash.exceptions.PreventUpdate

        # Guard: session may be missing if server was restarted after graph was built
        try:
            savepath = _resolve_savepath(session_data)
        except SessionPathError:
            savepath = None

        if not savepath or savepath["graph"] not in _sessions:
            from webapp.components.chat import create_message_component
            err_msg = create_message_component(
                "assistant",
                "⚠️ Session expired (server was restarted). Please run a new search to rebuild the graph and start chatting.",
            )
            msgs = list(current_messages or []) + [err_msg]
            return msgs, msgs, "", "", "", "", None, False, False, []

        session_data = _sessions[savepath["graph"]]
        session = session_data["session"]

        try:
            from webapp.callbacks.pipeline import detect_query_language
            from webapp.components.chat import create_message_component

            # Response language follows the user's current message.
            # If the script cannot be determined, detect_query_language returns
            # "English" as the default — matching the "fallback to English" rule.
            effective_language = detect_query_language(user_input)

            # Get AI response — reuse cached focus_nodes from analyze_selection
            # to avoid expensive find_relevant_nodes() on every follow-up turn
            cached_focus = session_data.get("focus_nodes")
            response = session.send_message(
                user_input,
                session_language=effective_language,
                focus_nodes=cached_focus,
            )

            if response["success"]:
                # Use returned message objects for stability instead of relying on history indexing
                user_msg_obj = response.get("user_msg")
                assistant_msg_obj = response.get("assistant_msg")

                # Fallback if objects are missing
                if not user_msg_obj:
                    user_msg_obj = session.history[-2]
                if not assistant_msg_obj:
                    assistant_msg_obj = session.history[-1]

                user_msg = create_message_component(
                    "user", user_msg_obj.content, msg_id=user_msg_obj.msg_id
                )
                response_content = response.get("message") or (assistant_msg_obj.content if assistant_msg_obj else "")
                suggestions, clean_content = parse_suggestions(response_content)

                # Update 2-hop paths from the latest response
                twohop_paths = response.get("twohop_paths", [])
                if twohop_paths and savepath:
                    _sessions[savepath["graph"]]["twohop_paths"] = twohop_paths

                ai_msg = create_message_component(
                    "assistant",
                    clean_content,
                    assistant_msg_obj.sources,
                    msg_id=assistant_msg_obj.msg_id,
                    suggestions=suggestions,
                )
            else:
                # Handle error case
                assistant_msg_obj = session.history[-1]
                user_msg = create_message_component("user", user_input)
                ai_msg = create_message_component(
                    "assistant",
                    f"❌ {response.get('message', 'Error processing request')}",
                    msg_id=assistant_msg_obj.msg_id if assistant_msg_obj else None,
                )
                twohop_paths = []

            # Strip suggestions from all previous messages — only the newest reply
            # should show pill questions, avoiding repeated rows of the same pills.
            previous = _strip_message_suggestions(list(current_messages) if current_messages else [])
            messages = previous + [user_msg, ai_msg]

            logger.info(f"DEBUG: send_message SUCCESS. Clearing inputs for trigger: {trigger_id}")
            return messages, messages, "", "", "", "", None, False, False, twohop_paths

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            from webapp.components.chat import create_message_component

            error_msg = create_message_component("assistant", f"❌ Error: {str(e)}")
            messages = list(current_messages) if current_messages else []
            messages.append(error_msg)
            return messages, messages, "", "", "", "", None, False, False, []

    @app.callback(
        [
            Output("chat-messages", "children", allow_duplicate=True),
            Output("chat-session-active", "data", allow_duplicate=True),
            Output("chat-status", "children", allow_duplicate=True),
            Output("chat-input-box", "disabled", allow_duplicate=True),
            Output("chat-send-btn", "disabled", allow_duplicate=True),
            Output("clear-chat-btn", "style", allow_duplicate=True),
            Output("chat-context-banner", "children", allow_duplicate=True),
            Output("chat-context-banner", "style", allow_duplicate=True),
        ],
        Input("clear-chat-btn", "n_clicks"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def clear_chat(n_clicks, session_data):
        """Clear chat history and reset session"""
        global _sessions

        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        # Clear session
        try:
            savepath = _resolve_savepath(session_data)
        except SessionPathError:
            savepath = None

        if savepath and savepath["graph"] in _sessions:
            session_data = _sessions.pop(savepath["graph"])
            session_data["session"].clear()
            session_data["rag"].clear()

        messages = [
            html.Div(
                [
                    html.Div("💬 Welcome to AI Chat!", className="text-primary fw-bold text-center mb-2"),
                    html.Div(
                        "Select edges in the graph, then click 'Analyze Selection' to start chatting.",
                        className="text-muted text-center small",
                    ),
                ],
                id="chat-welcome-message",
            )
        ]

        return (
            messages,
            False,  # Session not active
            "",  # Clear status
            True,  # Disable input
            True,  # Disable send
            {"display": "none"},  # Hide clear button
            None,
            {"display": "none"},
        )

    @app.callback(
        Output("download-chat-history", "data"),
        Input("download-chat-btn", "n_clicks"),
        [
            State("data-input", "value"),
            State("llm-provider-selector", "value"),
            State("openai-model-selector", "value"),
            State("openai-custom-model-input", "value"),
            State("google-model-selector", "value"),
            State("llm-model-input", "value"),
            State("current-session-path", "data"),
        ],
        prevent_initial_call=True,
    )
    def download_chat_history(
        n_clicks, initial_query, provider, oa_model, oa_custom, g_model, l_model, session_data
    ):
        global _sessions
        try:
            savepath = _resolve_savepath(session_data)
        except SessionPathError:
            savepath = None
        if not n_clicks or not savepath or savepath["graph"] not in _sessions:
            raise dash.exceptions.PreventUpdate

        session_data = _sessions[savepath["graph"]]
        session = session_data["session"]

        if not session or not session.history:
            raise dash.exceptions.PreventUpdate

        import datetime
        import html as html_lib
        import markdown
        from webapp.llm import llm_client

        # Determine the model name used
        if provider == "openai":
            model_name = oa_custom if oa_model == "custom" else oa_model
        elif provider == "google":
            model_name = g_model
        else:
            model_name = l_model

        # Use AI to generate a research title based on chat history
        research_title = "NetMedEx Professional Chat Transcript"
        try:
            # Combine first few exchanges for context
            context_messages = []
            for m in session.history[1:5]:  # Skip system, take first 4
                context_messages.append(f"{m.role}: {m.content[:200]}")

            context_text = "\n".join(context_messages)
            title_prompt = (
                "Based on the following biomedical research chat snippet, "
                "generate a concise, professional research subject title (max 12 words). "
                "Return ONLY the title text, no quotes or explanations.\n\n"
                f"Context:\n{context_text}"
            )
            ai_title = llm_client.chat_completion_text(
                messages=[{"role": "user", "content": title_prompt}],
                max_tokens=50,
                temperature=0.3,
            )
            if ai_title and len(ai_title.strip()) > 5:
                research_title = ai_title.strip()
        except Exception as e:
            logger.error(f"Error generating AI title for transcript: {e}")

        def hyperlink_pmids(html_text):
            pubmed_base = "https://pubmed.ncbi.nlm.nih.gov"
            link_style = "color:#0084ff; text-decoration:none; font-weight:500;"

            def make_link_prefixed(match):
                # Matches: PMID:12345678 / PMID: 12345678 / PMID：12345678
                full_match = match.group(0)
                pmid = match.group(2)
                return f'<a href="{pubmed_base}/{pmid}/" target="_blank" style="{link_style}">{full_match}</a>'

            def make_link_bracketed(match):
                # Matches: [12345678] — bare number in brackets (LLM citation style)
                pmid = match.group(1)
                return f'[<a href="{pubmed_base}/{pmid}/" target="_blank" style="{link_style}">{pmid}</a>]'

            # Split on existing <a>…</a> blocks to avoid double-wrapping
            segments = re.split(r'(<a\s[^>]*>.*?</a>)', html_text, flags=re.DOTALL | re.IGNORECASE)
            result = []
            for i, seg in enumerate(segments):
                if i % 2 == 1:  # inside existing <a> tag – skip
                    result.append(seg)
                else:
                    # Pass 1: PMID:12345678 / PMID：12345678 (with prefix)
                    seg = re.sub(r"(?i)(PMID[：:]?\s*)(\d{7,10})", make_link_prefixed, seg)
                    # Pass 2: [12345678] (bare number in brackets, LLM citation style)
                    # Negative lookbehind (?<![a-zA-Z]) prevents matching SNP rsIDs (e.g. rs[1234567]),
                    # gene accessions, or any identifier where a letter immediately precedes the bracket.
                    seg = re.sub(r"(?<![a-zA-Z])\[(\d{7,10})\]", make_link_bracketed, seg)
                    result.append(seg)
            return "".join(result)

        def normalize_mermaid_blocks(text):
            if not text or "```mermaid" in text:
                return text
            pattern = re.compile(
                r"(^|\n)(graph\s+(?:LR|TD|TB|BT|RL)\b[\s\S]*?)(?=\n(?:\*\*|###|\Z))",
                flags=re.IGNORECASE,
            )

            def _wrap(match):
                prefix = match.group(1)
                block = match.group(2).strip()
                return f"{prefix}```mermaid\n{block}\n```"

            return re.sub(pattern, _wrap, text, count=1)

        def md_to_html(text):
            text = normalize_mermaid_blocks(html_lib.escape(text or ""))
            # 1. Render Markdown first for structural integrity
            html_body = markdown.markdown(
                text,
                extensions=["extra", "sane_lists", "nl2br"],
                output_format="html",
            )
            # 2. Hyperlink PMIDs in the resulting HTML text
            html_body = hyperlink_pmids(html_body)

            def style_header(match):
                return (
                    "<div style='font-weight:700; color:#007bff; margin-top:12px;"
                    " border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:3px;"
                    " margin-bottom:8px; font-size:16px;'>"
                    f"{match.group(1)}</div>"
                )

            html_body = re.sub(
                r"<h2>(.*?)</h2>",
                style_header,
                html_body,
                flags=re.IGNORECASE | re.DOTALL,
            )

            return html_body

        html_content = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            f"<title>{html_lib.escape(research_title)}</title>",
            "<style>",
            "body { background-color: #f0f2f5; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 40px 20px; color: #1c1e21; line-height: 1.5; }",
            ".chat-container { max-width: 850px; margin: 0 auto; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 12px 40px rgba(0,0,0,0.08); }",
            ".header { padding-bottom: 25px; border-bottom: 2px solid #f0f2f5; margin-bottom: 30px; }",
            ".header h1 { margin: 0; font-size: 30px; color: #1a1b1e; font-weight: 800; line-height: 1.2; letter-spacing: -0.02em; }",
            ".metadata { margin-top: 20px; padding: 15px 20px; background: #f8f9fa; border-radius: 12px; border-left: 5px solid #00a67e; font-size: 14px; color: #495057; }",
            ".metadata-item { margin-bottom: 6px; display: flex; align-items: baseline; }",
            ".metadata-label { font-weight: 700; color: #212529; width: 110px; flex-shrink: 0; }",
            ".timestamp { font-size: 12px; color: #adb5bd; margin-top: 15px; text-align: right; font-weight: 500; }",
            ".chat-box { display: flex; flex-direction: column; gap: 32px; }",
            ".message-row { display: flex; width: 100%; align-items: flex-start; gap: 12px; }",
            ".user-row { flex-direction: row-reverse; }",
            ".assistant-row { flex-direction: row; }",
            ".avatar { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; color: white; margin-top: 4px; }",
            ".user-avatar { background: linear-gradient(135deg, #6e8efb, #a777e3); }",
            ".assistant-avatar { background: linear-gradient(135deg, #00b09b, #96c93d); }",
            ".bubble { max-width: 85%; padding: 16px 22px; border-radius: 20px; font-size: 15.5px; line-height: 1.6; position: relative; }",
            ".user-bubble { background-color: #007bff; color: #ffffff; border-bottom-right-radius: 4px; box-shadow: 0 4px 15px rgba(0,123,255,0.2); }",
            ".assistant-bubble { background-color: #ffffff; color: #212529; border-bottom-left-radius: 4px; border: 1px solid #e9ecef; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }",
            ".content p { margin-top: 0; margin-bottom: 12px; }",
            ".content p:last-child { margin-bottom: 0; }",
            "table { border-collapse: collapse; width: 100%; margin: 16px 0; border: 1px solid #dee2e6; border-radius: 8px; overflow: hidden; font-size: 14px; }",
            "th, td { border: 1px solid #dee2e6; padding: 12px 16px; text-align: left; }",
            "th { background-color: #f1f3f5; font-weight: 700; color: #343a40; }",
            ".sources-box { margin-top: 16px; padding-top: 12px; border-top: 1px solid #f1f3f5; font-size: 13px; color: #6c757d; }",
            ".suggestions-box { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }",
            ".suggested-pill { background-color: #f8f9fa; border: 1px solid #e9ecef; color: #495057; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; cursor: default; }",
            "a { color: #007bff; text-decoration: none; transition: color 0.2s; }",
            "a:hover { color: #0056b3; text-decoration: underline; }",
            "ul, ol { margin: 12px 0; padding-left: 24px; }",
            "li { margin-bottom: 8px; }",
            "li:last-child { margin-bottom: 0; }",
            "strong { font-weight: 700; color: inherit; }",
            ".content .mermaid { overflow-x: auto; max-width: 100%; padding: 4px 0; }",
            ".content .mermaid svg { max-width: 100%; height: auto; }",
            "</style>",
            "<script src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'></script>",
            "</head>",
            "<body>",
            "<div class='chat-container'>",
            "<div class='header'>",
            f"<h1>{html_lib.escape(research_title)}</h1>",
            "<div class='metadata'>",
            f"<div class='metadata-item'><span class='metadata-label'>LLM Model:</span> {html_lib.escape(str(model_name or 'N/A'))} ({html_lib.escape(str(provider or 'unknown').capitalize())})</div>",
            f"<div class='metadata-item'><span class='metadata-label'>Initial Query:</span> {html_lib.escape(initial_query or 'N/A')}</div>",
            "</div>",
            f"<div class='timestamp'>Generated by NetMedEx on {datetime.datetime.now().strftime('%B %d, %Y - %H:%M:%S')}</div>",
            "</div>",
            "<div class='chat-box'>",
        ]

        user_svg = '<svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M11 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/><path fill-rule="evenodd" d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1z"/></svg>'
        assistant_svg = '<svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5ZM3 8.062C3 6.76 4.235 5.765 5.53 5.889a28.02 28.02 0 0 1 4.94 0C11.765 5.765 13 6.76 13 8.062v1.157a.933.933 0 0 1-.765.935c-.845.147-2.34.346-4.235.346-1.895 0-3.39-.2-4.235-.346A.933.933 0 0 1 3 9.219V8.062Zm4.542-.827a.25.25 0 0 0-.217.068l-.92.9a24.767 24.767 0 0 1-1.871-.183.25.25 0 0 0-.068.495c.55.076 1.232.149 2.02.193a.25.25 0 0 0 .189-.071l.758-.736.847 1.71a.25.25 0 0 0 .404.062l.932-.97a25.286 25.286 0 0 0 1.922-.188.25.25 0 0 0-.068-.495c-.538.074-1.207.145-1.98.189a.25.25 0 0 0-.166.076l-.754.785-.842-1.7a.25.25 0 0 0-.182-.135Z"/><path d="M8.5 1.866a1 1 0 1 0-1 0V3h-2A4.5 4.5 0 0 0 1 7.5V8a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1v-.5A4.5 4.5 0 0 0 10.5 3h-2V1.866ZM14 7.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5A3.5 3.5 0 0 1 5.5 4h5A3.5 3.5 0 0 1 14 7.5Z"/></svg>'

        skip_prompts = {
            "Please provide a structured summary of the selected research based on the abstracts and graph structure.",
            "Please provide a concise initial brief for the selected abstracts",
        }

        # Resolve display query: prefer data-input value; fall back to first real user message
        if not initial_query:
            for msg in session.history:
                if msg.role == "user" and msg.content and not any(
                    sp in msg.content for sp in skip_prompts
                ):
                    initial_query = msg.content.strip()[:300]
                    if len(msg.content.strip()) > 300:
                        initial_query += "…"
                    break

        skip_prompt = "Please provide a structured summary of the selected research based on the abstracts and graph structure."
        last_msg_content = None
        for msg in session.history:
            if msg.role == "system":
                continue
            if not msg.content or msg.content.strip() == "":
                continue
            if skip_prompt in msg.content:
                continue

            # Simple deduplication for consecutive identity messages
            current_content = msg.content.strip()
            if current_content == last_msg_content:
                continue
            last_msg_content = current_content

            is_user = msg.role == "user"
            row_class = "user-row" if is_user else "assistant-row"
            bubble_class = "user-bubble" if is_user else "assistant-bubble"
            avatar_class = "user-avatar" if is_user else "assistant-avatar"
            avatar_svg = user_svg if is_user else assistant_svg

            # Separate suggestions for assistant messages
            suggestions = []
            clean_text = msg.content
            if not is_user:
                suggestions, clean_text = parse_suggestions(msg.content)

            content_html = md_to_html(clean_text)

            html_content.append(f"<div class='message-row {row_class}'>")
            html_content.append(f"<div class='avatar {avatar_class}'>{avatar_svg}</div>")
            html_content.append(f"<div class='bubble {bubble_class}'>")
            html_content.append(f"<div class='content'>{content_html}</div>")

            # Add suggested question pills
            if suggestions:
                html_content.append("<div class='suggestions-box'>")
                for q in suggestions[:3]:
                    html_content.append(
                        f"<div class='suggested-pill'>{html_lib.escape(q)}</div>"
                    )
                html_content.append("</div>")

            if hasattr(msg, "sources") and msg.sources:
                source_links = [
                    f'<a href="https://pubmed.ncbi.nlm.nih.gov/{html_lib.escape(str(p))}/" target="_blank">[PMID:{html_lib.escape(str(p))}]</a>'
                    for p in msg.sources
                ]
                html_content.append(
                    f"<div class='sources-box'><strong>References:</strong> {', '.join(source_links)}</div>"
                )

            html_content.append("</div></div>")

        html_content.extend(
            [
                "<script>",
                "(function(){",
                "  function convertCodeBlocks(){",
                "    const codeBlocks = document.querySelectorAll('pre code.language-mermaid');",
                "    codeBlocks.forEach((code) => {",
                "      const pre = code.closest('pre');",
                "      if (!pre) return;",
                "      const graphDef = (code.textContent || '').trim();",
                "      if (!graphDef) return;",
                "      const wrapper = document.createElement('div');",
                "      wrapper.className = 'mermaid';",
                "      wrapper.textContent = graphDef;",
                "      pre.replaceWith(wrapper);",
                "    });",
                "  }",
                "  function initMermaid(){",
                "    if (!window.mermaid) return;",
                "    window.mermaid.initialize({startOnLoad:false, securityLevel:'strict', theme:'default'});",
                "    convertCodeBlocks();",
                "    if (typeof window.mermaid.run === 'function') {",
                "      window.mermaid.run({querySelector: '.mermaid'});",
                "    } else if (typeof window.mermaid.init === 'function') {",
                "      window.mermaid.init(undefined, document.querySelectorAll('.mermaid'));",
                "    }",
                "  }",
                "  if (document.readyState === 'loading') {",
                "    document.addEventListener('DOMContentLoaded', initMermaid);",
                "  } else {",
                "    initMermaid();",
                "  }",
                "})();",
                "</script>",
                "</div></div></body></html>",
            ]
        )

        final_html = "\n".join(html_content)
        filename = f"NetMedEx_Transcript_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        return dcc.send_string(final_html, filename)

    @app.callback(
        [
            Output("chat-modal", "is_open"),
            Output("modal-chat-content", "children"),
        ],
        [
            Input("expand-chat-btn", "n_clicks"),
            Input("close-modal-btn", "n_clicks"),
        ],
        [
            State("chat-modal", "is_open"),
            State("chat-messages", "children"),
        ],
        prevent_initial_call=True,
    )
    def toggle_chat_modal(n1, n2, is_open, current_content):
        """Toggle chat modal and sync content"""
        ctx = dash.callback_context

        if not ctx.triggered:
            return is_open, current_content

        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        logger.info(f"Modal toggle triggered by: {button_id}")

        if button_id in ["expand-chat-btn", "close-modal-btn"]:
            return not is_open, current_content

        return is_open, current_content

    # Callback to handle suggested question clicks by populating the input box (Backported from Pediatric Portal)
    @app.callback(
        [
            Output("chat-input-box", "value", allow_duplicate=True),
            Output("modal-chat-input", "value", allow_duplicate=True),
            Output("suggested-question-store", "data", allow_duplicate=True),
            Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
        ],
        [Input({"type": "suggested-question", "index": ALL}, "n_clicks")],
        [
            State({"type": "suggested-question", "index": ALL}, "children"),
            State("sidebar-panel-toggle", "active_tab"),
        ],
        prevent_initial_call=True,
    )
    def handle_suggested_question(n_clicks_list, question_texts, current_tab):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n_clicks_list):
            raise dash.exceptions.PreventUpdate

        trigger_info = ctx.triggered[0]

        # Guard: when new pills are added to the DOM after an AI response, Dash
        # re-fires this ALL-pattern callback with value=None/0 for the new pill
        # while old pills still have n_clicks>0, causing any() to pass falsely.
        # Only proceed if the triggering component actually received a real click.
        if not trigger_info.get("value"):
            raise dash.exceptions.PreventUpdate

        import json

        try:
            prop_id = trigger_info["prop_id"]
            # Format is {"index":"...","type":"suggested-question"}.n_clicks
            json_str = prop_id.split(".n_clicks")[0]
            triggered_index = json.loads(json_str)["index"]

            # Find the match in question_texts
            inputs = ctx.inputs_list[0]
            for i, input_item in enumerate(inputs):
                if input_item["id"]["index"] == triggered_index:
                    matched_text = question_texts[i]
                    return "", "", matched_text, "chat"
        except Exception as e:
            logger.error(f"Error identifying clicked question: {e}")

        raise dash.exceptions.PreventUpdate

    # Clientside callback to scroll sidebar...
    app.clientside_callback(
        """
        function(active_tab) {
            if (active_tab === 'chat') {
                setTimeout(function() {
                    const sidebar = document.querySelector('.sidebar');
                    if (sidebar) {
                        sidebar.scrollTo({
                            top: sidebar.scrollHeight,
                            behavior: 'smooth'
                        });
                    }
                }, 300);
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("chat-status", "style"),  # Using a dummy output
        Input("sidebar-panel-toggle", "active_tab"),
        prevent_initial_call=False,
    )

    # Clientside callback to auto-scroll chat containers when messages are added.
    # If a user message is present (identified by .chat-message-user-anchor), scroll
    # it into view so users see their question at the top, rather than the bottom.
    app.clientside_callback(
        """
        function(children) {
            if (!children) return window.dash_clientside.no_update;
            setTimeout(function() {
                var chatContainer = document.getElementById('chat-messages');
                if (!chatContainer) return;
                // Find the last user message anchor and scroll it into view
                var anchors = chatContainer.querySelectorAll('.chat-message-user-anchor');
                var lastMessage = chatContainer.lastElementChild;
                if (lastMessage && lastMessage.classList.contains('chat-message-assistant')) {
                    // When assistant responds, find the MOST RECENT user question and scroll it to top
                    const latestAnchor = anchors.length > 0 ? anchors[anchors.length - 1] : null;
                    if (latestAnchor) {
                        latestAnchor.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    } else {
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                } else if (anchors.length > 0) {
                    var lastAnchor = anchors[anchors.length - 1];
                    lastAnchor.scrollIntoView({behavior: 'smooth', block: 'start'});
                } else {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 150);
            return window.dash_clientside.no_update;
        }
        """,
        Output("chat-messages", "style"),  # dummy output
        Input("chat-messages", "children"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(children) {
            if (!children) return window.dash_clientside.no_update;
            setTimeout(function() {
                var chatContainer = document.getElementById('modal-chat-content');
                if (!chatContainer) return;
                
                var anchors = chatContainer.querySelectorAll('.chat-message-user-anchor');
                var lastMessage = chatContainer.lastElementChild;
                
                if (lastMessage && lastMessage.classList.contains('chat-message-assistant')) {
                    // When assistant responds, find the MOST RECENT user question and scroll it to top
                    const latestAnchor = anchors.length > 0 ? anchors[anchors.length - 1] : null;
                    if (latestAnchor) {
                        latestAnchor.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    } else {
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                } else if (anchors.length > 0) {
                    var lastAnchor = anchors[anchors.length - 1];
                    lastAnchor.scrollIntoView({behavior: 'smooth', block: 'start'});
                } else {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 150);
            return window.dash_clientside.no_update;
        }
        """,
        Output("modal-chat-content", "style"),  # dummy output
        Input("modal-chat-content", "children"),
        prevent_initial_call=True,
    )
