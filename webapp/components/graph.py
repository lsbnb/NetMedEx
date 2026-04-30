from __future__ import annotations

import dash
import dash_cytoscape as cyto
from dash import dcc, html

from webapp.components.graph_info import graph_info
from webapp.utils import visibility, CYTO_STYLESHEET

graph = html.Div(
    [
        html.Div(
            [
                html.A(
                    html.Img(src=dash.get_asset_url("NetMedEx.png"), height="40px"),
                    href="https://github.com/lsbnb",
                    target="_blank",
                ),
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
                html.I(className="bi bi-diagram-3"),
                html.H4("No network loaded"),
                html.P(
                    "Run a search or upload a file from the Search panel to generate a knowledge graph.",
                    className="text-muted",
                ),
            ],
            id="graph-empty-state",
        ),
        html.Div(
            [
                graph_info,
                html.Div(
                    id="cytoscape-graph",
                    className="flex-grow-1",
                    children=cyto.Cytoscape(
                        id="cy",
                        elements=[],
                        style={"width": "100%", "height": "100%"},
                        stylesheet=CYTO_STYLESHEET,
                        boxSelectionEnabled=True,
                        minZoom=0.1,
                        maxZoom=20,
                    ),
                ),
                dcc.Store(id="is-new-graph", data=False),
                dcc.Store(id="pmid-title-dict", data={}),
                dcc.Store(id="pmid-citation-dict", data={}),
                dcc.Store(id="memory-node-degree", data=1),
                dcc.Store(id="memory-graph-cut-weight", data=[0, 20]),
                dcc.Store(id="memory-cy-params", data=[]),
                dcc.Store(id="memory-graph-layout"),
                dcc.Store(id="memory-fcose-node-repulsion"),
                dcc.Store(id="session-language", data="English"),
            ],
            id="cy-graph-container",
            className="d-flex flex-column flex-grow-1 position-relative",
            style=visibility.hidden,
        ),
    ],
    className="d-flex flex-column flex-grow-1 main-div",
)
