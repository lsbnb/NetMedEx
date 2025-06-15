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


node_info = html.Div(
    [
        html.H5("Node Info", className="text-center"),
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
