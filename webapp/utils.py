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
    "edge_info": "output.csv",
}
visibility = SimpleNamespace(visible={"visibility": "visible"}, hidden={"visibility": "hidden"})
display = SimpleNamespace(block={"display": "block"}, none={"display": "none"})

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
    if os.getenv("SAVEDIR") is None:
        shutil.rmtree(BASE_SAVEDIR, ignore_errors=True)
