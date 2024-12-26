import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

from webapp.utils import display


def generate_query_component(hidden=False):
    return html.Div(
        [
            html.H5("Query"),
            dbc.Input(placeholder="ex: COVID-19 AND PON1", type="text", id="data-input"),
        ],
        hidden=hidden,
    )


def generate_pmid_component(hidden=False):
    return html.Div(
        [
            html.H5("PMID"),
            dbc.Input(placeholder="ex: 33422831,33849366", type="text", id="data-input"),
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
                ),
            ),
            html.Div(id="output-data-upload"),
        ],
        hidden=hidden,
    )


def callbacks(app):
    @app.callback(
        Output("api-wrapper", "style"),
        Output("pubtator-file-wrapper", "style"),
        Input("api-toggle-items", "value"),
        prevent_initial_call=True,
    )
    def update_api_toggle(api_toggle):
        if api_toggle == "api":
            return display.block, display.none
        elif api_toggle == "file":
            return display.none, display.block

    @app.callback(
        Output("input-type", "children"),
        Input("input-type-selection", "value"),
    )
    def update_input_type(input_type):
        if input_type == "query":
            return [
                generate_query_component(hidden=False),
                generate_pmid_file_component(hidden=True),
            ]
        elif input_type == "pmids":
            return [
                generate_pmid_component(hidden=False),
                generate_pmid_file_component(hidden=True),
            ]
        elif input_type == "pmid_file":
            return [
                generate_query_component(hidden=True),
                generate_pmid_file_component(hidden=False),
            ]
