"""
NetMedEx: Pediatric CNS Tumor Edition  (Port 8051)
====================================================
Persistent-panel architecture: Dashboard and NetMedEx (Network+Chat) panels
are always in the DOM, toggled via CSS display, so iframe state is fully
preserved when switching tabs.  A context bar bridges the subtype selected
in the Dashboard into the Network/Chat panel with subtype-specific prompts.
"""

from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()

import os
import logging
from pathlib import Path
from urllib.parse import urlparse
import dash_bootstrap_components as dbc
import diskcache
from dash import (
    Dash,
    DiskcacheManager,
    Input,
    Output,
    State,
    callback_context,
    html,
    dcc,
    no_update,
)
from netmedex.utils import config_logger
from webapp.utils import cleanup_tempdir

# ── Config ────────────────────────────────────────────────────────────────────
PEDIATRIC_PORT = int(os.getenv("PEDIATRIC_PORT", "8051"))
NETMEDEX_PORT = int(os.getenv("NETMEDEX_PORT", "8050"))
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets_pediatric")

config_logger(is_debug=(os.getenv("LOGGING_DEBUG") == "true"), filename="webapp_pediatric.log")
logger = logging.getLogger(__name__)

cache = diskcache.Cache(str(Path(__file__).parent / "cache_pediatric"))
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
#  DATA CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
STATS = [
    ("📄", "Articles", "9,957", "#4fc3f7"),
    ("🧬", "Biomarkers", "160", "#81c784"),
    ("🔗", "Edges", "18,735", "#ffb74d"),
    ("🧪", "Subtypes", "8", "#f06292"),
    ("🤖", "Accuracy", "99.8%", "#80cbc4"),
]

SUBTYPES = [
    ("all", "All"),
    ("shh", "SHH-MB"),
    ("myc", "MYC-MB"),
    ("wnt", "WNT-MB"),
    ("g4", "Group 4"),
    ("idh", "IDH-Glioma"),
    ("braf", "BRAF-PLGG"),
    ("tsc", "TSC-SEGA"),
    ("h3k", "H3K27M-DMG"),
]

SUBTYPE_DETAILS = {
    "all": (
        "All Pediatric CNS Tumors",
        "Overview across medulloblastoma, pediatric glioma, BRAF-altered PLGG, TSC-SEGA, and H3K27M-DMG literature.",
    ),
    "shh": (
        "SHH-MB",
        "Sonic Hedgehog medulloblastoma context for pathway activation, SMO inhibitors, resistance, and outcome markers.",
    ),
    "myc": (
        "MYC-MB",
        "High-risk MYC-driven medulloblastoma context focused on amplification, cell-cycle programs, and therapeutic vulnerability.",
    ),
    "wnt": (
        "WNT-MB",
        "WNT medulloblastoma context focused on CTNNB1 biology, favorable prognosis, and de-escalation evidence.",
    ),
    "g4": (
        "Group 4 Medulloblastoma",
        "Group 4 medulloblastoma context for chromosomal instability, enhancer programs, and risk stratification.",
    ),
    "idh": (
        "IDH-Glioma",
        "Pediatric and adolescent IDH-mutant glioma context for ATRX, TP53, methylation class, and treatment response.",
    ),
    "braf": (
        "BRAF-PLGG",
        "BRAF-altered pediatric low-grade glioma context for V600E, fusion events, MAPK targeting, and resistance.",
    ),
    "tsc": (
        "TSC-SEGA",
        "Tuberous sclerosis complex and SEGA context for mTOR signaling, everolimus response, and surveillance.",
    ),
    "h3k": (
        "H3K27M-DMG",
        "Diffuse midline glioma context for H3K27 alteration, epigenetic therapy, immunotherapy, and clinical trials.",
    ),
}

# Subtype-specific prompts bridged from Dashboard into the Network/Chat context bar
SUBTYPE_HINTS = {
    "all": [
        "小兒 CNS 腫瘤的主要分子標誌物有哪些？",
        "比較各亞型的一線治療策略",
        "10k 文獻中預後最差的亞型特徵",
    ],
    "shh": [
        "SHH 亞型的 SMO/GLI 通路激活機制",
        "Vismodegib 在 SHH-MB 的療效與耐藥機制",
        "PTCH1 突變如何驅動 Hedgehog 通路",
    ],
    "myc": [
        "MYC 擴增如何驅動高風險髓母細胞瘤",
        "MYC-MB 的細胞週期靶點與治療策略",
        "MYCN 與 MYC 在髓母細胞瘤中的角色差異",
    ],
    "wnt": [
        "WNT-MB 的 CTNNB1 突變與 β-catenin 核轉位機制",
        "WNT 亞型預後良好的分子基礎",
        "WNT-MB 去強化治療 (de-escalation) 的臨床證據",
    ],
    "g4": [
        "Group 4 髓母細胞瘤的染色體不穩定性機制",
        "MYCN 擴增在 Group 4 的預後意義",
        "Group 4 的增強子重組 (enhancer hijacking) 與風險分層",
    ],
    "idh": [
        "IDH-Glioma 中 ATRX 與 TP53 共突變的意義",
        "IDH1 R132H 的甲基化特徵與治療反應",
        "小兒與成人 IDH 膠質瘤的分子差異",
    ],
    "braf": [
        "BRAF V600E 在 PLGG 的 MEK/MAPK 靶向療法",
        "KIAA1549-BRAF 融合在 BRAF-PLGG 的診斷意義",
        "Dabrafenib + Trametinib 聯合治療的療效與安全性",
    ],
    "tsc": [
        "TSC1/TSC2 突變如何啟動 mTOR 通路",
        "Everolimus 在 SEGA 治療的反應與監測",
        "Tuberous Sclerosis Complex 的多系統表現",
    ],
    "h3k": [
        "H3K27M 突變的表觀遺傳機制與 EZH2 靶向療法",
        "H3K27M-DMG 的免疫治療策略（PD-1/PD-L1）",
        "擴散性中線膠質瘤的臨床試驗現況",
    ],
}

# Top biomarkers per subtype — used as clickable Network search tags in the context bar
SUBTYPE_BIOMARKERS = {
    "all": ["EGFR", "AKT", "mTOR", "GFAP", "IDH1"],
    "shh": ["SHH", "SMO", "PTCH1", "GLI1", "MYCN"],
    "myc": ["MYC", "MYCN", "SOX2", "AKT", "beta-catenin"],
    "wnt": ["beta-catenin", "AKT", "SOX2", "mTOR", "CTNNB1"],
    "g4": ["MYCN", "MYC", "AKT", "CDX2", "KCNA1"],
    "idh": ["IDH1", "IDH2", "ATRX", "MGMT", "TERT"],
    "braf": ["BRAF", "MEK", "KIAA1549", "dabrafenib", "trametinib"],
    "tsc": ["TSC2", "TSC1", "mTOR", "everolimus", "AKT"],
    "h3k": ["TMZ", "MGMT", "IDH1", "EGFR", "AKT"],
}

# K-Means cluster most representative of each clinical subtype
SUBTYPE_TO_CLUSTER = {
    "all": 0,  # general mixed cohort
    "shh": 5,  # SHH 100% dominant
    "myc": 1,  # c-myc 100% dominant
    "wnt": 1,  # WNT-MB shares MB articles; beta-catenin in cluster 1
    "g4": 1,  # Group 4 MB, MYCN present in cluster 1
    "idh": 2,  # IDH 100% dominant
    "braf": 4,  # BRAF 98.7%, V600E 65.8%
    "tsc": 3,  # TSC2 97.7%, TSC1 73.6%
    "h3k": 7,  # H3K27M-DMG; TMZ-treated glioma cluster
}

_PANEL_FLEX = {
    "display": "flex",
    "flexDirection": "column",
    "height": "calc(100vh - 60px)",
    "overflow": "hidden",
}
_PANEL_HIDDEN = {"display": "none"}


def get_netmedex_url(current_href: str | None) -> str:
    parsed = urlparse(current_href or "")
    hostname = parsed.hostname or os.getenv("NETMEDEX_HOST") or "localhost"
    scheme = parsed.scheme or os.getenv("NETMEDEX_SCHEME") or "http"
    return f"{scheme}://{hostname}:{NETMEDEX_PORT}/"


# ══════════════════════════════════════════════════════════════════════════════
#  STATIC COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
topnav = html.Nav(
    id="ped-topnav",
    children=[
        html.Div(
            [
                html.Span("🧠", style={"fontSize": "1.5rem"}),
                html.Div(
                    [
                        html.Span(
                            "NetMedEx",
                            style={
                                "fontWeight": "800",
                                "fontSize": "1.0rem",
                                "color": "#fff",
                                "display": "block",
                                "lineHeight": "1.1",
                            },
                        ),
                        html.Span(
                            "Pediatric CNS Tumor Edition",
                            style={
                                "fontSize": "0.58rem",
                                "color": "#4fc3f7",
                                "letterSpacing": "1.2px",
                                "textTransform": "uppercase",
                                "fontWeight": "700",
                            },
                        ),
                    ],
                    style={"marginLeft": "10px"},
                ),
            ],
            style={"display": "flex", "alignItems": "center"},
        ),
        html.Div(
            [
                html.Button(
                    "📊 Dashboard", id="nav-dashboard", n_clicks=0, className="ped-nav-btn active"
                ),
                html.Button(
                    "🕸️ Network Analysis", id="nav-network", n_clicks=0, className="ped-nav-btn"
                ),
                html.Button("💬 AI Chat", id="nav-chat", n_clicks=0, className="ped-nav-btn"),
            ],
            style={"display": "flex", "gap": "6px"},
        ),
        html.Div(
            [
                html.Span("📄 9,957 Articles", className="ped-badge"),
                html.Span("🧬 10,457 Nodes", className="ped-badge"),
                html.Span("🔗 18,735 Edges", className="ped-badge"),
                html.Span("🤖 99.8% Accuracy", className="ped-badge"),
            ],
            style={"display": "flex", "alignItems": "center", "gap": "6px"},
        ),
    ],
)

stats_bar = html.Div(
    [
        html.Div(
            [
                html.Div(icon, style={"fontSize": "1.6rem"}),
                html.Div(
                    val,
                    style={
                        "fontSize": "1.3rem",
                        "fontWeight": "800",
                        "color": color,
                        "lineHeight": "1",
                    },
                ),
                html.Div(
                    lbl,
                    style={
                        "fontSize": "0.6rem",
                        "color": "rgba(232,244,253,0.5)",
                        "textTransform": "uppercase",
                        "letterSpacing": "0.6px",
                        "marginTop": "3px",
                    },
                ),
            ],
            className="ped-stat-card",
        )
        for icon, lbl, val, color in STATS
    ],
    className="ped-stats-bar",
)


# ══════════════════════════════════════════════════════════════════════════════
#  DYNAMIC COMPONENT BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def get_subtype_bar(active_subtype: str = "all"):
    return html.Div(
        [
            html.Span(
                "🔬 Subtype:",
                style={
                    "color": "#4fc3f7",
                    "fontWeight": "700",
                    "fontSize": "0.78rem",
                    "marginRight": "10px",
                    "whiteSpace": "nowrap",
                },
            ),
            *[
                html.Button(
                    label,
                    id=f"sub-btn-{key}",
                    n_clicks=0,
                    className="ped-subtype-btn" + (" active" if key == active_subtype else ""),
                )
                for key, label in SUBTYPES
            ],
        ],
        className="ped-subtype-selector",
    )


def get_subtype_summary(active_subtype: str = "all"):
    title, description = SUBTYPE_DETAILS.get(active_subtype, SUBTYPE_DETAILS["all"])
    return html.Div(
        [
            html.Div(title, className="ped-subtype-summary-title"),
            html.Div(description, className="ped-subtype-summary-copy"),
        ],
        className="ped-subtype-summary",
    )


def get_context_bar_children(active_panel: str, active_subtype: str, netmedex_url: str = "#"):
    """Return the children list for #netmedex-context-bar.

    Pills carry data-postmsg-* attributes picked up by ped_bridge_sender.js:
      - Click a prompt pill  → fillChat   → auto-fills #chat-input-box  + switches to Chat tab
      - Click a biomarker tag → searchNodes → auto-fills #graph-node-search + switches to Network tab
    """
    subtype_title, _ = SUBTYPE_DETAILS.get(active_subtype, SUBTYPE_DETAILS["all"])
    hints = SUBTYPE_HINTS.get(active_subtype, SUBTYPE_HINTS["all"])
    biomarkers = SUBTYPE_BIOMARKERS.get(active_subtype, SUBTYPE_BIOMARKERS["all"])
    is_chat = active_panel == "chat"
    mode_icon = "💬" if is_chat else "🕸️"
    mode_label = "AI Chat" if is_chat else "Network Analysis"
    mode_note = (
        "Graph state is preserved — switch freely between Network and Chat without losing context."
        if is_chat
        else "Pre-loaded with 9,957 pediatric CNS tumor articles. Click a biomarker tag to search the graph."
    )
    return [
        # Row 1: mode + subtype context + status
        html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            f"{mode_icon} {mode_label}",
                            style={
                                "fontWeight": "700",
                                "fontSize": "0.9rem",
                                "color": "#e8f4fd",
                            },
                        ),
                        html.Span(
                            "·", style={"color": "rgba(232,244,253,0.2)", "margin": "0 10px"}
                        ),
                        html.Span(
                            "📊 Context: ",
                            style={
                                "fontSize": "0.75rem",
                                "color": "rgba(232,244,253,0.45)",
                            },
                        ),
                        html.Span(
                            subtype_title,
                            style={
                                "fontSize": "0.78rem",
                                "color": "#4fc3f7",
                                "fontWeight": "700",
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
                html.Div(
                    [
                        html.Span(
                            "🟢 Online",
                            style={
                                "fontSize": "0.72rem",
                                "color": "#81c784",
                                "marginRight": "14px",
                            },
                        ),
                        html.A(
                            "↗ 直接開啟",
                            href=netmedex_url,
                            target="_blank",
                            style={
                                "fontSize": "0.72rem",
                                "color": "#ffb74d",
                                "textDecoration": "underline",
                                "fontWeight": "600",
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
            ],
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
        ),
        # Row 2: clickable prompt pills → fillChat + switch to Chat tab
        html.Div(
            [
                html.Span(
                    "💬 Ask AI:",
                    style={
                        "fontSize": "0.7rem",
                        "color": "rgba(232,244,253,0.4)",
                        "marginRight": "8px",
                        "whiteSpace": "nowrap",
                        "flexShrink": "0",
                    },
                ),
                *[
                    html.Span(
                        hint,
                        className="ped-ctx-pill",
                        title="點擊自動帶入 AI Chat",
                        **{"data-postmsg-type": "fillChat", "data-postmsg-value": hint},
                    )
                    for hint in hints
                ],
            ],
            style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "6px"},
        ),
        # Row 3: clickable biomarker tags → searchNodes + switch to Network tab
        html.Div(
            [
                html.Span(
                    "🔍 Search Network:",
                    style={
                        "fontSize": "0.7rem",
                        "color": "rgba(232,244,253,0.4)",
                        "marginRight": "8px",
                        "whiteSpace": "nowrap",
                        "flexShrink": "0",
                    },
                ),
                *[
                    html.Span(
                        bm,
                        className="ped-ctx-tag",
                        title=f"點擊在 Network 搜尋 {bm}",
                        **{"data-postmsg-type": "searchNodes", "data-postmsg-value": bm},
                    )
                    for bm in biomarkers
                ],
            ],
            style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "5px"},
        ),
        # Row 4: mode note
        html.Div(
            mode_note,
            style={
                "fontSize": "0.66rem",
                "color": "rgba(232,244,253,0.28)",
                "fontStyle": "italic",
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  PERSISTENT LAYOUT  (panels always in DOM, shown/hidden via CSS)
# ══════════════════════════════════════════════════════════════════════════════
def serve_layout():
    return html.Div(
        [
            topnav,
            dcc.Store(id="active-panel-store", data="dashboard"),
            dcc.Store(id="active-subtype-store", data="all"),
            dcc.Location(id="app-location", refresh=False),
            # ── Panel A: Dashboard ──────────────────────────────────────────
            html.Div(
                id="panel-dashboard-wrapper",
                children=[
                    stats_bar,
                    html.Div(id="subtype-bar-slot", children=get_subtype_bar("all")),
                    html.Div(id="subtype-summary-slot", children=get_subtype_summary("all")),
                    html.Div(
                        "⚡ Network & Chat share a single engine instance — graph state is preserved when you switch tabs.",
                        style={
                            "fontSize": "0.72rem",
                            "color": "var(--PED-ORANGE)",
                            "padding": "4px 20px",
                        },
                    ),
                    html.Iframe(
                        id="iframe-dashboard",
                        src="/assets/biodashboard.html?cluster=0",
                        style={"width": "100%", "flex": "1", "border": "none", "minHeight": "0"},
                    ),
                ],
                style={**_PANEL_FLEX},
            ),
            # ── Panel B: NetMedEx shared iframe (Network + Chat) ────────────
            # This single iframe loads once and is never reloaded — switching between
            # Network and Chat only swaps the context bar text, not the iframe itself.
            html.Div(
                id="panel-netmedex-wrapper",
                children=[
                    html.Div(
                        id="netmedex-context-bar",
                        className="ped-ctx-bar",
                        children=get_context_bar_children("network", "all"),
                    ),
                    html.Iframe(
                        id="iframe-netmedex",
                        src="",  # populated by clientside callback once browser URL is known
                        style={"width": "100%", "flex": "1", "border": "none", "minHeight": "0"},
                    ),
                ],
                style={**_PANEL_HIDDEN},
            ),
        ],
        style={
            "display": "flex",
            "flexDirection": "column",
            "height": "100vh",
            "background": "#0d1117",
            "overflow": "hidden",
        },
    )


app.layout = serve_layout


# ══════════════════════════════════════════════════════════════════════════════
#  CLIENTSIDE CALLBACK — derive NetMedEx URL from the actual browser hostname
# ══════════════════════════════════════════════════════════════════════════════
app.clientside_callback(
    f"""
    function(href) {{
        if (!href) return window.dash_clientside.no_update;
        try {{
            var u = new URL(href);
            return u.protocol + '//' + u.hostname + ':{NETMEDEX_PORT}/';
        }} catch(e) {{
            return 'http://localhost:{NETMEDEX_PORT}/';
        }}
    }}
    """,
    Output("iframe-netmedex", "src"),
    Input("app-location", "href"),
    prevent_initial_call=False,
)


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
@app.callback(
    Output("active-panel-store", "data"),
    Input("nav-dashboard", "n_clicks"),
    Input("nav-network", "n_clicks"),
    Input("nav-chat", "n_clicks"),
    prevent_initial_call=False,
)
def update_active_panel(n1, n2, n3):
    triggered = callback_context.triggered_id
    if triggered == "nav-network":
        return "network"
    if triggered == "nav-chat":
        return "chat"
    return "dashboard"


@app.callback(
    Output("active-subtype-store", "data"),
    [Input(f"sub-btn-{key}", "n_clicks") for key, _ in SUBTYPES],
    State("active-subtype-store", "data"),
    prevent_initial_call=True,
)
def update_active_subtype(*args):
    current = args[-1] or "all"
    triggered = callback_context.triggered_id
    if not triggered or not str(triggered).startswith("sub-btn-"):
        return current
    return str(triggered).replace("sub-btn-", "", 1)


@app.callback(
    Output("panel-dashboard-wrapper", "style"),
    Output("panel-netmedex-wrapper", "style"),
    Output("nav-dashboard", "className"),
    Output("nav-network", "className"),
    Output("nav-chat", "className"),
    Input("active-panel-store", "data"),
    prevent_initial_call=False,
)
def toggle_panels(active):
    ACT = "ped-nav-btn active"
    INACT = "ped-nav-btn"
    if active == "network":
        return _PANEL_HIDDEN, _PANEL_FLEX, INACT, ACT, INACT
    if active == "chat":
        return _PANEL_HIDDEN, _PANEL_FLEX, INACT, INACT, ACT
    # dashboard (default)
    return _PANEL_FLEX, _PANEL_HIDDEN, ACT, INACT, INACT


@app.callback(
    Output("subtype-bar-slot", "children"),
    Output("subtype-summary-slot", "children"),
    Output("iframe-dashboard", "src"),
    Input("active-subtype-store", "data"),
    prevent_initial_call=False,
)
def update_dashboard_subtype(active_subtype):
    cluster_id = SUBTYPE_TO_CLUSTER.get(active_subtype, 0)
    return (
        get_subtype_bar(active_subtype),
        get_subtype_summary(active_subtype),
        f"/assets/biodashboard.html?cluster={cluster_id}",
    )


@app.callback(
    Output("netmedex-context-bar", "children"),
    Input("active-panel-store", "data"),
    Input("active-subtype-store", "data"),
    State("app-location", "href"),
    prevent_initial_call=False,
)
def update_context_bar(active_panel, active_subtype, current_href):
    netmedex_url = get_netmedex_url(current_href)
    return get_context_bar_children(active_panel, active_subtype, netmedex_url)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    try:
        _host_env = os.getenv("HOST", "0.0.0.0")
        import re as _re

        host = _host_env if _re.match(r"^[\d.]+$", _host_env) else "0.0.0.0"
        os.environ["HOST"] = host
        print(f"\n{'='*60}")
        print(f"  🧠  NetMedEx: Pediatric CNS Tumor Edition")
        print(f"  🌐  http://localhost:{PEDIATRIC_PORT}")
        print(f"{'='*60}\n")
        app.run(host=host, port=PEDIATRIC_PORT, debug=(os.getenv("FLASK_DEBUG") == "true"))
    finally:
        cleanup_tempdir()


if __name__ == "__main__":
    main()
