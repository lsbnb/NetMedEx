
import dash_bootstrap_components as dbc
from dash import dcc, html
from webapp.components.utils import generate_param_title

chat_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Subnetwork Analysis & Chat")),
        dbc.ModalBody(
            [
                html.Div(
                    [
                        html.H5("Analysis Summary", className="text-secondary"),
                        dcc.Loading(
                            html.Div(id="llm-analysis-content", style={"whiteSpace": "pre-wrap"}),
                            type="default",
                        ),
                        html.Hr(),
                        html.H5("Chat", className="text-secondary"),
                        html.Div(
                            id="chat-history",
                            style={
                                "height": "300px",
                                "overflowY": "auto",
                                "border": "1px solid #ddd",
                                "marginBottom": "10px",
                                "padding": "10px",
                                "backgroundColor": "#f9f9f9"
                            },
                        ),
                        dbc.InputGroup(
                            [
                                dbc.Input(id="chat-input", placeholder="Ask a follow-up question...", type="text"),
                                dbc.Button("Send", id="chat-send-btn", color="primary", n_clicks=0),
                            ]
                        ),
                    ]
                )
            ]
        ),
        dbc.ModalFooter(
            dbc.Button("Close", id="close-chat-modal", className="ms-auto", n_clicks=0)
        ),
    ],
    id="chat-modal",
    size="lg",
    is_open=False,
    scrollable=True,
)

analyze_button = html.Div(
    [
        generate_param_title("AI Analysis", "Select nodes/edges in the graph and click Analyze."),
        dbc.Button("Analyze Selected Subnetwork", id="analyze-btn", color="info", className="w-100 mb-2"),
    ],
    className="param"
)
