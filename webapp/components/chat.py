from __future__ import annotations

"""
Chat interface components for RAG-based conversation

This module contains UI components for the chat panel, including
message display, input box, and source citations.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

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
    # Auto-linkify PMIDs in the text
    import re

    # Pattern to match PMID:123456, PMID 123456, etc.
    # Group 1 is the prefix (PMID:), Group 2 is the ID
    pmid_pattern = r"(?i)(pmid[:\s]?\s*)(\d+)"

    def replace_pmid(match):
        prefix = match.group(1)
        pmid = match.group(2)
        url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/{pmid}"
        return f"[{prefix}{pmid}]({url})"

    # Apply replacement to content
    linked_content = re.sub(pmid_pattern, replace_pmid, content)

    content_children = [
        html.Span(icon, className="message-icon me-2"),
        dcc.Markdown(
            linked_content,
            className="message-text d-inline-block",
            dangerously_allow_html=True,
            link_target="_blank",  # Ensure markdown links open in new tab
        ),
    ]

    if not is_user:
        content_children.append(
            dcc.Clipboard(
                content=content,
                title="Copy",
                style={
                    "display": "inline-block",
                    "float": "right",
                    "marginLeft": "10px",
                    "color": "#6c757d",
                    "cursor": "pointer",
                },
            )
        )

    message_parts = [
        html.Div(
            content_children,
            className=f"{message_class}-content clearfix",  # Add clearfix for float
        )
    ]

    # Add sources for assistant messages
    if not is_user and sources:
        source_badges = [
            html.A(
                dbc.Badge(f"PMID:{pmid}", color="info", className="me-1", pill=True),
                # Link to PubTator 3 to show entity highlighting
                href=f"https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/{pmid}",
                target="_blank",
                style={"textDecoration": "none"},
            )
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
                dbc.Textarea(
                    id="chat-input-box",
                    placeholder="Ask a question about the selected abstracts...",
                    disabled=True,  # Disabled until RAG is initialized
                    rows=3,
                    style={"resize": "none"},
                ),
                dbc.Button(
                    "Send",
                    id="chat-send-btn",
                    color="primary",
                    disabled=True,
                    style={"height": "auto", "alignSelf": "stretch"},  # Match textarea height
                ),
            ],
            className="mb-2",
        ),
        html.Div(
            [
                html.Small(
                    "💡 Tip: Ask about relationships, mechanisms, or key findings",
                    className="text-muted",
                    id="chat-input-hint",
                ),
                dcc.Loading(
                    id="chat-loading",
                    type="dot",
                    children=html.Div(id="chat-processing-status", style={"display": "none"}),
                    style={"marginLeft": "10px"},
                ),
            ],
            className="d-flex justify-content-between align-items-center",
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
                                        html.Span("Abstracts: ", className="text-muted small"),
                                        html.Span(
                                            "0", id="chat-abstract-count", className="fw-bold"
                                        ),
                                    ]
                                ),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Span("Nodes: ", className="text-muted small"),
                                        html.Span("0", id="chat-node-count", className="fw-bold"),
                                    ]
                                ),
                            ],
                            width=4,
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Span("Edges: ", className="text-muted small"),
                                        html.Span("0", id="chat-edge-count", className="fw-bold"),
                                    ]
                                ),
                            ],
                            width=4,
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
        dbc.Button(
            [html.I(className="bi bi-arrows-angle-expand me-2"), "Expand Chat"],
            id="expand-chat-btn",
            color="primary",
            outline=True,
            size="sm",
            className="w-100 mt-1",
        ),
        html.Div(id="chat-status", className="mt-2 small"),
    ],
    className="param",
)

# Chat Modal (for expanded view)
chat_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Chat History"), close_button=True),
        dbc.ModalBody(id="modal-chat-content", style={"minHeight": "400px"}),
        dbc.ModalFooter(
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Textarea(
                            id="modal-chat-input",
                            placeholder="Ask a question...",
                            rows=2,
                            style={"resize": "none"},
                        ),
                        className="flex-grow-1",
                    ),
                    dbc.Col(
                        dbc.Button("Send", id="modal-chat-send-btn", color="primary"),
                        width="auto",
                    ),
                    dbc.Col(
                        dcc.Loading(
                            id="modal-chat-loading",
                            type="dot",
                            children=html.Div(
                                id="modal-chat-processing-status", style={"display": "none"}
                            ),
                        ),
                        width="auto",
                    ),
                    dbc.Col(
                        dbc.Button(
                            "Close",
                            id="close-modal-btn",
                            color="secondary",
                            outline=True,
                        ),
                        width="auto",
                    ),
                ],
                className="w-100 align-items-center g-2",
            )
        ),
    ],
    id="chat-modal",
    size="xl",
    is_open=False,
    scrollable=True,
)

# Main chat panel
chat_panel = html.Div(
    [
        selection_info,
        html.Hr(),
        chat_messages,
        html.Hr(),
        chat_input,
        chat_modal,
        # Hidden storage for chat state
        dcc.Store(id="chat-session-active", data=False),
        dcc.Store(id="chat-history-store", data=[]),
        dcc.Store(id="selected-edges-data", data=None),
    ],
    id="chat-panel-container",
    style=display.none,
)
