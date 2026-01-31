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

from dash import Input, Output, State, callback, no_update
from dash.exceptions import PreventUpdate

logger = logging.getLogger(__name__)

# Global chat session (will be initialized when user clicks "Analyze Selection")
chat_session = None
rag_system = None


@callback(
    [
        Output("chat-edge-count", "children"),
        Output("chat-abstract-count", "children"),
        Output("analyze-selection-btn", "disabled"),
    ],
    [
        Input("cytoscape-graph", "selectedNodeData"),
        Input("cytoscape-graph", "selectedEdgeData"),
    ],
    State("graph-data", "data"),
)
def update_selection_count(selected_nodes, selected_edges, graph_data):
    """
    Update selection count based on graph selection.

    Args:
        selected_nodes: List of selected node data
        selected_edges: List of selected edge data
        graph_data: Full graph data with metadata

    Returns:
        Tuple of (edge_count, abstract_count, button_disabled)
    """
    if not selected_edges or len(selected_edges) == 0:
        return "0", "0", True

    edge_count = len(selected_edges)

    # Extract unique PMIDs from selected edges
    pmids = set()
    for edge in selected_edges:
        if "pmids" in edge.get("data", {}):
            edge_pmids = edge["data"]["pmids"]
            if isinstance(edge_pmids, list):
                pmids.update(edge_pmids)
            elif isinstance(edge_pmids, str):
                pmids.add(edge_pmids)

    abstract_count = len(pmids)

    # Enable button if we have at least one abstract
    button_disabled = abstract_count == 0

    return str(edge_count), str(abstract_count), button_disabled


@callback(
    [
        Output("chat-session-active", "data"),
        Output("chat-status", "children"),
        Output("chat-input-box", "disabled"),
        Output("chat-send-btn", "disabled"),
        Output("clear-chat-btn", "style"),
        Output("chat-messages", "children"),
    ],
    Input("analyze-selection-btn", "n_clicks"),
    [
        State("cytoscape-graph", "selectedEdgeData"),
        State("graph-data", "data"),
        State("llm-client-store", "data"),
    ],
    prevent_initial_call=True,
)
def initialize_chat(n_clicks, selected_edges, graph_data, llm_config):
    """
    Initialize RAG system and chat session with selected abstracts.

    Args:
        n_clicks: Button click count
        selected_edges: Selected edge data
        graph_data: Full graph data
        llm_config: LLM client configuration

    Returns:
        Tuple of (session_active, status_message, input_disabled, send_disabled, clear_style, messages)
    """
    global chat_session, rag_system

    if not n_clicks or not selected_edges:
        raise PreventUpdate

    try:
        # Import here to avoid circular dependencies
        from netmedex.chat import ChatSession
        from netmedex.rag import AbstractDocument, AbstractRAG
        from webapp.llm import LLMClient

        # Initialize LLM client
        llm_client = LLMClient()
        if not llm_client.client:
            return (
                False,
                "❌ Error: LLM not configured. Please set your API key in Advanced Settings.",
                True,
                True,
                {"display": "none"},
                no_update,
            )

        # Extract PMIDs and build abstract documents
        pmid_data = {}
        for edge in selected_edges:
            edge_pmids = edge.get("data", {}).get("pmids", [])
            if isinstance(edge_pmids, str):
                edge_pmids = [edge_pmids]

            for pmid in edge_pmids:
                if pmid not in pmid_data:
                    pmid_data[pmid] = {"pmid": pmid, "edges": []}
                pmid_data[pmid]["edges"].append(edge)

        # Get abstracts from graph metadata
        pmid_abstracts = graph_data.get("pmid_abstract", {}) if graph_data else {}
        pmid_titles = graph_data.get("pmid_title", {}) if graph_data else {}

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
            )

        # Initialize RAG system
        rag_system = AbstractRAG(llm_client)
        indexed_count = rag_system.index_abstracts(documents)

        # Initialize chat session
        chat_session = ChatSession(rag_system, llm_client)

        # Create welcome message
        welcome_message = [
            {
                "role": "assistant",
                "content": f"✅ Ready! I've indexed {indexed_count} abstracts. Ask me anything about these papers!",
                "sources": None,
            }
        ]

        # Create message components
        from webapp.components.chat import create_message_component

        message_components = [
            create_message_component(msg["role"], msg["content"], msg.get("sources"))
            for msg in welcome_message
        ]

        return (
            True,
            f"✅ Chat initiated with {indexed_count} abstracts",
            False,  # Enable input
            False,  # Enable send button
            {"display": "block"},  # Show clear button
            message_components,
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
        )


@callback(
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("chat-input-box", "value"),
    ],
    Input("chat-send-btn", "n_clicks"),
    [State("chat-input-box", "value"), State("chat-messages", "children")],
    prevent_initial_call=True,
)
def send_message(n_clicks, user_input, current_messages):
    """
    Process user message and get AI response.

    Args:
        n_clicks: Send button clicks
        user_input: User's message
        current_messages: Current message list

    Returns:
        Tuple of (updated_messages, cleared_input)
    """
    global chat_session

    if not n_clicks or not user_input or not user_input.strip():
        raise PreventUpdate

    if not chat_session:
        return no_update, no_update

    try:
        from webapp.components.chat import create_message_component

        # Add user message
        user_msg = create_message_component("user", user_input, None)
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
                "assistant", f"❌ {response.get('message', 'Error processing request')}", None
            )
            messages.append(error_msg)

        return messages, ""  # Clear input box

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        error_msg = create_message_component("assistant", f"❌ Error: {str(e)}", None)
        messages = list(current_messages) if current_messages else []
        messages.append(error_msg)
        return messages, ""


@callback(
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
        raise PreventUpdate

    # Clear session
    if chat_session:
        chat_session.clear()
    if rag_system:
        rag_system.clear()

    chat_session = None
    rag_system = None

    # Return to welcome state
    from webapp.components.chat import create_message_component

    welcome = [
        {
            "role": "assistant",
            "content": "Chat cleared. Select edges and click 'Analyze Selection' to start a new conversation.",
        }
    ]

    messages = [create_message_component(msg["role"], msg["content"], None) for msg in welcome]

    return (
        messages,
        False,  # Session not active
        "",  # Clear status
        True,  # Disable input
        True,  # Disable send
        {"display": "none"},  # Hide clear button
    )


# Allow Enter key to send message
@callback(
    Output("chat-send-btn", "n_clicks", allow_duplicate=True),
    Input("chat-input-box", "n_submit"),
    State("chat-send-btn", "n_clicks"),
    prevent_initial_call=True,
)
def submit_on_enter(n_submit, current_clicks):
    """Trigger send button when Enter is pressed"""
    if n_submit:
        return (current_clicks or 0) + 1
    raise PreventUpdate
