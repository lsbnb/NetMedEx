from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title
from webapp.utils import display

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
                {"label": "fCose", "value": "fcose"},
                {"label": "Cose", "value": "cose"},
                {"label": "Circle", "value": "circle"},
                {"label": "Grid", "value": "grid"},
                {"label": "Random", "value": "random"},
                {"label": "Concentric", "value": "concentric"},
                {"label": "Breadthfirst", "value": "breadthfirst"},
            ],
            value="fcose",
            style={"width": "200px"},
        ),
        # Node Repulsion slider (visible only when fcose is selected)
        html.Div(
            [
                generate_param_title(
                    "Node Repulsion",
                    "Higher values push nodes further apart, reducing crowding in dense networks.",
                ),
                dcc.Slider(
                    id="fcose-node-repulsion",
                    min=10000,
                    max=100000,
                    step=5000,
                    value=45000,
                    marks={10000: "10k", 45000: "45k", 100000: "100k"},
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            id="fcose-repulsion-wrapper",
            className="mt-2",
            style=display.hidden_panel,
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
    ],
    className="param",
)

edge_weight_cutoff = html.Div(
    [
        generate_param_title(
            "Edge Weight Cutoff",
            (
                "Filter edges by normalized weight (0-20):\n"
                "• Frequency mode: Co-occurrence count (scaled to 0-20 relative to max)\n"
                "• NPMI mode: Raw NPMI score (0.3-1.0) scaled to 6-20 range:\n"
                "   - 6 - 10 (NPMI 0.3-0.5, Broad Association): Common comorbidities\n"
                "   - 10 - 16 (NPMI 0.5-0.8, Specific Association): Precise mechanisms\n"
                "   - 16 - 20 (NPMI 0.8-1.0, Strong Coupling): Medical definitions"
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
    ],
    id="edge-weight-cutoff-wrapper",
    className="param",
)
