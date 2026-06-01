from __future__ import annotations

import logging
import re

import dash
from dash import ALL, Input, Output, State, dcc, html, no_update

from webapp.utils import SessionPathError, resolve_session_savepath
from webapp.callbacks.pipeline import detect_query_language

logger = logging.getLogger(__name__)

# Local stores for chat state (keyed by graph path)
_sessions: dict[str, dict] = {}

COMMUNITY_NODE_PATTERN = re.compile(r"^c\d+$")


def _resolve_savepath(session_data):
    return resolve_session_savepath(session_data)


def _abstract_documents_from_graph(
    G,
    *,
    limit: int | None = None,
    pmid_filter: set[str] | None = None,
):
    import datetime

    from netmedex.rag import AbstractDocument
    from netmedex.utils import calculate_citation_weight

    pmid_abstracts = G.graph.get("pmid_abstract", {}) or {}
    pmid_titles = G.graph.get("pmid_title", {}) or {}
    pmid_metadata = G.graph.get("pmid_metadata", {}) or {}
    current_year = datetime.datetime.now().year

    weighted_pmids = []
    for raw_pmid in pmid_abstracts:
        pmid = str(raw_pmid)
        if pmid_filter is not None and pmid not in pmid_filter:
            continue
        meta = pmid_metadata.get(raw_pmid, pmid_metadata.get(pmid, {}))
        if not isinstance(meta, dict):
            meta = {}
        weight = calculate_citation_weight(
            meta.get("citation_count"), meta.get("date"), current_year
        )
        weighted_pmids.append((pmid, raw_pmid, weight))

    weighted_pmids.sort(key=lambda item: item[2], reverse=True)
    if limit is not None:
        weighted_pmids = weighted_pmids[:limit]

    documents = []
    for pmid, raw_pmid, weight in weighted_pmids:
        documents.append(
            AbstractDocument(
                pmid=pmid,
                title=str(pmid_titles.get(raw_pmid, pmid_titles.get(pmid, f"PMID {pmid}")) or f"PMID {pmid}"),
                abstract=str(pmid_abstracts.get(raw_pmid, pmid_abstracts.get(pmid, "")) or ""),
                entities=[],
                edges=[],
                weight=weight,
            )
        )
    return documents


def _initialize_llm_from_callback_state(
    *,
    llm_provider,
    openai_api_key=None,
    openai_model=None,
    openai_custom_model=None,
    google_api_key=None,
    google_model=None,
    google_safety_setting=None,
    llm_base_url=None,
    llm_model=None,
    openrouter_api_key=None,
    openrouter_model=None,
    openrouter_custom_model=None,
    nvidia_api_key=None,
    nvidia_nim_base_url=None,
    nvidia_model=None,
    groq_api_key=None,
    groq_model=None,
    groq_custom_model=None,
    anthropic_api_key=None,
    anthropic_model=None,
    anthropic_custom_model=None,
):
    from webapp.llm import initialize_llm_client_from_settings, llm_client

    return initialize_llm_client_from_settings(
        llm_client,
        provider=llm_provider,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_custom_model=openai_custom_model,
        google_api_key=google_api_key,
        google_model=google_model,
        google_safety_setting=google_safety_setting,
        local_base_url=llm_base_url,
        local_model=llm_model,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        openrouter_custom_model=openrouter_custom_model,
        nvidia_api_key=nvidia_api_key,
        nvidia_nim_base_url=nvidia_nim_base_url,
        nvidia_model=nvidia_model,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_custom_model=groq_custom_model,
        anthropic_api_key=anthropic_api_key,
        anthropic_model=anthropic_model,
        anthropic_custom_model=anthropic_custom_model,
    )


def _rebuild_chat_session_from_graph(savepath, llm_client, topic: str | None = None):
    from netmedex.chat import ChatSession
    from netmedex.graph import load_graph
    from netmedex.graph_rag import GraphRetriever
    from netmedex.rag import AbstractRAG
    import pathlib as _pathlib

    G = load_graph(savepath["graph"])
    documents = _abstract_documents_from_graph(G)
    if not documents:
        raise ValueError("No abstracts available in graph file")

    rag_system = AbstractRAG(llm_client)
    rag_system.index_abstracts(documents)
    graph_retriever = GraphRetriever(G, node_rag=None)
    session = ChatSession(
        rag_system,
        llm_client,
        graph_retriever=graph_retriever,
        topic=topic or "biomedical research",
    )

    # Try to load chat history from disk
    history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
    session.load_from_file(str(history_file))

    _sessions[savepath["graph"]] = {
        "session": session,
        "rag": rag_system,
        "rebuilt_from_graph": True,
    }
    logger.info(
        "Rebuilt chat session from graph file: %s abstracts indexed",
        len(documents),
    )
    return _sessions[savepath["graph"]]


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


def rename_suggested_question_ids(node, suffix="-modal"):
    """
    Recursively traverse a component tree (either Dash component objects or
    serialized dictionaries) and append a suffix to the index of any
    component with id of type {"type": "suggested-question", "index": ...}.
    """
    if node is None:
        return None

    # Handle dictionary representation (serialized by Dash)
    if isinstance(node, dict):
        props = node.get("props", {})
        # If node has props and id is a dict
        comp_id = props.get("id")
        if isinstance(comp_id, dict) and comp_id.get("type") == "suggested-question":
            new_id = comp_id.copy()
            idx = str(comp_id.get("index", ""))
            if not idx.endswith(suffix):
                new_id["index"] = idx + suffix
            node = {**node, "props": {**props, "id": new_id}}
            props = node["props"]
            
        # Recurse through children
        children = props.get("children")
        if isinstance(children, list):
            new_children = [rename_suggested_question_ids(c, suffix) for c in children]
            node = {**node, "props": {**props, "children": new_children}}
        elif children is not None:
            new_children = rename_suggested_question_ids(children, suffix)
            node = {**node, "props": {**props, "children": new_children}}
        return node

    # Handle Dash component instance
    import copy
    node_copy = copy.copy(node)
    
    # Check for id attribute
    comp_id = getattr(node_copy, "id", None)
    if isinstance(comp_id, dict) and comp_id.get("type") == "suggested-question":
        new_id = comp_id.copy()
        idx = str(comp_id.get("index", ""))
        if not idx.endswith(suffix):
            new_id["index"] = idx + suffix
        node_copy.id = new_id
        
    # Recurse children
    if hasattr(node_copy, "children") and node_copy.children is not None:
        children = node_copy.children
        if isinstance(children, list):
            node_copy.children = [rename_suggested_question_ids(c, suffix) for c in children]
        else:
            node_copy.children = rename_suggested_question_ids(children, suffix)
            
    return node_copy


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

    def _clean_questions(raw_list: list) -> list:
        suggestions: list = []
        seen: set = set()
        for q in raw_list:
            q = re.sub(r"\s+", " ", q).strip()
            # Strip leading/trailing asterisks or brackets if they were captured
            q = re.sub(r"^[\s*_\[\]()\"'-]+|[\s*_\[\]()\"'-]+$", "", q)
            q = q.rstrip("?？.！!").strip()
            if q and len(q) > 3 and q.lower() not in seen:
                suggestions.append(q)
                seen.add(q.lower())
            if len(suggestions) >= 3:
                break
        return suggestions

    # Unified Q1 search pattern:
    # Matches Q1 optionally surrounded by asterisks/brackets, followed by colon/dot, and any trailing spaces/punctuation.
    q1_pattern = r"(?:\*\*|)?\[?(?:\*\*|)?\bQ1\b[\]*]*\s*[:.][\]*:\s.-]*"
    q1_match = re.search(q1_pattern, content, re.IGNORECASE)

    if not q1_match:
        # No Q1 marker found at all — fall back to generic default questions
        # so that pill buttons always appear even when the LLM omits the markers.
        if re.search(r"Suggested(?:\s+Follow-up)?\s+Questions?", content, re.IGNORECASE):
            return _default_questions(content), content
        return _default_questions(content), content  # always show fallback pills

    cut = q1_match.start()
    
    # Check if bracketed format (brackets enclosing the entire question rather than just the marker)
    matched_text = q1_match.group(0)
    q1_idx = matched_text.lower().find("q1")
    has_leading_bracket = "[" in matched_text[:q1_idx]
    
    # Find the position of the colon or dot
    colon_match = re.search(r"[:.]", matched_text)
    colon_idx = colon_match.start() if colon_match else len(matched_text)
    has_bracket_before_colon = "]" in matched_text[:colon_idx]
    
    use_bracketed = has_leading_bracket and not has_bracket_before_colon

    before = content[:cut].rstrip()
    before = re.sub(
        r"\n[^\n]*(?:Layer\s*5|建議問題|Suggested(?:\s+Follow-up)?\s+Questions?|"
        r"建議的問題|提案された質問|권장 후속 질문)[^\n]*$",
        "",
        before,
        flags=re.IGNORECASE,
    ).rstrip()

    tail = content[cut:]

    if use_bracketed:
        # Matches [Q1: text] or [**Q1**: text] or [**Q1:** text]
        raw_qs = re.findall(
            r"\[(?:\*\*)?Q\d+(?:\*\*)?\s*[:.]\s*(.*?)\]",
            tail,
            re.IGNORECASE | re.DOTALL,
        )
    else:
        # Split on any Q\d+ marker variation
        marker_pattern = r"(?:\*\*|)?\[?(?:\*\*|)?\bQ\d+\b[\]*]*\s*[:.][\]*:\s.-]*"
        parts = re.split(marker_pattern, tail, flags=re.IGNORECASE)
        raw_qs = [p.strip() for p in parts if p.strip()]

    suggestions = _clean_questions(raw_qs)
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
            State("cy", "selectedNodeData"),
            State("cy", "selectedEdgeData"),
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
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
            State("groq-custom-model-input", "value"),
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
            State("anthropic-custom-model-input", "value"),
            State("chat-messages", "children"),
        ],
        prevent_initial_call=True,
    )
    def auto_initialize_chat(
        current_tab,
        session_data,
        is_new_graph,
        selected_nodes,
        selected_edges,
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
        nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        groq_api_key,
        groq_model,
        groq_custom_model,
        anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
        current_messages,
    ):
        """
        Automatically initialize chat with an overall summary when a new graph is loaded.
        """
        # Trigger conditions:
        # 1. User must be in the chat tab
        # 2. Graph session path must be active
        if current_tab != "chat" or not session_data:
            raise dash.exceptions.PreventUpdate

        global _sessions
        try:
            savepath = _resolve_savepath(session_data)
        except SessionPathError:
            raise dash.exceptions.PreventUpdate
        session_key = savepath["graph"]

        # Check if the UI is currently empty / showing welcome message
        is_ui_empty = True
        if current_messages:
            if isinstance(current_messages, list):
                for component in current_messages:
                    if isinstance(component, dict):
                        props = component.get("props", {})
                        if props.get("id") != "chat-welcome-message":
                            is_ui_empty = False
                            break
            elif isinstance(current_messages, dict):
                props = current_messages.get("props", {})
                if props.get("id") != "chat-welcome-message":
                    is_ui_empty = False

        import pathlib as _pathlib
        history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
        
        has_history_in_memory = (
            session_key in _sessions 
            and _sessions[session_key].get("session") 
            and (_sessions[session_key]["session"].full_history or _sessions[session_key]["session"].history)
        )
        has_history_on_disk = history_file.exists()

        if has_history_in_memory or has_history_on_disk:
            if not is_ui_empty:
                raise dash.exceptions.PreventUpdate
                
            logger.info("auto_initialize_chat: Restoring chat history to the UI")
            try:
                from netmedex.chat import ChatSession
                from netmedex.graph import load_graph
                from netmedex.rag import AbstractRAG
                from netmedex.graph_rag import GraphRetriever
                from webapp.components.chat import create_message_component
                import re

                G = load_graph(savepath["graph"])
                effective_query = search_query or G.graph.get("query", "")
                
                _query_lang = detect_query_language(effective_query) if effective_query else None
                if _query_lang and _query_lang != "English":
                    effective_language = _query_lang
                elif session_language and session_language != "English":
                    effective_language = session_language
                elif G.graph.get("language") and G.graph["language"] != "English":
                    effective_language = G.graph["language"]
                elif session_language:
                    effective_language = session_language
                else:
                    effective_language = "English"

                # Filter community nodes (c0, c1, …) which carry no PMID data.
                real_selected_nodes = [
                    n for n in (selected_nodes or [])
                    if not COMMUNITY_NODE_PATTERN.match(str(n.get("id", "")))
                ]
                has_selection = bool((selected_edges or []) or real_selected_nodes)
                if has_selection:
                    selection_pmids = set()
                    for edge in (selected_edges or []):
                        ep = edge.get("pmids", [])
                        if isinstance(ep, str):
                            selection_pmids.add(ep)
                        else:
                            selection_pmids.update(str(p) for p in ep)
                    for node in real_selected_nodes:
                        np_ = node.get("pmids", [])
                        if isinstance(np_, str):
                            selection_pmids.add(np_)
                        else:
                            selection_pmids.update(str(p) for p in np_)
                    documents = _abstract_documents_from_graph(G, pmid_filter=selection_pmids)
                else:
                    documents = _abstract_documents_from_graph(G, limit=50)

                if not documents:
                    raise ValueError("No abstracts available for summary")

                llm_client = _initialize_llm_from_callback_state(
                    llm_provider=llm_provider,
                    openai_api_key=openai_api_key,
                    openai_model=openai_model,
                    openai_custom_model=openai_custom_model,
                    google_api_key=google_api_key,
                    google_model=google_model,
                    google_safety_setting=google_safety_setting,
                    llm_base_url=llm_base_url,
                    llm_model=llm_model,
                    openrouter_api_key=openrouter_api_key,
                    openrouter_model=openrouter_model,
                    openrouter_custom_model=openrouter_custom_model,
                    nvidia_api_key=nvidia_api_key,
                    nvidia_nim_base_url=nvidia_nim_base_url,
                    nvidia_model=nvidia_model,
                    groq_api_key=groq_api_key,
                    groq_model=groq_model,
                    groq_custom_model=groq_custom_model,
                    anthropic_api_key=anthropic_api_key,
                    anthropic_model=anthropic_model,
                    anthropic_custom_model=anthropic_custom_model,
                )

                if not has_history_in_memory:
                    rag_system = AbstractRAG(llm_client)
                    rag_system.index_abstracts(documents)
                    graph_retriever_auto = GraphRetriever(G, node_rag=None)

                    session = ChatSession(
                        rag_system,
                        llm_client,
                        graph_retriever=graph_retriever_auto,
                        topic=effective_query if effective_query else "biomedical research overview",
                    )
                    session.load_from_file(str(history_file))
                    _sessions[session_key] = {"session": session, "rag": rag_system}
                else:
                    session = _sessions[session_key]["session"]
                    if has_history_on_disk:
                        session.load_from_file(str(history_file))

                # Render history messages to UI components
                ui_messages = []
                history_to_render = session.full_history if session.full_history else session.history
                for msg in history_to_render:
                    if msg.role == "system":
                        continue
                    if not msg.content or msg.content.strip() == "":
                        continue
                    
                    is_user = msg.role == "user"
                    if is_user:
                        comp = create_message_component("user", msg.content, msg_id=msg.msg_id)
                    else:
                        display_text = getattr(msg, "full_content", None) or msg.content
                        suggestions, clean_content = parse_suggestions(display_text)
                        
                        cited_in_msg = sorted(set(
                            re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", display_text)
                        ) | set(
                            re.findall(r"\[(\d{7,10})\]", display_text)
                        ) | set(msg.sources or []))
                        
                        comp = create_message_component(
                            "assistant",
                            clean_content,
                            cited_in_msg or msg.sources,
                            msg_id=msg.msg_id,
                            suggestions=suggestions,
                        )
                    ui_messages.append(comp)

                if ui_messages:
                    # Strip pill suggestions from all messages except the very last
                    # assistant message — only the newest reply should show pills.
                    # Find index of last assistant message
                    last_assistant_idx = None
                    for i in range(len(ui_messages) - 1, -1, -1):
                        m = ui_messages[i]
                        # Dash serializes components as dicts; check if it's an assistant bubble
                        # create_message_component uses className="chat-message-assistant mb-3"
                        if isinstance(m, dict):
                            cls = m.get("props", {}).get("className", "") or ""
                            if "chat-message-assistant" in cls:
                                last_assistant_idx = i
                                break
                        else:
                            # Dash component object
                            cls = getattr(m, "className", "") or ""
                            if "chat-message-assistant" in cls:
                                last_assistant_idx = i
                                break
                    if last_assistant_idx is not None:
                        stripped_part = _strip_message_suggestions(ui_messages[:last_assistant_idx])
                        ui_messages = stripped_part + ui_messages[last_assistant_idx:]
                    else:
                        ui_messages = _strip_message_suggestions(ui_messages)

                # Context banner
                if has_selection:
                    banner_text = (
                        f"Selected Sub-network · {effective_query}"
                        if effective_query
                        else "Selected Sub-network"
                    )
                else:
                    banner_text = (
                        f"Overall Findings for '{effective_query}'"
                        if effective_query
                        else "Full Dataset Summary"
                    )
                context_banner = [
                    html.Div(
                        [
                            html.Span("🔍 Research Context: ", className="fw-bold"),
                            html.Span(banner_text),
                        ],
                        className="chat-context-query",
                    )
                ]

                return (
                    True,   # session active
                    "",     # status
                    False,  # Input enabled
                    False,  # Send enabled
                    {"display": "block"},  # clear button style
                    context_banner,
                    {"display": "block"},  # banner style
                    ui_messages,           # chat-messages children
                    no_update,             # suggested-question-store
                    False,                 # is-new-graph reset
                )
            except Exception as e:
                logger.error(f"Error restoring chat history: {e}")
                if not is_new_graph:
                    raise dash.exceptions.PreventUpdate

        if not has_history_in_memory and not has_history_on_disk and not is_new_graph:
            raise dash.exceptions.PreventUpdate

        logger.info(f"auto_initialize_chat STARTING for tab={current_tab}")

        from netmedex.chat import ChatSession
        from netmedex.graph import load_graph
        from netmedex.rag import AbstractRAG

        llm_client = _initialize_llm_from_callback_state(
            llm_provider=llm_provider,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            openai_custom_model=openai_custom_model,
            google_api_key=google_api_key,
            google_model=google_model,
            google_safety_setting=google_safety_setting,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
            openrouter_custom_model=openrouter_custom_model,
            nvidia_api_key=nvidia_api_key,
            nvidia_nim_base_url=nvidia_nim_base_url,
            nvidia_model=nvidia_model,
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            groq_custom_model=groq_custom_model,
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            anthropic_custom_model=anthropic_custom_model,
        )

        if not llm_client.client and not llm_client.anthropic_client:
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

            # Restore the search query from the saved graph when the UI field is
            # empty (e.g. after a page reload or when loading a cached graph).
            effective_query = search_query or G.graph.get("query", "")

            # Language priority: query text is the most reliable signal.
            # If the query is clearly non-English, always honour that regardless of
            # what session_language or the graph metadata say (they can be stale or
            # set to "English" as a default by the upload/restore pipeline path).
            _query_lang = detect_query_language(effective_query) if effective_query else None
            if _query_lang and _query_lang != "English":
                effective_language = _query_lang
            elif session_language and session_language != "English":
                effective_language = session_language
            elif G.graph.get("language") and G.graph["language"] != "English":
                effective_language = G.graph["language"]
            elif session_language:
                effective_language = session_language
            else:
                effective_language = "English"

            # Determine whether a sub-network is selected in the Cytoscape graph.
            # Filter community nodes (c0, c1, …) which carry no PMID data.
            real_selected_nodes = [
                n for n in (selected_nodes or [])
                if not COMMUNITY_NODE_PATTERN.match(str(n.get("id", "")))
            ]
            has_selection = bool((selected_edges or []) or real_selected_nodes)

            if has_selection:
                # Use only the PMIDs from the selected sub-network.
                selection_pmids: set[str] = set()
                for edge in (selected_edges or []):
                    ep = edge.get("pmids", [])
                    if isinstance(ep, str):
                        selection_pmids.add(ep)
                    else:
                        selection_pmids.update(str(p) for p in ep)
                for node in real_selected_nodes:
                    np_ = node.get("pmids", [])
                    if isinstance(np_, str):
                        selection_pmids.add(np_)
                    else:
                        selection_pmids.update(str(p) for p in np_)

                documents = _abstract_documents_from_graph(G, pmid_filter=selection_pmids)
                context_label = "Selected Sub-network"
                logger.info(
                    f"auto_initialize_chat: using selection ({len(selection_pmids)} PMIDs, "
                    f"{len(documents)} documents)"
                )
            else:
                documents = _abstract_documents_from_graph(G, limit=50)
                context_label = "Full Dataset"
                logger.info(
                    f"auto_initialize_chat: no selection — using full graph ({len(documents)} documents)"
                )

            if not documents:
                raise ValueError("No abstracts available for summary")

            # Initialize RAG and Chat
            rag_system = AbstractRAG(llm_client)
            rag_system.index_abstracts(documents)

            # Add lightweight GraphRetriever (no NodeRAG — no expensive indexing required).
            # Substring matching alone is sufficient to resolve entity names from the query,
            # and it enables Layer 3 (Causal Mechanism) to populate when the graph has
            # directional edges (inhibits, activates, ameliorates, etc.).
            from netmedex.graph_rag import GraphRetriever
            graph_retriever_auto = GraphRetriever(G, node_rag=None)

            session = ChatSession(
                rag_system,
                llm_client,
                graph_retriever=graph_retriever_auto,
                topic=effective_query if effective_query else "biomedical research overview",
            )

            # Store session
            session_id = savepath["graph"]
            _sessions[session_id] = {"session": session, "rag": rag_system}

            prompt_lang = effective_language
            # The bootstrap prompt is kept short and uses a special sentinel so that
            # send_message() can detect it as an internal call and:
            #   1. Set search_query = self.topic  (the real search terms, not this prompt)
            #   2. Skip all translation passes
            # The actual 5-layer response format is governed entirely by the system_prompt
            # in ChatSession, so we do NOT duplicate format instructions here.
            topic_display = effective_query if effective_query else "the provided abstracts"
            bootstrap_prompt = (
                f"[INTERNAL_BOOTSTRAP] Provide a comprehensive integrated summary of {topic_display} "
                f"based on all provided PubMed abstracts. "
                f"Respond in {prompt_lang}."
            )

            summary_result = session.send_message(
                bootstrap_prompt,
                session_language=effective_language,
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
                if has_selection:
                    banner_text = (
                        f"Selected Sub-network · {effective_query}"
                        if effective_query
                        else "Selected Sub-network"
                    )
                else:
                    banner_text = (
                        f"Overall Findings for '{effective_query}'"
                        if effective_query
                        else "Full Dataset Summary"
                    )
                context_banner = [
                    html.Div(
                        [
                            html.Span("🔍 Research Context: ", className="fw-bold"),
                            html.Span(banner_text),
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
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
            State("groq-custom-model-input", "value"),
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
            State("anthropic-custom-model-input", "value"),
        ],
        running=[
            (
                Output("analyze-selection-btn", "disabled", allow_duplicate=True),
                True,
                False,
            ),
            (
                Output("analyze-selection-btn", "children", allow_duplicate=True),
                [html.I(className="bi bi-arrow-repeat bi-spin me-2"), "Analyzing..."],
                [html.I(className="bi bi-chat-dots me-2"), "Analyze Selection"],
            ),
        ],
        progress=[
            Output("chat-analyze-progress", "value"),
            Output("chat-analyze-status-text", "children"),
        ],
        background=True,
        prevent_initial_call=True,
    )

    def initialize_chat(
        set_progress,
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
        nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        groq_api_key,
        groq_model,
        groq_custom_model,
        anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
    ):
        logger.info("initialize_chat (MANUAL) triggered")
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

            t0 = time.time()
            logger.info("Starting Chat Analysis...")

            # Compact the diskcache WAL before starting so accumulated writes
            # from previous runs don't block set_progress() calls mid-callback.
            try:
                import sqlite3 as _sqlite3
                from pathlib import Path as _Path
                _wal_db = _Path(__file__).parent.parent / "cache" / "cache.db"
                if _wal_db.exists():
                    _wconn = _sqlite3.connect(str(_wal_db))
                    _wconn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    _wconn.close()
                    logger.debug("WAL checkpoint completed before initialize_chat")
            except Exception:
                pass

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

            llm_client = _initialize_llm_from_callback_state(
                llm_provider=llm_provider,
                openai_api_key=openai_api_key,
                openai_model=openai_model,
                openai_custom_model=openai_custom_model,
                google_api_key=google_api_key,
                google_model=google_model,
                google_safety_setting=google_safety_setting,
                llm_base_url=llm_base_url,
                llm_model=llm_model,
                openrouter_api_key=openrouter_api_key,
                openrouter_model=openrouter_model,
                openrouter_custom_model=openrouter_custom_model,
                nvidia_api_key=nvidia_api_key,
                nvidia_nim_base_url=nvidia_nim_base_url,
                nvidia_model=nvidia_model,
                groq_api_key=groq_api_key,
                groq_model=groq_model,
                groq_custom_model=groq_custom_model,
                anthropic_api_key=anthropic_api_key,
                anthropic_model=anthropic_model,
                anthropic_custom_model=anthropic_custom_model,
            )

            if not llm_client.client and not llm_client.anthropic_client:
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

            set_progress((5, "🔬 Loading graph..."))
            G = load_graph(savepath["graph"])
            t_load = time.time()
            logger.info(f"Graph loaded in {t_load - t0:.2f}s")

            # Restore the search query from the saved graph when the UI field is
            # empty (e.g. after a page reload or when loading a cached graph).
            search_query = search_query or G.graph.get("query", "")

            # Language priority: query text is the most reliable signal.
            # Non-English queries always take precedence over stale session/graph values.
            _query_lang = detect_query_language(search_query) if search_query else None
            if _query_lang and _query_lang != "English":
                effective_language = _query_lang
            elif session_language and session_language != "English":
                effective_language = session_language
            elif G.graph.get("language") and G.graph["language"] != "English":
                effective_language = G.graph["language"]
            elif session_language:
                effective_language = session_language
            else:
                effective_language = "English"

            raw_id_to_node = {str(nid): (nid, data) for nid, data in G.nodes(data=True)}
            cy_id_to_raw_id = {
                str(data.get("_id")): str(nid)
                for nid, data in G.nodes(data=True)
                if data.get("_id")
            }
            label_to_raw_ids = {}
            for nid, data in G.nodes(data=True):
                label = str(data.get("name", "")).lower().strip()
                if label:
                    label_to_raw_ids.setdefault(label, []).append(str(nid))

            def _pmids_from_graph_node(node_payload: dict) -> list[str]:
                candidates = []
                for key in ("raw_node_id", "node_id"):
                    if node_payload.get(key):
                        candidates.append(str(node_payload[key]))
                if node_payload.get("id"):
                    candidates.append(cy_id_to_raw_id.get(str(node_payload["id"]), ""))
                name_key = str(
                    node_payload.get("label") or node_payload.get("name") or ""
                ).lower().strip()
                candidates.extend(label_to_raw_ids.get(name_key, []))

                seen = set()
                pmids = []
                for raw_id in candidates:
                    if not raw_id or raw_id in seen:
                        continue
                    seen.add(raw_id)
                    graph_node = raw_id_to_node.get(raw_id)
                    if not graph_node:
                        continue
                    node_pmids = graph_node[1].get("pmids", [])
                    if isinstance(node_pmids, str):
                        pmids.append(node_pmids)
                    else:
                        pmids.extend(str(p) for p in node_pmids)
                return pmids

            def _edge_pmids_from_graph(edge_payload: dict) -> list[str]:
                raw_source = edge_payload.get("source_raw_id")
                raw_target = edge_payload.get("target_raw_id")
                if not raw_source and edge_payload.get("source"):
                    raw_source = cy_id_to_raw_id.get(str(edge_payload["source"]))
                if not raw_target and edge_payload.get("target"):
                    raw_target = cy_id_to_raw_id.get(str(edge_payload["target"]))

                source_node = raw_id_to_node.get(str(raw_source or ""))
                target_node = raw_id_to_node.get(str(raw_target or ""))
                if (
                    source_node
                    and target_node
                    and G.has_edge(source_node[0], target_node[0])
                ):
                    data = G.edges[source_node[0], target_node[0]]
                else:
                    source_name = str(edge_payload.get("source_name", "")).lower().strip()
                    target_name = str(edge_payload.get("target_name", "")).lower().strip()
                    data = None
                    for u in label_to_raw_ids.get(source_name, []):
                        for v in label_to_raw_ids.get(target_name, []):
                            u_node = raw_id_to_node.get(u)
                            v_node = raw_id_to_node.get(v)
                            if u_node and v_node and G.has_edge(u_node[0], v_node[0]):
                                data = G.edges[u_node[0], v_node[0]]
                                break
                        if data is not None:
                            break
                if not data:
                    return []
                if data.get("pmids"):
                    return [str(p) for p in data.get("pmids", [])]
                return [str(p) for p in data.get("relations", {}).keys()]

            # Extract PMIDs and build abstract documents
            pmid_data = {}
            for edge in selected_edges or []:
                edge_pmids = edge.get("pmids", []) or _edge_pmids_from_graph(edge)
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
                    node_pmids = node.get("pmids", []) or _pmids_from_graph_node(node)
                    if isinstance(node_pmids, str):
                        node_pmids = [node_pmids]

                    for pmid in node_pmids:
                        if pmid not in pmid_data:
                            # Nodes don't have edge data, so we leave edges empty
                            pmid_data[pmid] = {"pmid": pmid, "edges": []}

            # Get abstracts and metadata from graph.
            # Normalise all keys to str so lookups never fail due to int/str mismatch
            # (the graph may store PMIDs as integers internally).
            pmid_abstracts = {str(k): v for k, v in (G.graph.get("pmid_abstract", {}) or {}).items()}
            pmid_titles    = {str(k): v for k, v in (G.graph.get("pmid_title", {}) or {}).items()}
            pmid_metadata  = {str(k): v for k, v in (G.graph.get("pmid_metadata", {}) or {}).items()}

            # Shared weighting utility
            import datetime

            from netmedex.utils import calculate_citation_weight

            current_year = datetime.datetime.now().year

            # Preflight diagnostic — log before indexing
            pmid_count = len(pmid_data)
            matched_abstract_count = sum(1 for p in pmid_data if p in pmid_abstracts)
            logger.info(
                "Preflight: selected_nodes=%s selected_edges=%s pmids=%s abstracts_matched=%s/%s",
                len(selected_nodes or []),
                len(selected_edges or []),
                pmid_count,
                matched_abstract_count,
                len(pmid_abstracts),
            )
            if matched_abstract_count < pmid_count:
                logger.warning(
                    "Only %s/%s selected PMIDs have abstracts in the graph; "
                    "%s PMID(s) will be indexed without abstract text.",
                    matched_abstract_count,
                    pmid_count,
                    pmid_count - matched_abstract_count,
                )

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

            set_progress((12, f"📄 Preparing {len(documents)} abstracts..."))

            # Initialize RAG system
            import re as _re

            def _rag_progress(msg):
                m = _re.search(r'batch (\d+)/(\d+)', msg)
                if m:
                    bi, bt = int(m.group(1)), int(m.group(2))
                    v = 15 + int((bi / bt) * 25)
                    set_progress((min(v, 40), f"📄 {msg}"))
                elif "✅" in msg:
                    set_progress((40, msg))
                else:
                    set_progress((18, f"📄 {msg}"))

            rag_system = AbstractRAG(llm_client)
            rag_system.index_abstracts(documents, progress_callback=_rag_progress)
            t_rag = time.time()
            logger.info(f"Abstracts indexed in {t_rag - t_load:.2f}s")

            set_progress((42, "🧬 Initializing node index..."))

            # Initialize Node RAG System with Persistent Cache (New in v1.1.0)
            from netmedex.node_rag import NodeRAG, GraphNode

            # Determine persistent directory based on graph path
            # Example: data/graph.pickle -> data/graph.pickle_chroma
            persist_dir = f"{savepath['graph']}_chroma"

            # Close the existing NodeRAG for this graph BEFORE opening a new
            # PersistentClient on the same directory.  If the old handle is still
            # open, SQLite WAL-mode will block the new connection indefinitely.
            _session_id_for_close = savepath["graph"]
            if _session_id_for_close in _sessions:
                _old_session = _sessions[_session_id_for_close]
                _old_gr = getattr(
                    getattr(_old_session.get("session"), "graph_retriever", None),
                    "node_rag",
                    None,
                )
                if _old_gr is not None:
                    _old_gr.close()
                    logger.info("Closed old NodeRAG before re-opening persistent store.")

            node_rag = NodeRAG(llm_client, persist_directory=persist_dir)

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
                    raw_node_id = n.get("raw_node_id") or cy_id_to_raw_id.get(str(n.get("id", "")))
                    if raw_node_id and str(raw_node_id) in raw_id_to_node:
                        core_node_ids.add(raw_id_to_node[str(raw_node_id)][0])
                        continue
                    name_key = str(n.get("label", n.get("name", ""))).lower().strip()
                    if name_key in label_to_raw_id:
                        core_node_ids.add(label_to_raw_id[name_key])
            if selected_edges:
                for e in selected_edges:
                    for raw_field in ("source_raw_id", "target_raw_id"):
                        raw_node_id = e.get(raw_field)
                        if raw_node_id and str(raw_node_id) in raw_id_to_node:
                            core_node_ids.add(raw_id_to_node[str(raw_node_id)][0])
                    for name_field in ("source_name", "target_name"):
                        name_key = str(e.get(name_field, "")).lower().strip()
                        if name_key in label_to_raw_id:
                            core_node_ids.add(label_to_raw_id[name_key])

            def _node_progress(msg):
                if "✅" in msg or "cache" in msg.lower():
                    set_progress((65, msg))
                else:
                    set_progress((55, f"🧬 {msg}"))

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
                        set_progress((48, f"🧬 Indexing {len(graph_nodes)} nodes..."))
                        node_rag.index_nodes(graph_nodes, progress_callback=_node_progress)
                        logger.info(
                            f"Partial indexing complete: {len(graph_nodes)}/ {total_nodes} nodes indexed."
                        )
                    _node_index_count = len(graph_nodes)
                    _node_index_mode = "partial"
                else:
                    logger.info(
                        f"Small graph detected ({total_nodes} nodes). Building full node list..."
                    )
                    graph_nodes = []
                    for node_id, data in G.nodes(data=True):
                        name = data.get("name", str(node_id))
                        node_type = data.get("type", "Entity")
                        graph_node = GraphNode(
                            node_id=str(node_id), name=name, type=node_type, metadata=data
                        )
                        graph_nodes.append(graph_node)

                    set_progress((48, f"🧬 Indexing {len(graph_nodes)} nodes..."))
                    node_rag.index_nodes(graph_nodes, progress_callback=_node_progress)
                    logger.info(f"Full indexing complete: {len(graph_nodes)} nodes indexed.")
                    _node_index_count = len(graph_nodes)
                    _node_index_mode = "full"
            else:
                logger.info("NodeRAG already indexed. Skipping re-scan.")
                _node_index_count = node_rag.count() if hasattr(node_rag, "count") else len(G.nodes)
                _node_index_mode = "cached"

            t_node = time.time()
            logger.info(f"Node indexing check in {t_node - t_rag:.2f}s")

            set_progress((68, "🌐 Building graph retriever..."))

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

            set_progress((74, "✨ Generating AI summary..."))

            # Register the new session (old NodeRAG was already closed before NodeRAG init above)
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

            prompt_lang = effective_language

            # The [INTERNAL_BOOTSTRAP] sentinel tells send_message() to:
            #   1. Use self.topic (= the real search query) for RAG retrieval, not this prompt text
            #   2. Skip translation passes
            # The 5-layer structure is governed entirely by the system_prompt in ChatSession,
            # so we must NOT duplicate format instructions here (they would conflict).
            topic_display = search_query if search_query else "the selected abstracts"
            bootstrap_prompt = (
                f"[INTERNAL_BOOTSTRAP] Provide a comprehensive integrated analysis of {topic_display} "
                f"based on the selected PubMed abstracts and knowledge graph. "
                f"Respond in {prompt_lang}."
            )

            logger.info(
                f"Generating initial summary (topic='{topic_display}', output: {prompt_lang})..."
            )
            summary_result = session.send_message(
                bootstrap_prompt,
                session_language=effective_language,
                skip_translation=True,  # The translation instruction is embedded in the prompt
                focus_nodes=list(core_node_ids) if core_node_ids else None,
            )
            t_sum = time.time()
            logger.info(f"Initial summary generated in {t_sum - t_node:.2f}s")
            logger.info(f"Total Analyze Selection time: {t_sum - t0:.2f}s")
            set_progress((95, "🎉 Almost done..."))
            bootstrap_user = summary_result.get("user_msg")
            if bootstrap_user is not None:
                if bootstrap_user in session.history:
                    session.history.remove(bootstrap_user)
                if bootstrap_user in session.full_history:
                    session.full_history.remove(bootstrap_user)

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
                cited_in_summary = sorted(set(
                    re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", summary_content)
                ) | set(
                    re.findall(r"\[(\d{7,10})\]", summary_content)
                ))
                summary_component = create_message_component(
                    "assistant",
                    clean_content,
                    cited_in_summary or (summary_msg.sources if summary_msg else None),
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

            _index_summary = (
                f"📊 {matched_abstract_count} abstracts · "
                f"{_node_index_count} nodes ({_node_index_mode})"
            )
            logger.info("Indexing summary: %s", _index_summary)

            # Save the initial chat session state to file
            try:
                import pathlib as _pathlib
                history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
                session.save_to_file(str(history_file))
            except Exception as _e:
                logger.error(f"Failed to save initial chat history: {_e}")

            return (
                True,
                _index_summary,
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
            State("nvidia-api-key-input", "value"),
            State("nvidia-nim-base-url-input", "value"),
            State("nvidia-model-selector", "value"),
            State("groq-api-key-input", "value"),
            State("groq-model-selector", "value"),
            State("groq-custom-model-input", "value"),
            State("anthropic-api-key-input", "value"),
            State("anthropic-model-selector", "value"),
            State("anthropic-custom-model-input", "value"),
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
        nvidia_api_key,
        nvidia_nim_base_url,
        nvidia_model,
        groq_api_key,
        groq_model,
        groq_custom_model,
        anthropic_api_key,
        anthropic_model,
        anthropic_custom_model,
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

        if savepath and savepath["graph"] not in _sessions:
            try:
                import os

                if os.path.exists(savepath["graph"]):
                    llm_client = _initialize_llm_from_callback_state(
                        llm_provider=llm_provider,
                        openai_api_key=openai_api_key,
                        openai_model=openai_model,
                        openai_custom_model=openai_custom_model,
                        google_api_key=google_api_key,
                        google_model=google_model,
                        google_safety_setting=google_safety_setting,
                        llm_base_url=llm_base_url,
                        llm_model=llm_model,
                        openrouter_api_key=openrouter_api_key,
                        openrouter_model=openrouter_model,
                        openrouter_custom_model=openrouter_custom_model,
                        nvidia_api_key=nvidia_api_key,
                        nvidia_nim_base_url=nvidia_nim_base_url,
                        nvidia_model=nvidia_model,
                        groq_api_key=groq_api_key,
                        groq_model=groq_model,
                        groq_custom_model=groq_custom_model,
                        anthropic_api_key=anthropic_api_key,
                        anthropic_model=anthropic_model,
                        anthropic_custom_model=anthropic_custom_model,
                    )
                    if not llm_client.client and not llm_client.anthropic_client:
                        logger.warning(
                            "Rebuilding chat session from graph, but LLM client is not fully initialized. "
                            "Provider: %s", llm_client.provider
                        )
                    _rebuild_chat_session_from_graph(
                        savepath,
                        llm_client,
                        topic=search_query,
                    )
            except Exception as e:
                logger.error(f"Failed to rebuild chat session from graph: {e}")

        if not savepath or savepath["graph"] not in _sessions:
            from webapp.components.chat import create_message_component
            err_msg = create_message_component(
                "assistant",
                "⚠️ Session expired and the chat context could not be rebuilt. Please verify the LLM settings or run a new search.",
            )
            msgs = list(current_messages or []) + [err_msg]
            return msgs, [rename_suggested_question_ids(m, suffix="-modal") for m in msgs] if msgs else [], "", "", "", "", None, False, False, []

        session_data = _sessions[savepath["graph"]]
        session = session_data["session"]

        try:
            from webapp.callbacks.pipeline import detect_query_language
            from webapp.components.chat import create_message_component

            # Response language follows the user's current message.
            # If the script cannot be determined, detect_query_language returns
            # "English" as the default — matching the "fallback to English" rule.
            effective_language = detect_query_language(user_input)

            # Pass focus_nodes=None so find_relevant_nodes() runs fresh on each
            # user question — reusing the initial selection caused every follow-up
            # to receive identical graph context, producing repetitive responses.
            response = session.send_message(
                user_input,
                session_language=effective_language,
                focus_nodes=None,
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

                # Sources = only show PMIDs actually cited/mentioned in the text
                cited_in_response = sorted(set(
                    re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", response_content)
                ) | set(
                    re.findall(r"\[(\d{7,10})\]", response_content)
                ) | set(response.get("sources") or []))

                # Update 2-hop paths from the latest response
                twohop_paths = response.get("twohop_paths", [])
                if twohop_paths and savepath:
                    _sessions[savepath["graph"]]["twohop_paths"] = twohop_paths

                ai_msg = create_message_component(
                    "assistant",
                    clean_content,
                    cited_in_response or assistant_msg_obj.sources,
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

            # Save the updated session history to file
            if savepath:
                try:
                    import pathlib as _pathlib
                    history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
                    session.save_to_file(str(history_file))
                except Exception as _e:
                    logger.error(f"Failed to save chat history: {_e}")

            logger.info(f"send_message SUCCESS for trigger: {trigger_id}")
            return messages, [rename_suggested_question_ids(m, suffix="-modal") for m in messages] if messages else [], "", "", "", "", None, False, False, twohop_paths

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            from webapp.components.chat import create_message_component

            error_msg = create_message_component("assistant", f"❌ Error: {str(e)}")
            messages = list(current_messages) if current_messages else []
            messages.append(error_msg)
            return messages, [rename_suggested_question_ids(m, suffix="-modal") for m in messages] if messages else [], "", "", "", "", None, False, False, []

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
            Output("twohop-highlight-paths", "data", allow_duplicate=True),
        ],
        Input("clear-chat-btn", "n_clicks"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def clear_chat(n_clicks, session_data):
        """Clear chat history, reset session, and remove sub-network highlighting"""
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
            gr = getattr(getattr(session_data.get("session"), "graph_retriever", None), "node_rag", None)
            if gr is not None:
                gr.close()
            session_data["session"].clear()
            session_data["rag"].clear()

        # Delete chat history file from disk
        if savepath:
            import pathlib as _pathlib
            history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
            if history_file.exists():
                try:
                    history_file.unlink()
                except Exception:
                    pass

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
            False,   # Session not active
            "",      # Clear status
            True,    # Disable input
            True,    # Disable send button
            {"display": "none"},  # Hide clear button
            None,
            {"display": "none"},
            [],      # ← Clear sub-network highlight paths (unlocks the graph)
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
        if not n_clicks or not savepath:
            raise dash.exceptions.PreventUpdate

        import json
        import pathlib as _pathlib
        history_file = _pathlib.Path(savepath["graph"]).parent / "chat_history.json"
        
        export_history = []
        if savepath["graph"] in _sessions:
            session_data = _sessions[savepath["graph"]]
            session = session_data.get("session")
            if session:
                export_history = getattr(session, "full_history", None) or session.history
        
        if not export_history and history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                from netmedex.chat import ChatMessage
                export_history = [
                    ChatMessage(
                        role=d["role"],
                        content=d["content"],
                        sources=d.get("sources"),
                        timestamp=d.get("timestamp"),
                        msg_id=d.get("msg_id"),
                        full_content=d.get("full_content"),
                    )
                    for d in data.get("full_history", data.get("history", []))
                ]
            except Exception as e:
                logger.error(f"Failed to read chat history for download: {e}")
                
        if not export_history:
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
            messages_for_title = [m for m in export_history if m.role != "system"]
            for m in messages_for_title[:4]:  # Take first 4 non-system messages
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
            for msg in export_history:
                if msg.role == "user" and msg.content and not any(
                    sp in msg.content for sp in skip_prompts
                ):
                    initial_query = msg.content.strip()[:300]
                    if len(msg.content.strip()) > 300:
                        initial_query += "…"
                    break

        skip_prompt = "Please provide a structured summary of the selected research based on the abstracts and graph structure."
        last_msg_content = None
        for msg in export_history:
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
            # Use full_content for export if available (compressed content is for LLM history only)
            display_text = getattr(msg, "full_content", None) or msg.content
            clean_text = display_text
            if not is_user:
                suggestions, clean_text = parse_suggestions(display_text)

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

            if not is_user:
                # Extract PMIDs from full_content for comprehensive References,
                # matching the same logic used in the live chat Sources display.
                full_text = getattr(msg, "full_content", None) or msg.content
                export_pmids = sorted(set(
                    re.findall(r"(?i)PMID[:\s]\s*(\d{7,10})", full_text)
                ) | set(
                    re.findall(r"\[(\d{7,10})\]", full_text)
                ) | set(msg.sources or []))
                if export_pmids:
                    source_links = [
                        f'<a href="https://pubmed.ncbi.nlm.nih.gov/{html_lib.escape(str(p))}/" target="_blank">[PMID:{html_lib.escape(str(p))}]</a>'
                        for p in export_pmids
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
            modal_content = [rename_suggested_question_ids(c, suffix="-modal") for c in current_content] if current_content else []
            return is_open, modal_content

        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        logger.info(f"Modal toggle triggered by: {button_id}")

        if button_id in ["expand-chat-btn", "close-modal-btn"]:
            modal_content = [rename_suggested_question_ids(c, suffix="-modal") for c in current_content] if current_content else []
            return not is_open, modal_content

        modal_content = [rename_suggested_question_ids(c, suffix="-modal") for c in current_content] if current_content else []
        return is_open, modal_content

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

    # ── Sub-network Freeze Fix ──────────────────────────────────────────────────
    # After a chat response, twohop-highlight-paths holds path data that causes
    # the graph to stay dimmed/highlighted ("frozen"). Tapping any node or edge
    # clears the paths so apply_graph_visual_filters removes the dimming effect.
    @app.callback(
        Output("twohop-highlight-paths", "data", allow_duplicate=True),
        Input("cy", "tapNodeData"),
        Input("cy", "tapEdgeData"),
        State("twohop-highlight-paths", "data"),
        prevent_initial_call=True,
    )
    def clear_twohop_on_graph_tap(tap_node, tap_edge, current_paths):
        """Clear 2-hop path highlighting when user taps any node/edge in the graph.

        This allows users to 'unlock' the sub-network after a chat response has
        applied the 2-hop path highlight without requiring a full chat clear.
        """
        if not current_paths:
            raise dash.exceptions.PreventUpdate
        logger.debug("Graph tap detected — clearing twohop-highlight-paths")
        return []
