from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import icon_download
from webapp.utils import visibility


def create_legend_box(icon, text):
    return html.Div(
        [
            html.Img(src=dash.get_asset_url(icon), width=25, height=25),
            html.P(text),
        ],
        className="legend-box",
    )


edge_info = html.Div(
    [
        html.H5("Edge Info", className="text-center"),
        dbc.Button([icon_download(), "CSV"], id="export-edge-btn", className="export-btn"),
        dcc.Download(id="export-edge-csv"),
        html.Div(id="edge-info"),
    ],
    id="edge-info-container",
    className="flex-grow-1",
    style=visibility.hidden,
)


EXPANDABLE_NODE_TYPES = [
    "Gene",
    "Chemical",
    "Disease",
    "Pathway",
    "BiologicalProcess",
    "Phenotype",
    "CellLine",
    "CellularComponent",
    "Species",
    "ProteinMutation",
    "DNAMutation",
    "SNP",
]

# Grow the view from the selected node using the full (unpruned) session
# graph, so a pathway can be followed hop by hop instead of being limited to
# the edges that survived the interactive-rendering caps.
node_expand_controls = html.Div(
    [
        html.Div(
            [
                dbc.Button(
                    "Expand neighbors",
                    id="expand-node-btn",
                    size="sm",
                    color="primary",
                    title="Add this node's strongest neighbors from the full graph "
                    "(click again for the next batch)",
                ),
                dbc.Select(
                    id="expand-node-count",
                    options=[{"label": str(n), "value": n} for n in (10, 25, 50)],
                    value=10,
                    size="sm",
                    style={"width": "70px"},
                ),
                dbc.Button(
                    "Undo",
                    id="expand-node-undo-btn",
                    size="sm",
                    color="secondary",
                    outline=True,
                    title="Remove the nodes added by the last expansion",
                ),
            ],
            className="d-flex gap-2 align-items-center",
        ),
        dcc.Dropdown(
            id="expand-node-types",
            options=EXPANDABLE_NODE_TYPES,
            multi=True,
            placeholder="All node types",
            className="mt-2",
        ),
        dbc.Checkbox(
            id="expand-node-multi-pmid",
            label="Only edges supported by ≥2 papers",
            value=True,
            className="mt-1",
        ),
        html.Div(id="expand-node-status", className="small text-muted mt-1"),
        dcc.Store(id="expand-node-history", data=[]),
    ],
    id="node-expand-controls",
    className="mb-2 pb-2 border-bottom",
)


node_info = html.Div(
    [
        html.H5("Node Info", className="text-center"),
        # Controls above the info body: a hub's PMID list can run to thousands
        # of rows, which would push them out of reach.
        node_expand_controls,
        html.Div(id="node-info"),
    ],
    id="node-info-container",
    className="flex-grow-1",
    style=visibility.hidden,
)


legend = html.Div(
    [
        create_legend_box("icon_species.svg", "Species"),
        create_legend_box("icon_chemical.svg", "Chemical"),
        create_legend_box("icon_gene.svg", "Gene"),
        create_legend_box("icon_disease.svg", "Disease"),
        create_legend_box("icon_cellline.svg", "CellLine"),
        create_legend_box("icon_dnamutation.svg", "DNAMutation"),
        create_legend_box("icon_proteinmutation.svg", "ProteinMutation"),
        create_legend_box("icon_snp.svg", "SNP"),
    ],
    id="legend-container",
)

graph_info = html.Div([edge_info, node_info, legend], id="bottom-container", className="d-flex")
