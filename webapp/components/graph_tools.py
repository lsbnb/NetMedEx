import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title

graph_layout = html.Div(
    [
        generate_param_title(
            "Graph Layout",
            "Select a layout to arrange the nodes",
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
