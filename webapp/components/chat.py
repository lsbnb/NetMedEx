from __future__ import annotations

"""
Chat interface components for RAG-based conversation

This module contains UI components for the chat panel, including
message display, input box, and source citations.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.utils import display


def create_message_component(
    role: str,
    content: str,
    sources: list[str] | None = None,
    msg_id: str | None = None,
    suggestions: list[str] | None = None,
):
    """
    Create a chat message component.
    """
    is_user = role == "user"
    base_message_class = "chat-message-user" if is_user else "chat-message-assistant"
    wrapper_class = (
        f"{base_message_class} chat-message-user-anchor mb-3"
        if is_user
        else f"{base_message_class} mb-3"
    )

    import re
    import uuid

    # Aggressive Regex for PMID link conversion
    # Matches: PMID: 123456, PMID 123456, PMID123456, [123456], (123456), or bare 7-10 digit numbers
    # It also handles (and removes) redundant parenthetical URLs often appended by LLMs.
    pmid_pattern = r"(?i)\[?\(?(pmid[:\s]?\s*)?(\d{7,10})\)?\]?(?:\s*\((https?://\S+)\))?"

    def replace_pmid(match):
        pmid = match.group(2)
        url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/{pmid}"
        # Use native Markdown link syntax — raw HTML <a> tags are stripped by react-markdown's sanitizer.
        # Escaped brackets \[ \] in Markdown link text render as literal [ ] characters.
        return f" [\\[{pmid}\\]]({url}) "

    def normalize_mermaid_blocks(text: str) -> str:
        """Wrap plain Mermaid graph syntax into fenced ```mermaid blocks."""
        if not text or "```mermaid" in text:
            return text
        # Common Mermaid graph starts: graph LR/TD/TB/BT/RL
        pattern = re.compile(
            r"(^|\n)(graph\s+(?:LR|TD|TB|BT|RL)\b[\s\S]*?)(?=\n(?:\*\*|###|\Z))",
            flags=re.IGNORECASE,
        )

        def _wrap(match):
            prefix = match.group(1)
            block = match.group(2).strip()
            return f"{prefix}```mermaid\n{block}\n```"

        return re.sub(pattern, _wrap, text, count=1)

    content = normalize_mermaid_blocks(content)
    linked_content = re.sub(pmid_pattern, replace_pmid, content)

    markdown_component = dcc.Markdown(
        linked_content,
        className="message-text m-0",
        dangerously_allow_html=True,
        link_target="_blank",
    )

    if is_user:
        # User Layout: right-aligned bubble with avatar
        avatar = html.Div(
            html.I(className="bi bi-person-fill"), className="chat-avatar user-avatar"
        )
        bubble_content = html.Div(markdown_component, className=f"{base_message_class}-content")
        message_parts = [bubble_content, avatar]
    else:
        # Assistant Layout: full-width bubble with avatar
        avatar = html.Div(
            html.I(className="bi bi-robot"), className="chat-avatar assistant-avatar"
        )

        import re

        main_content = content
        if suggestions is None:
            suggestions = []
            # Robust parsing for suggested questions using multiple headers
            suggestion_headers = [
                "Suggested Questions:",
                "Suggested Questions：",
                "建議問題:",
                "建議問題：",
                "建議的問題:",
                "建議的問題：",
                "Suggested Follow-up:",
                "Suggested Follow-up：",
                "提案された質問:",
                "提案された質問：",
            ]
            found_header = None
            for header in suggestion_headers:
                bolded = f"**{header}**"
                if bolded in content:
                    found_header = bolded
                    break

            if not found_header:
                for header in suggestion_headers:
                    if header in content:
                        found_header = header
                        break
            if found_header:
                parts = content.split(found_header)
                main_content = parts[0].strip()
                raw_suggestions = parts[1].strip().split("\n")
                for line in raw_suggestions:
                    line = line.strip()
                    # Remove bullet/numbering
                    clean_line = re.sub(r"^(?:\d+\.|\*|-|•)\s*", "", line).strip()
                    # Handle Q1: [Q1:] or other variations
                    clean_line = re.sub(
                        r"^\[?Q\d*[:\.\-\)\、：]?\s*(.*?)\]?$", r"\1", clean_line
                    ).strip()
                    # Remove trailing punctuation
                    clean_line = re.sub(r"[.?!]$", "", clean_line).strip()
                    if clean_line and len(clean_line) > 3:
                        suggestions.append(clean_line)

        main_content = normalize_mermaid_blocks(main_content)
        main_content = re.sub(r"[\s\*_#\-]+$", "", main_content).strip()

        # pmid_pattern is applied to main_content later during rendering
        markdown_component = dcc.Markdown(
            re.sub(pmid_pattern, replace_pmid, main_content),
            className="message-text m-0",
            dangerously_allow_html=True,
            link_target="_blank",
        )

        content_children = [markdown_component]

        copy_id_index = msg_id if msg_id else f"copy-{uuid.uuid4().hex[:8]}"
        content_children.append(
            html.Div(
                [
                    html.Pre(content, id=f"copy-text-{copy_id_index}", style={"display": "none"}),
                    html.I(
                        className="bi bi-files text-secondary p-2 js-copy-btn",
                        **{"data-copy-id": copy_id_index},
                        style={"fontSize": "1rem", "cursor": "pointer"},
                        title="Copy Response",
                    ),
                ],
                style={
                    "textAlign": "right",
                    "marginTop": "8px",
                    "borderTop": "1px solid #f0f0f0",
                    "paddingTop": "6px",
                },
            )
        )

        bubble_content = html.Div(
            [html.Div(content_children, className="message-bubble clearfix")],
            className=f"{base_message_class}-content",
        )
        assistant_column = [bubble_content]

        if suggestions:
            suggestion_btns = [
                dbc.Button(
                    q,
                    id={
                        "type": "suggested-question",
                        "index": f"suggest-{msg_id}-{i}" if msg_id else f"suggest-new-{i}",
                    },
                    color="light",
                    size="sm",
                    className="me-2 mb-2 px-3 text-start suggested-question-btn rounded-pill",
                )
                for i, q in enumerate(suggestions[:3])
            ]
            assistant_column.append(
                html.Div(
                    [
                        html.Div(suggestion_btns, className="d-flex flex-wrap gap-1 mt-3"),
                    ],
                    className="message-suggestions",
                )
            )

        if sources:
            source_badges = [
                html.A(
                    dbc.Badge(f"PMID:{pmid}", color="info", className="me-1", pill=True),
                    href=f"https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/{pmid}",
                    target="_blank",
                    style={"textDecoration": "none"},
                )
                for pmid in sources
            ]
            assistant_column.append(
                html.Div(
                    [html.Small("📎 Sources: ", className="text-muted")] + source_badges,
                    className="message-sources mt-2",
                )
            )

        message_parts = [
            avatar,
            html.Div(assistant_column, style={"maxWidth": "100%", "width": "100%"}),
        ]

    return html.Div(message_parts, className=wrapper_class)


# Chat messages container
chat_messages = html.Div(
    id="chat-messages",
    className="chat-messages-container",
    style={
        "height": "380px",
        "overflowY": "auto",
        "border": "1px solid #ddd",
        "borderRadius": "8px",
        "padding": "15px",
        "backgroundColor": "#f8f9fa",
        "display": "flex",
        "flexDirection": "column",  # Oldest messages at the top, newest at bottom
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
                    style={
                        "resize": "none",
                        "whiteSpace": "nowrap",
                        "overflow": "hidden",
                    },
                ),
                dbc.Button(
                    html.I(className="bi bi-arrow-up"),
                    id="chat-send-btn",
                    color="primary",
                    disabled=True,
                    className="chat-send-button",
                    style={"height": "44px", "width": "44px", "alignSelf": "end"},
                ),
            ],
            className="mb-2",
        ),
        html.Div(
            [
                html.Small(
                    "💡 Tip: Press Enter to send, Shift+Enter for a new line",
                    className="text-muted",
                    id="chat-input-hint",
                ),
                dcc.Loading(
                    id="chat-loading",
                    type="dot",
                    children=html.Div(id="chat-processing-status", className="small text-muted"),
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
                html.Div(
                    [
                        html.H6("📊 Selection Summary", className="mb-0"),
                        html.Span(
                            [
                                html.I(
                                    className="bi bi-info-circle ms-2 text-muted",
                                    id="selection-summary-info",
                                    style={"cursor": "pointer", "fontSize": "0.9rem"},
                                ),
                                dbc.Tooltip(
                                    "This count includes all unique PMIDs from selected nodes and edges. "
                                    "It may be larger than the 'Network Statistics' count because it includes "
                                    "PMIDs from isolated nodes that have no edges.",
                                    target="selection-summary-info",
                                    placement="right",
                                ),
                            ]
                        ),
                    ],
                    className="d-flex align-items-center mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Span("Articles: ", className="text-muted small"),
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
        html.Div(
            [
                dbc.Progress(
                    id="chat-analyze-progress",
                    value=100,
                    striped=True,
                    animated=True,
                    color="success",
                    className="chat-analyze-progress-bar mb-1",
                    style={"height": "6px", "borderRadius": "3px"},
                ),
                html.Div(
                    "🔬 Analyzing selection...",
                    id="chat-analyze-status-text",
                    className="text-muted small text-center mt-1",
                    style={"fontSize": "0.75rem"},
                ),
            ],
            id="chat-analyze-progress-container",
            style={"display": "none"},
            className="mb-2",
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
        dbc.Button(
            [html.I(className="bi bi-download me-2"), "Download History"],
            id="download-chat-btn",
            color="info",
            outline=True,
            size="sm",
            className="w-100 mt-1",
        ),
        dcc.Download(id="download-chat-history"),
        html.Div(id="chat-status", className="mt-2 small"),
    ],
    className="param",
)

# Chat Modal (for expanded view)
chat_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Chat History"), close_button=True),
        dbc.ModalBody(
            id="modal-chat-content",
            style={
                "minHeight": "400px",
                "display": "flex",
                "flexDirection": "column",
                "overflowY": "auto",
            },
        ),
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
                        dbc.Button(
                            html.I(className="bi bi-arrow-up"),
                            id="modal-chat-send-btn",
                            color="primary",
                            className="chat-send-button",
                            style={"height": "44px", "width": "44px"},
                        ),
                        width="auto",
                    ),
                    dbc.Col(
                        dcc.Loading(
                            id="modal-chat-loading",
                            type="dot",
                            children=html.Div(
                                id="modal-chat-processing-status", className="small text-muted"
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
        html.Div(id="chat-context-banner", className="chat-context-banner", style=display.none),
        html.Hr(),
        chat_messages,
        html.Hr(),
        chat_input,
        chat_modal,
        dcc.Store(id="chat-session-active", data=False),
        dcc.Store(id="chat-history-store", data=[]),
        dcc.Store(id="selected-edges-data", data=None),
        dcc.Store(id="suggested-question-store", data=None),
    ],
    id="chat-panel-container",
    style=display.none,
)
