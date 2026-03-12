from __future__ import annotations
import re

"""
Chat callbacks for RAG-based conversation system

This module handles:
- Edge selection from graph
- RAG initialization with selected abstracts
- Chat message processing
- UI state management
"""

import logging

import dash
from dash import ALL, Input, Output, State, dcc, html, no_update

logger = logging.getLogger(__name__)

# Local stores for chat state
# These are used to avoid global variables in a multi-user environment
# However, for simplicity in this prototype, we'll keep the session-based imports
# and use dcc.Stores for persistent state.
chat_session = None
rag_system = None

COMMUNITY_NODE_PATTERN = re.compile(r"^c\d+$")


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
                        "props": {"className": "loading-dots"},
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

    @app.callback(
        [
            Output("chat-node-count", "children"),
            Output("chat-edge-count", "children"),
            Output("chat-abstract-count", "children"),
            Output("analyze-selection-btn", "disabled"),
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

        # Extract unique PMIDs from selected edges
        pmids = set()
        if selected_edges:
            for edge in selected_edges:
                if "pmids" in edge:
                    edge_pmids = edge["pmids"]
                    if isinstance(edge_pmids, list):
                        pmids.update(edge_pmids)
                    elif isinstance(edge_pmids, str):
                        pmids.add(edge_pmids)

        # Also extract PMIDs from selected REAL nodes
        # (articles that mention the entity but might not have edges in the current selection)
        for node in real_selected_nodes:
            if "pmids" in node:
                node_pmids = node["pmids"]
                if isinstance(node_pmids, list):
                    pmids.update(node_pmids)
                elif isinstance(node_pmids, str):
                    pmids.add(node_pmids)

        abstract_count = len(pmids)

        # Enable button if we have at least one abstract
        button_disabled = abstract_count == 0

        return str(node_count), str(edge_count), str(abstract_count), button_disabled

    @app.callback(
        [
            Output("chat-session-active", "data"),
            Output("chat-status", "children"),
            Output("chat-input-box", "disabled"),
            Output("chat-send-btn", "disabled"),
            Output("clear-chat-btn", "style"),
            Output("chat-messages", "children"),
            Output(
                "sidebar-panel-toggle", "active_tab", allow_duplicate=True
            ),  # Switch to Chat panel automatically
            Output("analyze-selection-btn", "children", allow_duplicate=True),
            Output("suggested-question-store", "data", allow_duplicate=True),
        ],
        Input("analyze-selection-btn", "n_clicks"),
        [
            State("cy", "selectedNodeData"),
            State("cy", "selectedEdgeData"),
            State("current-session-path", "data"),  # Used to get the graph file path if needed
            State("session-language", "data"),
        ],
        prevent_initial_call=True,
    )
    def initialize_chat(n_clicks, selected_nodes, selected_edges, savepath, session_language):
        """
        Initialize RAG system and chat session with selected abstracts.
        """
        global chat_session, rag_system

        # Reset button content
        reset_btn = [html.I(className="bi bi-chat-dots me-2"), "Analyze Selection"]

        if not n_clicks or (not selected_edges and not selected_nodes):
            raise dash.exceptions.PreventUpdate

        try:
            import pickle
            from netmedex.chat import ChatSession
            from netmedex.rag import AbstractDocument, AbstractRAG
            from webapp.llm import llm_client

            if not llm_client.client:
                return (
                    False,
                    "❌ Error: LLM not configured. Please set your API key in Advanced Settings.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    no_update,
                    reset_btn,
                    no_update,
                )

            # Load the graph to get abstracts
            if not savepath or "graph" not in savepath:
                return (
                    False,
                    "❌ Error: Graph session data not found.",
                    True,
                    True,
                    {"display": "none"},
                    no_update,
                    no_update,
                    reset_btn,
                    no_update,
                )

            with open(savepath["graph"], "rb") as f:
                G = pickle.load(f)

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

            # Get abstracts from graph metadata
            pmid_abstracts = G.graph.get("pmid_abstract", {})
            pmid_titles = G.graph.get("pmid_title", {})

            logger.info(f"PMIDs in selected edges: {list(pmid_data.keys())}")
            logger.info(f"Total abstracts in graph: {len(pmid_abstracts)}")
            logger.info(
                f"Sample abstract key: {next(iter(pmid_abstracts.keys())) if pmid_abstracts else 'None'}"
            )

            # Build AbstractDocument objects
            documents = []
            for pmid, data in pmid_data.items():
                title = pmid_titles.get(pmid, f"PMID {pmid}")
                abstract = pmid_abstracts.get(pmid, "Abstract not available.")

                doc = AbstractDocument(
                    pmid=pmid, title=title, abstract=abstract, entities=[], edges=data["edges"]
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
                    no_update,
                    reset_btn,
                    no_update,
                )

            # Initialize RAG system
            rag_system = AbstractRAG(llm_client)
            indexed_count = rag_system.index_abstracts(documents)

            # Initialize Node RAG System (New in v0.8)
            from netmedex.node_rag import NodeRAG, GraphNode

            node_rag = NodeRAG(llm_client)

            # Index all nodes in the current graph
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
            logger.info(f"Indexed {len(graph_nodes)} nodes for semantic search")

            # Initialize Graph Retriever with NodeRAG
            from netmedex.graph_rag import GraphRetriever

            graph_retriever = GraphRetriever(G, node_rag=node_rag)
            logger.info("GraphRetriever initialized with full graph")

            # Initialize chat session with Hybrid RAG
            chat_session = ChatSession(rag_system, llm_client, graph_retriever=graph_retriever)

            # Create welcome message
            welcome_text = (
                f"✅ Hybrid RAG Ready! I've indexed {indexed_count} abstracts and loaded the knowledge graph. "
                "I can analyze both text details and structural paths."
            )

            from webapp.components.chat import create_message_component

            welcome_msg = create_message_component("assistant", welcome_text, msg_id="welcome-msg")
            messages = [welcome_msg]

            # Auto-generate summary
            try:
                logger.info("Auto-generating summary for selection...")
                summary_prompt = (
                    "Please provide a structured summary of the selected research based on the abstracts and graph structure. "
                    "You MUST follow the standard output structure: \n"
                    "1. **Evidence-Based Answer**: Key findings directly from the papers.\n"
                    "2. **Hypotheses / Speculative Inference**: Potential mechanisms or implications suggested by the patterns.\n"
                    "3. **Suggested Questions:**: 3 brief follow-up questions.\n"
                    f"All content must be in {session_language or 'English'}. Translate the section headers accordingly."
                )
                response = chat_session.send_message(summary_prompt)

                if response["success"]:
                    # The last message in history is the summary
                    summary_obj = chat_session.history[-1]
                    summary_msg = create_message_component(
                        "assistant",
                        f"📊 **Analysis of Selection:**\n\n{response['message']}",
                        response.get("sources", []),
                        msg_id=summary_obj.msg_id,
                    )
                    messages.append(summary_msg)
            except Exception as e:
                logger.error(f"Error auto-generating summary: {e}")
                # Fallback if summary fails, just show welcome
                pass

            return (
                True,
                f"✅ Indexed {indexed_count} abstracts + Graph",
                False,  # Enable input
                False,  # Enable send button
                {"display": "block"},  # Show clear button
                messages,
                "chat",  # Set toggle to chat
                reset_btn,
                None,  # ⚠️ FIX: Clear suggested-question-store on re-initialization
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
                no_update,
                reset_btn,
                no_update,
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
        session_language,
        is_disabled,
    ):
        """
        Process user message and get AI response.
        """
        global chat_session

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

        if not chat_session:
            # Return same state, clear inputs and store, but unlock buttons
            return current_messages, current_messages, "", "", "", "", None, False, False

        try:
            from webapp.components.chat import create_message_component
            from webapp.callbacks.pipeline import detect_query_language

            # Dynamically detect language of the new message
            msg_lang = detect_query_language(user_input)
            # If a specific non-English language is detected, use it. Otherwise, fallback to the session language
            # unless the input is clearly long enough to be an English question.
            effective_language = msg_lang if msg_lang != "English" else session_language

            # Get AI response
            response = chat_session.send_message(user_input, session_language=effective_language)

            if response["success"]:
                # Use returned message objects for stability instead of relying on history indexing
                user_msg_obj = response.get("user_msg")
                assistant_msg_obj = response.get("assistant_msg")

                # Fallback if objects are missing
                if not user_msg_obj:
                    user_msg_obj = chat_session.history[-2]
                if not assistant_msg_obj:
                    assistant_msg_obj = chat_session.history[-1]

                user_msg = create_message_component(
                    "user", user_msg_obj.content, msg_id=user_msg_obj.msg_id
                )
                ai_msg = create_message_component(
                    "assistant",
                    assistant_msg_obj.content,
                    assistant_msg_obj.sources,
                    msg_id=assistant_msg_obj.msg_id,
                )
            else:
                # Handle error case
                assistant_msg_obj = chat_session.history[-1]
                user_msg = create_message_component("user", user_input)
                ai_msg = create_message_component(
                    "assistant",
                    f"❌ {response.get('message', 'Error processing request')}",
                    msg_id=assistant_msg_obj.msg_id if assistant_msg_obj else None,
                )

            messages = list(current_messages) if current_messages else []
            messages.append(user_msg)
            messages.append(ai_msg)

            # Update both views and clear both inputs + the suggestion store + unlock buttons
            return messages, messages, "", "", "", "", None, False, False

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            from webapp.components.chat import create_message_component

            error_msg = create_message_component("assistant", f"❌ Error: {str(e)}")
            messages = list(current_messages) if current_messages else []
            messages.append(error_msg)
            return messages, messages, "", "", "", "", None, False, False

    @app.callback(
        [
            Output("chat-messages", "children", allow_duplicate=True),
            Output("chat-session-active", "data", allow_duplicate=True),
            Output("chat-status", "children", allow_duplicate=True),
            Output("chat-input-box", "disabled", allow_duplicate=True),
            Output("chat-send-btn", "disabled", allow_duplicate=True),
            Output("clear-chat-btn", "style", allow_duplicate=True),
        ],
        Input("clear-chat-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_chat(n_clicks):
        """Clear chat history and reset session"""
        global chat_session, rag_system

        if not n_clicks:
            raise dash.exceptions.PreventUpdate

        # Clear session
        if chat_session:
            chat_session.clear()
        if rag_system:
            rag_system.clear()

        chat_session = None
        rag_system = None

        # Return to welcome state
        from webapp.components.chat import create_message_component

        welcome_text = (
            "Chat cleared. Select edges and click 'Analyze Selection' to start a new conversation."
        )
        messages = [create_message_component("assistant", welcome_text)]

        return (
            messages,
            False,  # Session not active
            "",  # Clear status
            True,  # Disable input
            True,  # Disable send
            {"display": "none"},  # Hide clear button
        )

    @app.callback(
        Output("download-chat-history", "data"),
        Input("download-chat-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def download_chat_history(n_clicks):
        global chat_session
        if not n_clicks or not chat_session or not chat_session.history:
            raise dash.exceptions.PreventUpdate

        import datetime

        def hyperlink_pmids(text):
            return re.sub(
                r"PMID:?\s*(\d+)",
                r'<a href="https://pubmed.ncbi.nlm.nih.gov/\1/" target="_blank">PMID: \1</a>',
                text,
                flags=re.IGNORECASE,
            )

        def md_to_html(text):
            # Better markdown to HTML conversion for bubbles
            # 1. Bolding
            text = text.replace("**", "<strong>").replace("**", "</strong>")
            # 2. Section Headers (Clearer hierarchy)
            headers = [
                ("Evidence-Based Answer", "證據基礎的回答"),
                ("Hypotheses / Speculative Inference", "假設 / 推理性推論"),
                ("Suggested Questions", "建議的問題"),
            ]
            for eng, chi in headers:
                pattern = f"(?i)^({re.escape(eng)}|{re.escape(chi)})[:：]?"
                replacement = (
                    f"<div style='font-weight:700; color:#007bff; margin-top:12px; "
                    f"border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:3px; "
                    f"margin-bottom:8px; font-size:16px;'>\\1</div>"
                )
                text = re.sub(pattern, replacement, text, flags=re.MULTILINE)

            # 3. Newlines to breaks
            text = text.replace("\n", "<br>")
            # 4. Bullet points
            text = re.sub(r"^-\s+(.+)$", r"<li>\1</li>", text, flags=re.MULTILINE)
            text = text.replace("</li><br><li>", "</li><li>")
            if "<li>" in text:
                text = re.sub(
                    r"(<li>.*</li>)",
                    r"<ul style='margin:8px 0; padding-left:20px;'>\1</ul>",
                    text,
                    flags=re.DOTALL,
                )

            return hyperlink_pmids(text)

        html_content = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<title>NetMedEx Chat History</title>",
            "<style>",
            "body { background-color: #f0f2f5; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 40px 20px; color: #1c1e21; }",
            ".chat-container { max-width: 850px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); overflow: hidden; display: flex; flex-direction: column; }",
            ".header { background: #ffffff; border-bottom: 2px solid #f0f2f5; padding: 25px 35px; }",
            ".header h1 { margin: 0; font-size: 22px; color: #007bff; font-weight: 700; }",
            ".timestamp { font-size: 13px; color: #8d949e; margin-top: 6px; }",
            ".chat-box { padding: 35px; display: flex; flex-direction: column; gap: 28px; }",
            ".message-row { display: flex; width: 100%; }",
            ".user-row { justify-content: flex-end; }",
            ".assistant-row { justify-content: flex-start; }",
            ".bubble { max-width: 85%; padding: 14px 20px; border-radius: 20px; position: relative; font-size: 15px; line-height: 1.6; }",
            ".user-bubble { background-color: #0084ff; color: white; border-bottom-right-radius: 4px; box-shadow: 0 2px 4px rgba(0,132,255,0.2); }",
            ".assistant-bubble { background-color: #f0f2f5; color: #050505; border-bottom-left-radius: 4px; border: 1px solid #e4e6eb; }",
            ".role-label { font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 6px; opacity: 0.8; letter-spacing: 0.8px; }",
            ".user-row .role-label { text-align: right; margin-right: 8px; color: #0084ff; }",
            ".assistant-row .role-label { text-align: left; margin-left: 8px; color: #65676b; }",
            ".sources-box { margin-top: 15px; padding-top: 10px; border-top: 1px dotted #ccc; font-size: 12px; color: #65676b; }",
            "a { color: #0084ff; text-decoration: none; font-weight: 500; }",
            "a:hover { text-decoration: underline; }",
            ".user-bubble a { color: #fff; text-decoration: underline; }",
            "ul { margin: 10px 0; padding-left: 25px; }",
            "li { margin-bottom: 6px; }",
            "strong { font-weight: 600; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='chat-container'>",
            "<div class='header'>",
            "<h1>NetMedEx Professional Chat Transcript</h1>",
            f"<div class='timestamp'>Generated on {datetime.datetime.now().strftime('%B %d, %Y - %H:%M:%S')}</div>",
            "</div>",
            "<div class='chat-box'>",
        ]

        for msg in chat_session.history:
            if msg.role == "system":
                continue

            is_user = msg.role == "user"
            row_class = "user-row" if is_user else "assistant-row"
            bubble_class = "user-bubble" if is_user else "assistant-bubble"
            role_text = "User" if is_user else "NetMedEx Assistant"

            content_html = md_to_html(msg.content)

            html_content.append(f"<div class='message-row {row_class}'>")
            html_content.append("<div>")
            html_content.append(f"<div class='role-label'>{role_text}</div>")
            html_content.append(f"<div class='bubble {bubble_class}'>")
            html_content.append(f"<div class='content'>{content_html}</div>")

            if hasattr(msg, "sources") and msg.sources:
                source_links = [
                    f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p}/" target="_blank">PMID:{p}</a>'
                    for p in msg.sources
                ]
                html_content.append(
                    f"<div class='sources-box'><strong>References:</strong> {', '.join(source_links)}</div>"
                )

            html_content.append("</div></div></div>")

        html_content.append("</div></div></body></html>")

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

    # Callback to handle suggested question clicks via Store to keep inputs blank
    @app.callback(
        [
            Output("suggested-question-store", "data"),
        ],
        [Input({"type": "suggested-question", "index": ALL}, "n_clicks")],
        [
            State({"type": "suggested-question", "index": ALL}, "children"),
        ],
        prevent_initial_call=True,
    )
    def handle_suggested_question(n_clicks_list, question_texts):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n_clicks_list):
            raise dash.exceptions.PreventUpdate

        clicked_idx = -1
        for i, n in enumerate(n_clicks_list):
            # Check for the specific index that was clicked
            if ctx.triggered[0]["prop_id"].startswith(f'{{"index":"{i}"') or n:
                # More reliable to use triggered prop_id if possible, but n_clicks works
                pass

        # Simpler: find the one with the highest clicks or just the first non-zero
        # since only one is clicked at a time
        trigger_info = ctx.triggered[0]
        import json

        try:
            prop_id = trigger_info["prop_id"]
            # Format is {"index":"...","type":"suggested-question"}.n_clicks
            json_str = prop_id.split(".n_clicks")[0]
            triggered_index = json.loads(json_str)["index"]

            # Find the match in question_texts
            # Note: question_texts order should match n_clicks_list order
            # but we need the correct text. Let's find it by index.
            # dash.callback_context.inputs_list[0] has the IDs
            inputs = ctx.inputs_list[0]
            for i, input_item in enumerate(inputs):
                if input_item["id"]["index"] == triggered_index:
                    return [question_texts[i]]
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

    # Clientside callback to auto-scroll chat containers to bottom when messages are added
    app.clientside_callback(
        """
        function(children) {
            if (!children) return window.dash_clientside.no_update;
            setTimeout(function() {
                var chatContainer = document.getElementById('chat-messages');
                if (chatContainer) {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 100);
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
                var modalContainer = document.getElementById('modal-chat-content');
                if (modalContainer) {
                    modalContainer.scrollTop = modalContainer.scrollHeight;
                }
            }, 100);
            return window.dash_clientside.no_update;
        }
        """,
        Output("modal-chat-content", "style"),  # dummy output
        Input("modal-chat-content", "children"),
        prevent_initial_call=True,
    )
