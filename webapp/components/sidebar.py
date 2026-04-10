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
                        "PubTator File: Network Generation from PubTator File\n"
                        "Graph File: Load a previously exported NetMedEx graph (.pkl) to skip re-analysis"
                    ),
                ),
                dbc.RadioItems(
                    id="api-toggle-items",
                    options=[
                        {"label": "PubTator3 API", "value": "api"},
                        {"label": "PubTator File", "value": "file"},
                        {"label": "Graph File (.pkl)", "value": "graph_file"},
                    ],
                    value="api",
                    inline=True,
                    style={"fontSize": "0.76rem"},
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

# Define permanent upload components to ensure IDs always exist in layout
# Note: pmid-file-data is now managed in input_type_update.py

graph_file = html.Div(
    [
        html.Div(
            [
                generate_param_title(
                    "Graph File (.pkl)",
                    "Load a NetMedEx graph file (.pkl) exported from the Graph Panel. "
                    "Restores the full graph including semantic analysis results — no re-processing needed.",
                ),
                dcc.Upload(
                    id="graph-file-data",
                    accept=".pkl",
                    children=html.Div(
                        [
                            html.Div(
                                [
                                    "Drag and Drop or ",
                                    html.A("Select .pkl File", className="hyperlink"),
                                ],
                                className="upload-box form-control",
                                id="graph-file-upload-trigger",
                            ),
                        ],
                        style={"cursor": "pointer"},
                    ),
                    style={"width": "100%"},
                ),
                html.Div(id="graph-file-upload"),
            ],
            className="param",
        )
    ],
    style=display.none,
    id="graph-file-wrapper",
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
                                    value=False,
                                    className="me-2",
                                ),
                                html.Span(
                                    "🤖 Enable AI Search:",
                                    className="fw-bold me-2",
                                    style={"fontSize": "0.9rem", "whiteSpace": "nowrap"},
                                ),
                                html.Small(
                                    "Let AI translate your language into PubTator queries",
                                    className="text-muted",
                                    style={"fontSize": "0.8rem"},
                                ),
                            ],
                            className="d-flex align-items-center flex-wrap",
                        )
                    ],
                    color="info",
                    className="mb-0",
                    style={"padding": "0.5rem 0.75rem"},
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Query",
                    "Enter PMIDs (comma-separated), keywords, or natural language if AI Search is enabled.",
                ),
                dbc.Textarea(
                    placeholder="ex: COVID-19 AND PON1\nor paste a list of PMIDs (separate with comma or newline)...",
                    id="data-input",
                    style={"width": "100%", "minHeight": "120px", "resize": "vertical"},
                    className="form-control",
                ),
            ],
            id="input-type",
            className="param",
        ),
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
                html.Div(
                    [
                        generate_param_title(
                            "PubTator Parameters",
                            (
                                "Use MeSH Vocabulary: Replace original text in articles with standardized MeSH terms\n"
                                "Full Text: Build network from full-text articles if available, defaulting to abstracts otherwise (not recommended to enable)\n"
                                "Fetch Citation Counts: Fetch citation counts from OpenCitations for all articles (v0.9.7 feature)"
                            ),
                        ),
                    ],
                    className="flex-grow-1",
                ),
                dbc.Checklist(
                    options=[
                        {"label": "Use MeSH Vocabulary", "value": "use_mesh"},
                        {"label": "Full Text", "value": "full_text"},
                        {"label": "Fetch Citation Counts", "value": "fetch_citations"},
                    ],
                    id="pubtator-params",
                    value=["use_mesh"],
                    switch=True,
                    inline=True,
                    style={"fontSize": "0.76rem"},
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
                    (
                        "Suggested Settings:\n"
                        "• 0.3 - 0.5: Recommended (Balanced recall & precision)\n"
                        "• > 0.7: Strict (High-confidence evidence)\n"
                        "• < 0.2: Exploratory (Weak/novel associations)"
                    ),
                ),
                dcc.Slider(
                    0,
                    1.0,
                    0.05,
                    value=0.4,
                    marks={0: "0.0", 0.4: "0.4", 0.7: "0.7", 1.0: "1.0"},
                    id="semantic-threshold",
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            className="param",
            id="semantic-options",
            style=display.hidden_panel,
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

# Semantic coloring constants
COLOR_POSITIVE = "#28a745"  # Green
COLOR_NEGATIVE = "#dc3545"  # Red
COLOR_NEUTRAL = "#999999"  # Gray

NODE_TYPE_OPTIONS = [
    {"label": "Gene", "value": "Gene"},
    {"label": "Disease", "value": "Disease"},
    {"label": "Chemical", "value": "Chemical"},
    {"label": "Species", "value": "Species"},
    {"label": "CellLine", "value": "CellLine"},
    {"label": "DNAMutation", "value": "DNAMutation"},
    {"label": "ProteinMutation", "value": "ProteinMutation"},
    {"label": "SNP", "value": "SNP"},
    {"label": "Community", "value": "Community"},
]


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
            style=display.none,
        ),
        # Submit and Reset buttons
        html.Div(
            [
                dbc.Button(
                    "Submit",
                    id="submit-button",
                    color="primary",
                    size="lg",
                    className="mb-2",
                    style={"borderRadius": "8px", "flex": "2"},
                ),
                dbc.Button(
                    "Reset",
                    id="reset-button",
                    color="danger",
                    size="lg",
                    className="mb-2",
                    style={"borderRadius": "8px", "flex": "1"},
                ),
            ],
            className="d-flex gap-2 w-100",
        ),
        html.Div(id="output"),
    ],
    id="progress-wrapper",
)

export_buttons = html.Div(
    [
        generate_param_title(
            "Export",
            (
                "HTML/XGMML: Browser previews or Cytoscape import (preserves full network depth).\n"
                "PubTator: Original annotation file for re-analysis.\n"
                "RIS (EndNote): Full bibliographic metadata (authors, journal, DOI) for citation management.\n"
                "Graph (.pkl): Complete analysis state (including semantic results) for instant restoration."
            ),
        ),
        html.Div(
            [
                dbc.Button(
                    [icon_download(), "HTML"], id="export-btn-html", className="export-btn"
                ),
                dcc.Download(id="export-html"),
                dbc.Button(
                    [icon_download(), "XGMML"], id="export-btn-xgmml", className="export-btn"
                ),
                dcc.Download(id="export-xgmml"),
                dbc.Button(
                    [icon_download(), "PubTator"],
                    id="download-pubtator-btn",
                    className="export-btn",
                    color="success",
                ),
                dcc.Download(id="download-pubtator"),
                dbc.Button(
                    [icon_download(), "RIS (EndNote)"],
                    id="export-btn-ris",
                    className="export-btn",
                    color="info",
                ),
                dcc.Download(id="export-ris"),
                dbc.Button(
                    [icon_download(), "Graph (.pkl)"],
                    id="export-btn-graph",
                    className="export-btn",
                    color="warning",
                ),
                dcc.Download(id="export-graph"),
            ],
            className="d-flex gap-2 flex-wrap mt-1",
        ),
    ],
    className="param export-container",
)

search_panel = html.Div(
    [
        api_or_file,
        api_params,
        pubtator_file,
        graph_file,
        network_params,
        progress,
    ],
    id="search-panel",
)

graph_settings_panel = html.Div(
    [
        # Network Statistics Summary Card
        dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.H5("Network Statistics", className="mb-0 text-center"),
                                html.Span(
                                    [
                                        html.I(
                                            className="bi bi-info-circle ms-2 text-muted",
                                            id="network-stats-info",
                                            style={"cursor": "pointer", "fontSize": "0.8rem"},
                                        ),
                                        dbc.Tooltip(
                                            "This count represents unique PMIDs linked to explicit relationships (edges) in the current graph. "
                                            "It may be smaller than the Chat panel count because it excludes isolated nodes without edges.",
                                            target="network-stats-info",
                                            placement="bottom",
                                        ),
                                    ]
                                ),
                            ],
                            className="d-flex align-items-center justify-content-center mb-3",
                        ),
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
                    value=[],
                ),
            ],
            className="param",
        ),
        graph_layout,
        edge_weight_cutoff,
        html.Div(
            [
                generate_param_title(
                    "Edge Confidence Threshold",
                    "Only show semantic edges with confidence score above this value. "
                    "Higher values prioritize precision, while lower values increase recall.",
                ),
                dcc.Slider(
                    id="confidence-threshold",
                    min=0,
                    max=1,
                    step=0.05,
                    value=0.0,
                    marks={0: "0.0", 0.5: "0.5", 1.0: "1.0"},
                    tooltip={"placement": "bottom", "always_visible": True},
                    updatemode="drag",
                ),
            ],
            className="param",
            id="confidence-threshold-wrapper",
        ),
        html.Div(
            [
                generate_param_title(
                    "Search Nodes",
                    "Find nodes by name or identifier. Supports case-insensitive, fuzzy matching, and common synonym aliases.",
                ),
                dbc.Input(
                    id="graph-node-search",
                    type="text",
                    placeholder="e.g. metformin, MESH:D008687, TP53",
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                generate_param_title(
                    "Visible Node Types",
                    "Choose which node types remain visible in the graph.",
                ),
                dbc.Checklist(
                    id="graph-visible-node-types",
                    options=NODE_TYPE_OPTIONS,
                    value=[option["value"] for option in NODE_TYPE_OPTIONS],
                    inline=True,
                ),
            ],
            className="param",
        ),
        html.Div(
            [
                dbc.Button(
                    "Reset Graph View",
                    id="graph-reset-view-btn",
                    color="secondary",
                    outline=True,
                    className="w-100",
                ),
            ],
            className="param",
        ),
        minimal_degree,
    ],
    id="graph-settings-panel",
    style=display.hidden_panel,
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
    persistence=False,
)

# Header row containing tabs and settings
header_row = html.Div(
    [
        sidebar_toggle,
        html.Div(
            [
                html.Small("v1.1.0", className="text-muted", style={"fontSize": "0.7rem"}),
                advanced_settings,
            ],
            className="d-flex flex-column align-items-center ms-auto",
        ),
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
