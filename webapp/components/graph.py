import dash
from dash import dcc, html

from webapp.components.graph_info import graph_info
from webapp.utils import visibility

graph = html.Div(
    [
        html.Div(
            [
                html.Img(src=dash.get_asset_url("NetMedEx.png"), height="40px"),
            ],
            className="d-flex flex-row justify-content-center",
        ),
        html.Div(
            [
                graph_info,
                html.Div(id="cy-graph", className="flex-grow-1"),
                dcc.Store(id="is-new-graph", data=False),
                dcc.Store(id="pmid-title-dict", data={}),
            ],
            id="cy-graph-container",
            className="d-flex flex-column flex-grow-1 position-relative",
            style=visibility.hidden,
        ),
    ],
    className="d-flex flex-column flex-grow-1 main-div",
)
