"""Open a server-side prebuilt graph when the page loads.

Set NETMEDEX_PRELOAD_GRAPH=/path/to/graph.pickle to serve a fixed knowledge
graph (e.g. a 36k-article project graph, ~200 MB -- too large to push through
a browser upload). Each browser session gets its own session directory whose
graph file is a symlink to the preloaded pickle, so nothing is copied and the
original is never written: session graph files are only ever written when a
brand-new session is created by the search/upload pipeline. The file is
operator-configured, so the upload-only ALLOW_UNSAFE_GRAPH_PICKLE_UPLOAD gate
does not apply.
"""
from __future__ import annotations

import logging
import os

from dash import Input, Output, State, no_update

from webapp.callbacks.graph_utils import load_graph_cached
from webapp.callbacks.node_connect import warm_core_paths
from webapp.utils import (
    SessionPathError,
    cy_container_visibility,
    generate_session_id,
    get_data_savepath,
    make_session_token,
    resolve_session_savepath,
)

logger = logging.getLogger(__name__)


def preload_graph_path() -> str | None:
    path = os.getenv("NETMEDEX_PRELOAD_GRAPH")
    return os.path.realpath(path) if path else None


def _session_for_preload(session_data, target: str):
    """Reuse this tab's session if it already points at the preloaded graph."""
    try:
        savepath = resolve_session_savepath(session_data)
        if os.path.realpath(savepath["graph"]) == target:
            return session_data, savepath
    except (SessionPathError, OSError, TypeError):
        pass
    session_id = generate_session_id()
    savepath = get_data_savepath(session_id)
    if os.path.lexists(savepath["graph"]):
        os.remove(savepath["graph"])
    os.symlink(target, savepath["graph"])
    return make_session_token(session_id), savepath


def callbacks(app):
    @app.callback(
        Output("cy-graph-container", "style", allow_duplicate=True),
        Output("is-new-graph", "data", allow_duplicate=True),
        Output("pmid-title-dict", "data", allow_duplicate=True),
        Output("pmid-citation-dict", "data", allow_duplicate=True),
        Output("current-session-path", "data", allow_duplicate=True),
        Output("total-stats", "data", allow_duplicate=True),
        Output("sidebar-panel-toggle", "active_tab", allow_duplicate=True),
        Input("preload-graph-trigger", "data"),
        State("current-session-path", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def open_preloaded_graph(enabled, session_data):
        target = preload_graph_path()
        if not enabled or not target:
            return (no_update,) * 7
        if not os.path.exists(target):
            logger.error("NETMEDEX_PRELOAD_GRAPH not found: %s", target)
            return (no_update,) * 7

        G = load_graph_cached(target)  # also warms the cache for rebuilds/expansion
        warm_core_paths(target)  # ~1 min in the background; connecting is instant after
        token, _ = _session_for_preload(session_data, target)
        pmid_citation_dict = {
            pmid: meta.get("citation_count")
            for pmid, meta in G.graph.get("pmid_metadata", {}).items()
            if isinstance(meta, dict)
        }
        stats = {
            "articles": len(G.graph.get("pmid_title", {})),
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
        }
        logger.info("Preloaded graph %s: %s", target, stats)
        return (
            cy_container_visibility.visible,
            True,
            G.graph.get("pmid_title", {}),
            pmid_citation_dict,
            token,
            stats,
            "graph",
        )
