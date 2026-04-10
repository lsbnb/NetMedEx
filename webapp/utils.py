from __future__ import annotations

import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

BASE_SAVEDIR = (
    Path(__file__).resolve().parents[1] / "webapp-temp"
    if (base_savedir := os.getenv("SAVEDIR")) is None
    else Path(base_savedir)
)
MAX_ARTICLES = 1000
DATA_FILENAME = {
    "graph": "G.pkl",
    "xgmml": "output.xgmml",
    "html": "output.html",
    "pubtator": "output.pubtator",
    "biocjson": "output.biocjson",
    "edge_info": "output.csv",
    "ris": "citations.ris",
}
visibility = SimpleNamespace(visible={"visibility": "visible"}, hidden={"visibility": "hidden"})
display = SimpleNamespace(
    block={"display": "block"},
    none={"display": "none"},
    hidden_panel={
        "position": "absolute",
        "top": "-9999px",
        "left": "-9999px",
        "visibility": "hidden",
        "height": "0px",
        "width": "100%",
        "overflow": "hidden",
    },
)

CYTO_STYLESHEET = [
    {
        "selector": "core",
        "style": {
            "selection-box-color": "#FF0000",
            "selection-box-border-color": "#FF0000",
            "selection-box-opacity": "0.2",
        },
    },
    {
        "selector": "node",
        "style": {
            "text-valign": "center",
            "label": "data(label)",
            "shape": "data(shape)",
            "color": "data(label_color)",
            "background-color": "data(color)",
            "width": "data(node_size)",
            "height": "data(node_size)",
        },
    },
    {
        "selector": ":parent",
        "style": {
            "background-opacity": 0.3,
        },
    },
    {
        "selector": "edge",
        "style": {
            "width": "data(weight)",
            "curve-style": "haystack",
            "haystack-radius": 0,
            "label": "data(relation_display)",
            "font-size": "11px",
            "font-weight": "bold",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.8,
            "text-background-padding": "3px",
            "color": "#000000",
            "text-rotation": "autorotate",
        },
    },
    {
        "selector": "edge[is_directional]",
        "style": {
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#999",
            "arrow-scale": 1.2,
        },
    },
    {
        "selector": ".top-center",
        "style": {
            "text-valign": "top",
            "text-halign": "center",
            "font-size": "36px",
            "font-weight": "bold",
            "text-outline-color": "#ffffff",
            "text-outline-width": "2px",
            "text-outline-opacity": "0.8",
        },
    },
    {
        "selector": "edge[primary_relation = 'activates'], edge[primary_relation = 'increases'], edge[primary_relation = 'upregulates'], edge[primary_relation = 'induces'], edge[primary_relation = 'enhances'], edge[primary_relation = 'promotes'], edge[primary_relation = 'stimulates'], edge[primary_relation = 'treats'], edge[primary_relation = 'prevents'], edge[primary_relation = 'cures'], edge[primary_relation = 'ameliorates']",
        "style": {
            "line-color": "#28a745",
            "target-arrow-color": "#28a745",
            "source-arrow-color": "#28a745",
        },
    },
    {
        "selector": "edge[primary_relation = 'inhibits'], edge[primary_relation = 'decreases'], edge[primary_relation = 'downregulates'], edge[primary_relation = 'suppresses'], edge[primary_relation = 'represses'], edge[primary_relation = 'blocks'], edge[primary_relation = 'causes'], edge[primary_relation = 'triggers']",
        "style": {
            "line-color": "#dc3545",
            "target-arrow-color": "#dc3545",
            "source-arrow-color": "#dc3545",
        },
    },
    {
        "selector": ":selected",
        "style": {
            "overlay-color": "#FF0000",
            "overlay-opacity": 0.2,
            "overlay-padding": "5px",
        },
    },
]


def generate_session_id():
    return str(uuid4())


def get_data_savepath(session_id: str):
    savepath = {}
    savedir = BASE_SAVEDIR / session_id
    savedir.mkdir(parents=True, exist_ok=True)
    for file, filepath in DATA_FILENAME.items():
        savepath[file] = str(savedir / filepath)
    return savepath


def cleanup_tempdir():
    """
    Perform surgical cleanup of the temporary directory.
    Attempts to remove session folders older than 24 hours to preserve
    active sessions across server restarts.
    """
    # Only cleanup if we are NOT in debug/reloader mode.
    if os.getenv("FLASK_DEBUG") == "true":
        return

    if not BASE_SAVEDIR.exists():
        return

    import time

    current_time = time.time()
    retention_seconds = 24 * 3600  # 24 hours

    try:
        # If SAVEDIR is set explicitly, we assume managed persistence and skip auto-cleanup
        if os.getenv("SAVEDIR") is not None:
            return

        for item in BASE_SAVEDIR.iterdir():
            if item.is_dir():
                # Check modification time of the directory
                mtime = item.stat().st_mtime
                if (current_time - mtime) > retention_seconds:
                    print(f"Cleaning up old session directory: {item.name}")
                    shutil.rmtree(item, ignore_errors=True)
            elif item.is_file() and item.name != ".gitignore":
                # Remove loose files in tempdir
                item.unlink(missing_ok=True)

    except Exception as e:
        print(f"Warning during tempdir cleanup: {e}")
