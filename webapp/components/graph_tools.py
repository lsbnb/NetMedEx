from __future__ import annotations

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
            (
                "Filter edges by weight range:\n"
                "• Frequency mode: Keep edges with co-occurrence count within range\n"
                "• NPMI mode: Keep edges within NPMI score range:\n"
                "   - 0.3 - 0.5 (Broad Association): Common comorbidities or standard therapies\n"
                "   - 0.5 - 0.8 (Specific Association): Precise mechanisms (e.g. target proteins)\n"
                "   - 0.8 - 1.0 (Strong Coupling): Medical definitions or rare findings"
            ),
            id="edge-weight-cutoff-label",
        ),
        dcc.RangeSlider(
            id="graph-cut-weight",
            min=0,
            max=20,
            step=1,
            value=[0, 20],
            marks={i: str(i) for i in range(0, 21, 5)},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        dcc.Store(id="memory-graph-cut-weight", data=[0, 20]),
    ],
    className="param",
)
