from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from webapp.components.advanced_settings import advanced_settings
from webapp.components.chat import chat_panel
from webapp.components.graph_tools import (
    edge_weight_cutoff,
    graph_layout,
    minimal_degree,
)
from webapp.components.utils import (
    generate_param_title,
    icon_download,
)
from webapp.utils import display

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
        html.Div(
            [
                generate_param_title(
                    "AI Search",
                    "Use LLM to translate natural language queries into optimized PubTator boolean queries.",
                ),
                dbc.Alert(
                    [
                        html.Div(
                            [
                                dbc.Switch(
                                    id="ai-search-toggle",
                                    label="🤖 Enable AI-Powered Search",
                                    value=False,
                                    className="mb-2",
                                ),
                                html.Small(
                                    "Let AI translate your natural language into optimized search queries",
                                    className="d-block text-muted",
                                    style={"fontSize": "0.85rem"},
                                ),
                            ]
                        )
                    ],
                    color="info",
                    className="mb-0",
                    style={"padding": "0.75rem"},
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
                    "Edge Construction Method",
                    (
                        "Co-occurrence: Fast edge creation based on entity co-mentions (high recall)\n"
                        "Semantic Analysis: LLM-based relationship extraction (balanced precision/recall, requires API) ⚡\n"
                        "BioREx Relations Only: Use only expert-curated relationships (high precision, low coverage)"
                    ),
                ),
                dcc.Dropdown(
                    id="edge-method",
                    options=[
                        {"label": "Co-occurrence (Fast)", "value": "co-occurrence"},
                        {"label": "Semantic Analysis (LLM) ⚡", "value": "semantic"},
                        {"label": "BioREx Relations Only", "value": "relation"},
                    ],
                    value="co-occurrence",
                    style={"width": "250px"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Small(
                            "⚠️ Semantic analysis requires LLM configuration and may incur API costs.",
                            className="text-warning",
                        ),
                    ],
                    className="mb-2",
                ),
                generate_param_title(
                    "Semantic Confidence Threshold",
                    "Minimum confidence score (0-1) for LLM-identified relationships. Higher values = more precision, fewer edges.",
                ),
                dcc.Slider(
                    0,
                    1.0,
                    0.1,
                    value=0.5,
                    marks={0: "0.0", 0.5: "0.5", 1.0: "1.0"},
                    id="semantic-threshold",
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            className="param",
            id="semantic-options",
            style=display.none,
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
    ],
    id="cy-wrapper",
)


progress = html.Div(
    [
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        # Progress header
                        html.H5("Progress", className="mb-3"),
                        # Progress bar with percentage display
                        dbc.Progress(
                            [
                                dbc.Progress(
                                    value=0,
                                    id="progress",
                                    bar=True,
                                    animated=True,
                                    striped=True,
                                    style={"minHeight": "25px"},
                                )
                            ],
                            className="mb-3",
                            style={"height": "25px"},
                        ),
                        # Status message with icon
                        html.Div(
                            [
                                html.Span("", id="progress-status", className="text-muted"),
                            ],
                            className="d-flex align-items-center",
                        ),
                    ]
                )
            ],
            className="shadow-sm mb-3",
            id="progress-card",
        ),
        # Submit button
        html.Div(
            [
                dbc.Button(
                    "Submit",
                    id="submit-button",
                    color="primary",
                    size="lg",
                    className="w-100 mb-2",
                    style={"borderRadius": "8px"},
                ),
                html.Div(id="output"),
            ]
        ),
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
        ),
        dcc.Download(id="download-pubtator"),
    ],
    className="param export-container",
)

search_panel = html.Div(
    [api_or_file, api_params, pubtator_file, network_params, progress],
    id="search-panel",
)

graph_settings_panel = html.Div(
    [
        # Network Statistics Summary Card
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.H5("Network Statistics", className="mb-3 text-center"),
                        html.Div(
                            [
                                # Articles count
                                html.Div(
                                    [
                                        html.Div("📄", style={"fontSize": "1.5rem"}),
                                        html.Div(
                                            [
                                                html.H4("0", id="stat-articles", className="mb-0"),
                                                html.Small("Articles", className="text-muted"),
                                            ]
                                        ),
                                    ],
                                    className="d-flex align-items-center gap-2 mb-2",
                                ),
                                # Nodes count
                                html.Div(
                                    [
                                        html.Div("🔵", style={"fontSize": "1.5rem"}),
                                        html.Div(
                                            [
                                                html.H4("0", id="stat-nodes", className="mb-0"),
                                                html.Small("Nodes", className="text-muted"),
                                            ]
                                        ),
                                    ],
                                    className="d-flex align-items-center gap-2 mb-2",
                                ),
                                # Edges count
                                html.Div(
                                    [
                                        html.Div("🔗", style={"fontSize": "1.5rem"}),
                                        html.Div(
                                            [
                                                html.H4("0", id="stat-edges", className="mb-0"),
                                                html.Small("Edges", className="text-muted"),
                                            ]
                                        ),
                                    ],
                                    className="d-flex align-items-center gap-2",
                                ),
                            ]
                        ),
                    ]
                )
            ],
            className="shadow-sm mb-3",
            style={"backgroundColor": "rgba(255, 255, 255, 0.1)"},
        ),
        export_buttons,
        html.Div(
            [
                generate_param_title(
                    "Network Display",
                    "Community: Group nodes into communities for better visualization",
                ),
                dbc.Checklist(
                    options=[
                        {"label": "Show Communities", "value": "community"},
                    ],
                    switch=True,
                    id="cy-params",
                    value=["community"],
                ),
            ],
            className="param",
        ),
        dcc.Store(id="memory-cy-params", data=["community"]),  # Store for tracking changes
        graph_layout,
        edge_weight_cutoff,
        minimal_degree,
    ],
    id="graph-settings-panel",
    style=display.none,
)

# Store to hold total statistics
total_stats_store = dcc.Store(id="total-stats", data={"articles": 0, "nodes": 0, "edges": 0})

sidebar_toggle = dbc.Tabs(
    [
        dbc.Tab(
            label="🔍 Search",
            tab_id="search",
            label_style={"cursor": "pointer", "color": "black"},
            active_label_style={
                "color": "black",
                "fontWeight": "bold",
                "backgroundColor": "white",
            },
        ),
        dbc.Tab(
            label="🕸️ Graph",
            tab_id="graph",
            label_style={"cursor": "pointer", "color": "black"},
            active_label_style={
                "color": "black",
                "fontWeight": "bold",
                "backgroundColor": "white",
            },
        ),
        dbc.Tab(
            label="💬 Chat",
            tab_id="chat",
            label_style={"cursor": "pointer", "color": "black"},
            active_label_style={
                "color": "black",
                "fontWeight": "bold",
                "backgroundColor": "white",
            },
        ),
    ],
    id="sidebar-panel-toggle",
    active_tab="search",
    className="flex-grow-1",  # Take available space
)

# Header row containing tabs and settings
header_row = html.Div(
    [
        sidebar_toggle,
        advanced_settings,
    ],
    className="d-flex align-items-center mb-3",
)

sidebar = html.Div(
    [
        header_row,
        search_panel,
        graph_settings_panel,
        chat_panel,
        total_stats_store,
    ],
    className="sidebar",
    id="sidebar-container",
)
