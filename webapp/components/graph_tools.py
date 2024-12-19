import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title, icon_download
from webapp.utils import visibility

graph_layout = html.Div(
    [
        generate_param_title(
            "Graph Layout",
            "Select a layout to arrange the nodes",
            is_right=True,
        ),
        dcc.Dropdown(
            id="graph-layout",
            options=[
                {"label": "Preset", "value": "preset"},
                {"label": "Circle", "value": "circle"},
                {"label": "Grid", "value": "grid"},
                {"label": "Random", "value": "random"},
                {"label": "Concentric", "value": "concentric"},
                {"label": "Breadthfirst", "value": "breadthfirst"},
                {"label": "Cose", "value": "cose"},
            ],
            value="preset",
            style={"width": "200px"},
        ),
    ],
    className="param",
)


minimal_degree = html.Div(
    [
        generate_param_title(
            "Minimal Degree",
            "Set the minimum node degree to filter the graph",
            is_right=True,
        ),
        dbc.Input(
            id="node-degree",
            min=1,
            step=1,
            value=1,
            type="number",
            style={"width": "200px"},
        ),
        dcc.Store(id="memory-node-degree", data=1),
    ],
    className="param",
)

edge_weight_cutoff = html.Div(
    [
        generate_param_title(
            "Edge Weight Cutoff",
            "Set the minimum edge weight to filter the graph",
            is_right=True,
        ),
        dcc.Slider(
            0,
            20,
            1,
            value=3,
            marks=None,
            id="graph-cut-weight",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        dcc.Store(id="memory-graph-cut-weight", data=3),
    ],
    className="param",
)

graph_tools = html.Div(
    [
        dbc.Button(
            [
                icon_download(),
                "PubTator",
            ],
            id="download-pubtator-btn",
            className="export-btn",
            color="success",
            style=visibility.hidden,
        ),
        dcc.Download(id="download-pubtator"),
        dbc.Button(
            [
                icon_download(),
                "HTML",
            ],
            id="export-btn-html",
            className="export-btn",
        ),
        dcc.Download(id="export-html"),
        dbc.Button(
            [
                icon_download(),
                "XGMML",
            ],
            id="export-btn-xgmml",
            className="export-btn",
        ),
        dcc.Download(id="export-xgmml"),
        dbc.Button(
            html.Img(
                src=dash.get_asset_url("three-dots.svg"),
            ),
            # "Settings",
            id="graph-settings-btn",
            className="btn-secondary settings",
        ),
        html.Div(
            [
                html.H4("Settings"),
                graph_layout,
                edge_weight_cutoff,
                minimal_degree,
            ],
            id="graph-settings-collapse",
            className="settings-collapse",
            style=visibility.hidden,
        ),
    ],
    className="settings-container settings-background",
)
