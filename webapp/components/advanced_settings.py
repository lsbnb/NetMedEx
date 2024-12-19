import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.utils import generate_param_title
from webapp.utils import visibility

max_articles = html.Div(
    [
        generate_param_title(
            "Max Articles",
            "Set the maximum number of articles retrieved via API",
        ),
        dcc.Slider(
            50,
            3000,
            50,
            value=1000,
            marks=None,
            id="max-articles",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ],
    className="param",
)

max_edges = html.Div(
    [
        generate_param_title(
            "Max Edges",
            "Set the maximum number of edges to display in the graph (0: No limit)",
        ),
        dcc.Slider(
            0,
            1000,
            50,
            value=1000,
            marks=None,
            id="max-edges",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ],
    className="param",
)


advanced_settings = html.Div(
    [
        dbc.Button(
            html.Img(src=dash.get_asset_url("icon_config.svg"), width=22, height=22),
            # "Settings",
            id="advanced-settings-btn",
            className="btn-secondary settings",
        ),
        html.Div(
            [
                html.H5("Advanced Settings", className="text-center"),
                max_articles,
                max_edges,
            ],
            id="advanced-settings-collapse",
            className="settings-collapse",
            style=visibility.hidden,
        ),
    ],
    id="advanced-settings",
    className="settings-container",
)
