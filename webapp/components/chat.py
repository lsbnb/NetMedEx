from __future__ import annotations

"""
Chat interface components for RAG-based conversation

This module contains UI components for the chat panel, including
message display, input box, and source citations.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title
from webapp.utils import display


def create_message_component(role: str, content: str, sources: list[str] | None = None):
    """
    Create a chat message component.

    Args:
        role: "user" or "assistant"
        content: Message text
        sources: List of PMIDs (for assistant messages)

    Returns:
        Dash component for the message
    """
    is_user = role == "user"

    message_class = "chat-message-user" if is_user else "chat-message-assistant"
    icon = "👤" if is_user else "🤖"

    # Build message content
    message_parts = [
        html.Div(
            [
                html.Span(icon, className="message-icon me-2"),
                dcc.Markdown(
                    content, className="message-text d-inline-block", dangerously_allow_html=True
                ),
            ],
            className=f"{message_class}-content",
        )
    ]

    # Add sources for assistant messages
    if not is_user and sources:
        source_badges = [
            dbc.Badge(f"PMID:{pmid}", color="info", className="me-1", pill=True)
            for pmid in sources
        ]
        message_parts.append(
            html.Div(
                [html.Small("📎 Sources: ", className="text-muted")] + source_badges,
                className="message-sources mt-2",
            )
        )

    return html.Div(message_parts, className=f"{message_class} mb-3")


# Chat messages container
chat_messages = html.Div(
    id="chat-messages",
    className="chat-messages-container",
    style={
        "height": "400px",
        "overflowY": "auto",
        "border": "1px solid #ddd",
        "borderRadius": "8px",
        "padding": "15px",
        "backgroundColor": "#f8f9fa",
    },
    children=[
        html.Div(
            [
                html.Div(
                    "💬 Welcome to AI Chat!",
                    className="text-primary fw-bold text-center mb-2",
                ),
                html.Div(
                    "Select edges in the graph, then click 'Analyze Selection' to start chatting.",
                    className="text-muted text-center small",
                ),
            ],
            id="chat-welcome-message",
        )
    ],
)

# Chat input area
chat_input = html.Div(
    [
        dbc.InputGroup(
            [
                dbc.Input(
                    id="chat-input-box",
                    placeholder="Ask a question about the selected abstracts...",
                    type="text",
                    disabled=True,  # Disabled until RAG is initialized
                ),
                dbc.Button(
                    "Send",
                    id="chat-send-btn",
                    color="primary",
                    disabled=True,
                ),
            ],
            className="mb-2",
        ),
        html.Small(
            "💡 Tip: Ask about relationships, mechanisms, or key findings",
            className="text-muted",
            id="chat-input-hint",
        ),
    ],
    className="chat-input-area",
)

# Selection info panel
selection_info = html.Div(
    [
        html.Div(
            [
                html.H6("📊 Selection Summary", className="mb-3"),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Span("Edges: ", className="text-muted small"),
                                        html.Span("0", id="chat-edge-count", className="fw-bold"),
                                    ]
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Span("Abstracts: ", className="text-muted small"),
                                        html.Span(
                                            "0", id="chat-abstract-count", className="fw-bold"
                                        ),
                                    ]
                                ),
                            ],
                            width=6,
                        ),
                    ]
                ),
            ],
            id="chat-selection-summary",
            className="mb-3",
        ),
        dbc.Button(
            [html.I(className="bi bi-chat-dots me-2"), "Analyze Selection"],
            id="analyze-selection-btn",
            color="success",
            className="w-100 mb-2",
            disabled=True,
        ),
        dbc.Button(
            [html.I(className="bi bi-trash me-2"), "Clear Chat"],
            id="clear-chat-btn",
            color="secondary",
            outline=True,
            size="sm",
            className="w-100",
            style=display.none,
        ),
        html.Div(id="chat-status", className="mt-2 small"),
    ],
    className="param",
)

# Main chat panel
chat_panel = html.Div(
    [
        selection_info,
        html.Hr(),
        chat_messages,
        html.Hr(),
        chat_input,
        # Hidden storage for chat state
        dcc.Store(id="chat-session-active", data=False),
        dcc.Store(id="chat-history-store", data=[]),
        dcc.Store(id="selected-edges-data", data=None),
    ],
    id="chat-panel-container",
    style=display.none,
)
