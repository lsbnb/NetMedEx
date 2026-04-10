from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from webapp.utils import display


def generate_query_component(hidden=False, ai_enabled=False):
    if ai_enabled:
        placeholder = (
            "Ask a question (e.g., 'How does Icariin regulate osteoblasts?') for AI translation..."
        )
    else:
        placeholder = "Enter keywords (e.g., 'COVID-19 AND PON1')..."
    return html.Div(
        [
            html.H5("Query"),
            dbc.Textarea(
                placeholder=placeholder,
                id="data-input",
                style={"width": "100%", "minHeight": "120px", "resize": "vertical"},
                className="form-control",
            ),
        ],
        hidden=hidden,
    )


def generate_pmid_component(hidden=False):
    return html.Div(
        [
            html.H5("PMID"),
            dbc.Textarea(
                placeholder="ex: 33422831,33849366\nor paste a list of PMIDs...",
                id="data-input",
                style={"width": "100%", "minHeight": "100px", "resize": "vertical"},
                className="form-control",
            ),
        ],
        hidden=hidden,
    )


def generate_pmid_file_component(hidden=False):
    return html.Div(
        [
            html.H5("PMID File"),
            dcc.Upload(
                id="pmid-file-data",
                children=html.Div(
                    ["Drag and Drop or ", html.A("Select Files", className="hyperlink")],
                    className="upload-box form-control",
                    id="pmid-file-upload-trigger",
                ),
                style={"width": "100%"},
            ),
            html.Div(id="output-data-upload"),
        ],
        hidden=hidden,
    )


def callbacks(app):
    @app.callback(
        Output("api-wrapper", "style"),
        Output("pubtator-file-wrapper", "style"),
        Output("graph-file-wrapper", "style"),
        Input("api-toggle-items", "value"),
        prevent_initial_call=True,
    )
    def update_api_toggle(api_toggle):
        if api_toggle == "api":
            return display.block, display.none, display.none
        elif api_toggle == "file":
            return display.none, display.block, display.none
        elif api_toggle == "graph_file":
            return display.none, display.none, display.block
        # fallback
        return display.block, display.none, display.none

    @app.callback(
        Output("input-type", "children"),
        Input("input-type-selection", "value"),
        Input("ai-search-toggle", "value"),
    )
    def update_input_type(input_type, ai_enabled):
        if input_type == "query":
            return [
                generate_query_component(hidden=False, ai_enabled=ai_enabled),
                generate_pmid_file_component(hidden=True),
            ]
        elif input_type == "pmids":
            return [
                generate_pmid_component(hidden=False),
                generate_pmid_file_component(hidden=True),
            ]
        elif input_type == "pmid_file":
            return [
                generate_query_component(hidden=True, ai_enabled=ai_enabled),
                generate_pmid_file_component(hidden=False),
            ]
