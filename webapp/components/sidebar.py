import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.advanced_settings import advanced_settings
from webapp.components.graph_tools import (
    edge_weight_cutoff,
    graph_layout,
    minimal_degree,
)
from webapp.components.utils import (
    generate_param_title,
    icon_download,
    icon_graph,
    icon_search,
)
from webapp.utils import display, visibility

api_or_file = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "Source",
                    (
                        "PubTator3 API: Search + Network Generation\n"
                        "PubTator File: Network Generation from PubTator File"
                    ),
                ),
                dbc.RadioItems(
                    id="api-toggle-items",
                    options=[
                        {"label": "PubTator3 API", "value": "api"},
                        {"label": "PubTator File", "value": "file"},
                    ],
                    value="api",
                    inline=True,
                ),
            ],
            className="param",
        )
    ],
    id="api-toggle",
)

pubtator_file = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "PubTator File",
                    "The file downloaded using the 'PubTator File' button after running the 'PubTator3 API'",
                ),
                dcc.Upload(
                    id="pubtator-file-data",
                    children=html.Div(
                        ["Drag and Drop or ", html.A("Select Files", className="hyperlink")],
                        className="upload-box form-control",
                    ),
                ),
                html.Div(id="pubtator-file-upload"),
            ],
            className="param",
        )
    ],
    style=display.none,
    id="pubtator-file-wrapper",
)

api_params = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "Search Type",
                    (
                        "Text Search: Use keywords to retrieve relevant articles (use double quotes to match whole words and AND/OR to combine keywords)\n"
                        "PMID: Retrieve articles by PubMed Identifier (PMID)\n"
                        "PMID File: Retrieve articles by a text file of PMIDs (one per line)"
                    ),
                ),
                dcc.Dropdown(
                    id="input-type-selection",
                    options=[
                        {"label": "Text Search", "value": "query"},
                        {"label": "PMID", "value": "pmids"},
                        {"label": "PMID File", "value": "pmid_file"},
                    ],
                    value="query",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(id="input-type", className="param"),
        html.Div(
            [
                generate_param_title("Sort", "Sort articles by recency or relevance"),
                dbc.RadioItems(
                    id="sort-toggle-methods",
                    options=[
                        {"label": "Recency", "value": "date"},
                        {"label": "Relevance", "value": "score"},
                    ],
                    value="date",
                    inline=True,
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "PubTator3 Parameters",
                    (
                        "Use MeSH Vocabulary: Replace original text in articles with standardized MeSH terms\n"
                        "Full Text: Build network from full-text articles if available, defaulting to abstracts otherwise (not recommended to enable)"
                    ),
                ),
                dbc.Checklist(
                    options=[
                        {"label": "Use MeSH Vocabulary", "value": "use_mesh"},
                        {"label": "Full Text", "value": "full_text"},
                    ],
                    switch=True,
                    id="pubtator-params",
                    value=["use_mesh"],
                ),
            ],
            className="param",
        ),
    ],
    id="api-wrapper",
)


network_params = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "Node Filter",
                    (
                        "All: Retain all annotations\n"
                        "MeSH: Retain annotations with standardized MeSH terms only\n"
                        "BioREx Relation: Retain annotations with high-confidence relationships from PubTator3 BioREx model"
                    ),
                ),
                dcc.Dropdown(
                    id="node-type",
                    options=[
                        {"label": "All", "value": "all"},
                        {"label": "MeSH", "value": "mesh"},
                        {"label": "BioREx Relation", "value": "relation"},
                    ],
                    value="all",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Weighting Method",
                    (
                        "Frequency: Calculate edge weights using co-occurence counts\n"
                        "NPMI: Calulate edge weights using normalized mutual pointwise information"
                    ),
                ),
                dcc.Dropdown(
                    id="weighting-method",
                    options=[
                        {"label": "Frequency", "value": "freq"},
                        {"label": "NPMI", "value": "npmi"},
                    ],
                    value="freq",
                    style={"width": "200px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Edge Weight Cutoff",
                    "Set the minimum edge weight to filter the graph",
                ),
                dcc.Slider(
                    0,
                    20,
                    1,
                    value=2,
                    marks=None,
                    id="cut-weight",
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Network Parameters",
                    "Community: Group nodes into communities",
                ),
                dbc.Checklist(
                    options=[
                        {"label": "Community", "value": "community"},
                    ],
                    switch=True,
                    id="cy-params",
                    value=["community"],
                ),
            ],
            className="param",
        ),
    ],
    id="cy-wrapper",
)


progress = html.Div(
    [
        html.Div(
            [html.H5("Progress"), html.P(" ", id="progress-status"), dbc.Progress(id="progress")],
            className="param",
        ),
        html.Div([dbc.Button("Submit", id="submit-button"), html.Div(id="output")]),
    ],
    id="progress-wrapper",
)

export_buttons = html.Div(
    [
        html.H5("Export", className="text-center"),
        dbc.Button([icon_download(), "HTML"], id="export-btn-html", className="export-btn"),
        dcc.Download(id="export-html"),
        dbc.Button([icon_download(), "XGMML"], id="export-btn-xgmml", className="export-btn"),
        dcc.Download(id="export-xgmml"),
        dbc.Button(
            [icon_download(), "PubTator"],
            id="download-pubtator-btn",
            className="export-btn",
            color="success",
            style=visibility.hidden,
        ),
        dcc.Download(id="download-pubtator"),
    ],
    className="param export-container",
)

search_panel = html.Div(
    [advanced_settings, api_or_file, api_params, pubtator_file, network_params, progress],
    id="search-panel",
)

graph_settings_panel = html.Div(
    [export_buttons, graph_layout, edge_weight_cutoff, minimal_degree],
    id="graph-settings-panel",
    style=display.none,
)

sidebar_toggle = dbc.RadioItems(
    id="sidebar-panel-toggle",
    options=[
        {"label": [icon_search(), "Search"], "value": "search"},
        {"label": [icon_graph(), "Graph"], "value": "graph"},
    ],
    value="search",
    inline=True,
    className="mb-3 sidebar-toggle",
    labelClassName="toggle-label",
    labelCheckedClassName="toggle-selected",
)

sidebar = html.Div(
    [sidebar_toggle, search_panel, graph_settings_panel],
    className="sidebar",
    id="sidebar-container",
)
