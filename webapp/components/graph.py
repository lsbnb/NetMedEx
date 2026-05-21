from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import dcc, html

from webapp.components.graph_info import graph_info
from webapp.utils import CYTO_STYLESHEET, visibility

graph = html.Div(
    [
        html.Div(
            [
                dbc.Button(
                    html.I(className="bi bi-layout-sidebar"),
                    id="sidebar-toggle-btn",
                    color="light",
                    size="sm",
                    className="me-3 flex-shrink-0",
                    title="Toggle sidebar",
                ),
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
            className="d-flex flex-row align-items-center py-2",
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
        html.Div(id="sidebar-init", style={"display": "none"}),
        html.Div(
            [
                graph_info,
                # Spinner that activates when cy.elements is being updated.
                # Placed as a sibling (not a wrapper) so Cytoscape's flex height
                # is never disrupted.
                dcc.Loading(
                    id="cy-loading",
                    type="circle",
                    color="#0d6efd",
                    target_components={"cy": "elements"},
                    overlay_style={
                        "position": "absolute",
                        "top": "50%",
                        "left": "50%",
                        "transform": "translate(-50%, -50%)",
                        "zIndex": 20,
                        "pointerEvents": "none",
                    },
                    style={"display": "none"},
                ),
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
                dcc.Store(id="twohop-highlight-paths", data=[]),
                dcc.Store(id="sidebar-collapsed-store", storage_type="local", data=False),
            ],
            id="cy-graph-container",
            className="d-flex flex-column flex-grow-1 position-relative",
            style=visibility.hidden,
        ),
    ],
    id="graph-panel",
    className="d-flex flex-column flex-grow-1 main-div",
)
