from __future__ import annotations

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
            style={"width": "100%", "color": "#1f0737"},
            className="text-dark",
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
                    max=200000,
                    step=5000,
                    value=45000,
                    marks={10000: "10k", 45000: "45k", 100000: "100k", 200000: "200k"},
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
        dcc.Slider(
            id="node-degree",
            min=1,
            max=20,
            step=1,
            value=1,
            marks={1: "1", 5: "5", 10: "10", 15: "15", 20: "20"},
            tooltip={"placement": "bottom", "always_visible": True},
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


# Grow the view by linking any entity in the full graph to the graph's core
# (anchor) nodes through its best few-hop paths -- see callbacks/node_connect.py.
core_connect = html.Div(
    [
        generate_param_title(
            "Connect to Core Nodes",
            "Search one or more entities in the full knowledge graph and add their\n"
            "best paths to the core nodes shown at start, within the hop limit.\n"
            "Paths prefer fewer hops and edges supported by more papers, and avoid\n"
            "detours through generic hubs (e.g. patient, inflammation).",
        ),
        dcc.Dropdown(
            id="connect-node-select",
            options=[],
            placeholder="Type entities, e.g. miR-21, NLRP3, IL-6",
            multi=True,
            searchable=True,
            clearable=True,
        ),
        html.Div(
            [
                html.Span("Max hops", className="small me-2"),
                dcc.Dropdown(
                    id="connect-max-hops",
                    options=[{"label": str(n), "value": n} for n in (1, 2, 3, 4)],
                    value=3,
                    clearable=False,
                    style={"width": "70px"},
                ),
                html.Button(
                    "Add & connect",
                    id="connect-node-btn",
                    className="btn btn-primary btn-sm ms-auto",
                ),
                html.Button(
                    "Undo",
                    id="connect-undo-btn",
                    className="btn btn-outline-secondary btn-sm ms-2",
                    title="Remove the nodes added by the last Connect or Expand",
                ),
            ],
            className="d-flex align-items-center mt-2",
        ),
        html.Div(
            id="connect-node-status",
            className="small text-muted mt-1",
            style={"whiteSpace": "pre-line"},
        ),
    ],
    className="param",
)
