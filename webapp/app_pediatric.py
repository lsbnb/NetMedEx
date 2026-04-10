"""
NetMedEx: Pediatric CNS Tumor Edition  (Port 8051)
====================================================
Robust 3-panel research portal using minimal, conflict-free Dash architecture.
"""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
import logging
import dash_bootstrap_components as dbc
import diskcache
from flask import request
from dash import Dash, DiskcacheManager, Input, Output, State, callback_context, html, dcc, no_update
from netmedex.utils import config_logger
from webapp.utils import cleanup_tempdir

# ── Config ────────────────────────────────────────────────────────────────────
PEDIATRIC_PORT = int(os.getenv("PEDIATRIC_PORT", "8051"))
NETMEDEX_PORT  = int(os.getenv("NETMEDEX_PORT",  "8050"))
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets_pediatric")

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"), filename="webapp_pediatric.log")
logger = logging.getLogger(__name__)

cache = diskcache.Cache("./cache_pediatric")
bg_manager = DiskcacheManager(cache)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    background_callback_manager=bg_manager,
    suppress_callback_exceptions=True,
    assets_folder=_ASSETS_DIR,
)
app.title = "NetMedEx: Pediatric CNS Tumor Edition"
app._favicon = "NetMedEx_ico.ico"

# ══════════════════════════════════════════════════════════════════════════════
#  STATIC COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
topnav = html.Nav(
    id="ped-topnav",
    children=[
        # Brand
        html.Div([
            html.Span("🧠", style={"fontSize": "1.5rem"}),
            html.Div([
                html.Span("NetMedEx", style={
                    "fontWeight": "800", "fontSize": "1.0rem",
                    "color": "#fff", "display": "block", "lineHeight": "1.1",
                }),
                html.Span("Pediatric CNS Tumor Edition", style={
                    "fontSize": "0.58rem", "color": "#4fc3f7",
                    "letterSpacing": "1.2px", "textTransform": "uppercase", "fontWeight": "700",
                }),
            ], style={"marginLeft": "10px"}),
        ], style={"display": "flex", "alignItems": "center"}),

        # Navigation buttons
        html.Div([
            html.Button("📊 Dashboard",       id="nav-dashboard", n_clicks=0, className="ped-nav-btn"),
            html.Button("🕸️ Network Analysis", id="nav-network",   n_clicks=0, className="ped-nav-btn"),
            html.Button("💬 AI Chat",          id="nav-chat",       n_clicks=0, className="ped-nav-btn"),
        ], style={"display": "flex", "gap": "6px"}),

        # Right badges
        html.Div([
            html.Span("📄 9,957 Articles",  className="ped-badge"),
            html.Span("🧬 10,457 Nodes",   className="ped-badge"),
            html.Span("🔗 18,735 Edges",   className="ped-badge"),
            html.Span("🤖 99.8% Accuracy", className="ped-badge"),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
    ],
)

STATS = [
    ("📄", "Articles",     "9,957",  "#4fc3f7"),
    ("🧬", "Biomarkers",   "160",    "#81c784"),
    ("🔗", "Edges",        "18,735", "#ffb74d"),
    ("🧪", "Subtypes",     "8",      "#f06292"),
    ("🤖", "Accuracy",     "99.8%",  "#80cbc4"),
]

SUBTYPES = [
    ("all",  "All"),       ("shh",  "SHH-MB"),  ("myc",  "MYC-MB"),
    ("wnt",  "WNT-MB"),    ("g4",   "Group 4"),  ("idh",  "IDH-Glioma"),
    ("braf", "BRAF-PLGG"), ("tsc",  "TSC-SEGA"), ("h3k",  "H3K27M-DMG"),
]

stats_bar = html.Div([
    html.Div([
        html.Div(icon, style={"fontSize": "1.6rem"}),
        html.Div(val,  style={"fontSize": "1.3rem", "fontWeight": "800",
                              "color": color, "lineHeight": "1"}),
        html.Div(lbl,  style={"fontSize": "0.6rem",
                              "color": "rgba(232,244,253,0.5)",
                              "textTransform": "uppercase",
                              "letterSpacing": "0.6px", "marginTop": "3px"}),
    ], className="ped-stat-card")
    for icon, lbl, val, color in STATS
], className="ped-stats-bar")

subtype_bar = html.Div([
    html.Span("🔬 Subtype:", style={
        "color": "#4fc3f7", "fontWeight": "700",
        "fontSize": "0.78rem", "marginRight": "10px", "whiteSpace": "nowrap",
    }),
    *[html.Button(
        label,
        id=f"sub-btn-{key}",
        n_clicks=0,
        className="ped-subtype-btn" + (" active" if key == "all" else ""),
    ) for key, label in SUBTYPES],
], className="ped-subtype-selector")

HINTS = [
    "SHH 亞型的核心分子驅動因素與 Vismodegib 療效",
    "比較 MYC-MB 與 WNT-MB 的染色體不穩定性",
    "IDH-Glioma 在 10k 文獻中的 ATRX 突變頻率",
    "BRAF V600E 在 低度膠質瘤 的靶向療法現況",
    "H3K27M-DMG 的免疫治療新策略",
]


# ══════════════════════════════════════════════════════════════════════════════
#  DYNAMIC PANEL GENERATORS
# ══════════════════════════════════════════════════════════════════════════════
def get_dashboard_panel():
    return html.Div(
        id="panel-dashboard",
        children=[
            stats_bar,
            subtype_bar,
            html.Div(
                "Tip: If the Network or Chat panels fail to load, please ensure Port 8050 is active and forwarded in your environment.",
                style={"fontSize": "0.75rem", "color": "var(--PED-ORANGE)", "padding": "5px 20px"}
            ),
            html.Iframe(
                src="/assets/biodashboard.html",
                id="iframe-dashboard",
                style={"width": "100%", "flex": "1", "border": "none", "minHeight": "0"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column",
               "height": "calc(100vh - 60px)", "overflow": "hidden"},
    )

def get_network_panel(netmedex_url):
    return html.Div(
        id="panel-network",
        children=[
            html.Div([
                html.Span(f"⚡ Pre-loaded with 9k Pediatric CNS articles. Connecting to {netmedex_url}... "),
                html.A("🔗 如果畫面空白，請點此直接開啟主系統", href=netmedex_url, target="_blank", style={"color": "#ffb74d", "fontWeight": "bold", "textDecoration": "underline"})
            ], className="ped-info-banner"),
            html.Iframe(
                src=netmedex_url,
                id="iframe-network",
                style={"width": "100%", "flex": "1", "border": "none", "minHeight": "0"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column",
               "height": "calc(100vh - 60px)", "overflow": "hidden"},
    )

def get_chat_panel(netmedex_url):
    return html.Div(
        id="panel-chat",
        children=[
            html.Div([
                html.Div([
                    html.Span("💬 Pediatric CNS Tumor AI Assistant", style={
                        "fontWeight": "700", "fontSize": "0.95rem", "color": "#e8f4fd",
                    }),
                    html.Span(" · Connecting to main engine... ",
                              style={"fontSize": "0.68rem", "color": "rgba(232,244,253,0.4)",
                                     "marginLeft": "10px"}),
                    html.A("🔗 (如果畫面異常，點此直接開啟對話)", href=netmedex_url, target="_blank", style={"fontSize": "0.75rem", "color": "#ffb74d", "marginLeft": "10px", "textDecoration": "underline"})
                ], style={"display": "flex", "alignItems": "center"}),
                html.Span("🟢 Online", style={"fontSize": "0.75rem", "color": "#81c784"}),
            ], className="ped-chat-header"),

            html.Div([
                html.Div("💡 Quick prompts:", style={
                    "fontSize": "0.72rem", "color": "rgba(232,244,253,0.45)",
                    "marginBottom": "8px",
                }),
                html.Div([
                    html.Button(h, id=f"hint-{i}", n_clicks=0, className="ped-hint-btn")
                    for i, h in enumerate(HINTS)
                ], style={"display": "flex", "flexWrap": "wrap", "gap": "8px"}),
            ], className="ped-chat-hints"),

            html.Iframe(
                src=netmedex_url,
                id="iframe-chat",
                style={"width": "100%", "flex": "1", "border": "none", "minHeight": "0"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column",
               "height": "calc(100vh - 60px)", "overflow": "hidden"},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════
def serve_layout():
    return html.Div(
        [
            topnav,
            dcc.Store(id="active-panel-store", data="dashboard"),
            dcc.Location(id="app-location", refresh=False),
            html.Div(
                id="ped-content",
                # Initially only render the dashboard strictly so iframes don't cause cross-origin load crashes!
                children=get_dashboard_panel(),
                style={"flex": "1", "overflow": "hidden", "display": "flex", "flexDirection": "column"},
            ),
        ],
        style={
            "display": "flex", "flexDirection": "column",
            "height": "100vh", "background": "#0d1117", "overflow": "hidden",
        },
    )

app.layout = serve_layout


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
@app.callback(
    Output("active-panel-store", "data"),
    Input("nav-dashboard", "n_clicks"),
    Input("nav-network",   "n_clicks"),
    Input("nav-chat",      "n_clicks"),
    prevent_initial_call=False,
)
def update_active_panel(n1, n2, n3):
    triggered = callback_context.triggered_id
    if triggered == "nav-network":
        return "network"
    elif triggered == "nav-chat":
        return "chat"
    return "dashboard"


@app.callback(
    Output("ped-content", "children"),
    Output("nav-dashboard",   "className"),
    Output("nav-network",     "className"),
    Output("nav-chat",        "className"),
    Input("active-panel-store", "data"),
    State("app-location", "host"),
    prevent_initial_call=False,
)
def render_panel(active, host):
    if not host:
        host = "localhost"
    
    # Extract just the IP/domain without the current port
    raw_host = host.split(":")[0]
    netmedex_url = f"http://{raw_host}:{NETMEDEX_PORT}/"
    
    ACT  = "ped-nav-btn active"
    INACT = "ped-nav-btn"

    if active == "network":
        return get_network_panel(netmedex_url), INACT, ACT, INACT
    elif active == "chat":
        return get_chat_panel(netmedex_url), INACT, INACT, ACT
    else:   # default: dashboard
        return get_dashboard_panel(), ACT, INACT, INACT


def main():
    try:
        host = os.getenv("HOST", "0.0.0.0")
        print(f"\n{'='*60}")
        print(f"  🧠  NetMedEx: Pediatric CNS Tumor Edition")
        print(f"  🌐  http://localhost:{PEDIATRIC_PORT}")
        print(f"{'='*60}\n")
        app.run(host=host, port=PEDIATRIC_PORT,
                debug=(os.getenv("FLASK_DEBUG") == "true"))
    finally:
        cleanup_tempdir()

if __name__ == "__main__":
    main()
