from __future__ import annotations

import dash
from dash import dcc, html
import dash_cytoscape as cyto

from webapp.components.graph_info import graph_info
from webapp.utils import visibility

graph = html.Div(
    [
        html.Div(
            [
                html.Img(src=dash.get_asset_url("NetMedEx.png"), height="40px"),
                html.Span(
                    "💡 Tip: Hold Shift + Left Click and drag to select a subnetwork",
                    className="ms-4 align-self-center text-secondary fst-italic",
                    style={"fontSize": "0.9rem"},
                ),
            ],
            className="d-flex flex-row justify-content-center align-items-center py-2",
        ),
        html.Div(
            [
                graph_info,
                html.Div(
                    [
                        cyto.Cytoscape(
                            id="cy",
                            elements=[],
                            style={"width": "100%", "height": "100%"},
                            boxSelectionEnabled=True,
                            minZoom=0.1,
                            maxZoom=20,
                        )
                    ],
                    id="cy-graph",
                    className="flex-grow-1",
                ),
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
