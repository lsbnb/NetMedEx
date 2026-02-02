from __future__ import annotations

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
from dash import Input, Output, State, no_update

logger = logging.getLogger(__name__)

# Local stores for chat state
# These are used to avoid global variables in a multi-user environment
# However, for simplicity in this prototype, we'll keep the session-based imports
# and use dcc.Stores for persistent state.
chat_session = None
rag_system = None


def callbacks(app):
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

        node_count = len(selected_nodes) if selected_nodes else 0
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
        ],
        Input("analyze-selection-btn", "n_clicks"),
        [
            State("cy", "selectedEdgeData"),
            State("current-session-path", "data"),  # Used to get the graph file path if needed
        ],
        prevent_initial_call=True,
    )
    def initialize_chat(n_clicks, selected_edges, savepath):
        """
        Initialize RAG system and chat session with selected abstracts.
        """
        global chat_session, rag_system

        if not n_clicks or not selected_edges:
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
                )

            # Initialize RAG system
            rag_system = AbstractRAG(llm_client)
            indexed_count = rag_system.index_abstracts(documents)

            # Initialize Graph Retriever
            from netmedex.graph_rag import GraphRetriever

            graph_retriever = GraphRetriever(G)
            logger.info("GraphRetriever initialized with full graph")

            # Initialize chat session with Hybrid RAG
            chat_session = ChatSession(rag_system, llm_client, graph_retriever=graph_retriever)

            # Create welcome message
            welcome_text = (
                f"✅ Hybrid RAG Ready! I've indexed {indexed_count} abstracts and loaded the knowledge graph. "
                "I can analyze both text details and structural paths. Ask me anything!"
            )

            from webapp.components.chat import create_message_component

            welcome_msg = create_message_component("assistant", welcome_text)

            return (
                True,
                f"✅ Indexed {indexed_count} abstracts + Graph",
                False,  # Enable input
                False,  # Enable send button
                {"display": "block"},  # Show clear button
                [welcome_msg],
                "chat",  # Set toggle to chat
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
            )

    @app.callback(
        [
            Output("chat-messages", "children", allow_duplicate=True),
            Output("modal-chat-content", "children", allow_duplicate=True),
            Output("chat-input-box", "value"),
            Output("modal-chat-input", "value"),
            Output("chat-processing-status", "children"),
            Output("modal-chat-processing-status", "children"),
        ],
        [
            Input("chat-send-btn", "n_clicks"),
            Input("modal-chat-send-btn", "n_clicks"),
        ],
        [
            State("chat-input-box", "value"),
            State("modal-chat-input", "value"),
            State("chat-messages", "children"),
        ],
        prevent_initial_call=True,
    )
    def send_message(n1, n2, main_input, modal_input, current_messages):
        """
        Process user message and get AI response.
        """
        global chat_session

        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        button_id = ctx.triggered[0]["prop_id"].split(".")[0]

        # Determine user input source
        user_input = main_input if button_id == "chat-send-btn" else modal_input

        if not user_input or not user_input.strip():
            raise dash.exceptions.PreventUpdate

        if not chat_session:
            # Return same state, clear inputs (though likely already clear or invalid)
            return current_messages, current_messages, "", "", "", ""

        try:
            from webapp.components.chat import create_message_component

            # Add user message
            user_msg = create_message_component("user", user_input)
            messages = list(current_messages) if current_messages else []
            messages.append(user_msg)

            # Get AI response
            response = chat_session.send_message(user_input)

            if response["success"]:
                # Add assistant message with sources
                assistant_msg = create_message_component(
                    "assistant", response["message"], response.get("sources", [])
                )
                messages.append(assistant_msg)
            else:
                # Add error message
                error_msg = create_message_component(
                    "assistant", f"❌ {response.get('message', 'Error processing request')}"
                )
                messages.append(error_msg)

            # Update both views and clear both inputs
            return messages, messages, "", "", "", ""

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            from webapp.components.chat import create_message_component

            error_msg = create_message_component("assistant", f"❌ Error: {str(e)}")
            messages = list(current_messages) if current_messages else []
            messages.append(error_msg)
            return messages, messages, "", "", "", ""

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
