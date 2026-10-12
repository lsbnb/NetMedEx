"""Expand a selected node with its strongest neighbors from the full graph.

The interactive view is pruned to a few thousand edges, so on a large
knowledge graph most of a node's relations are not on screen. Expanding pulls
the next batch of the selected node's neighbors from the full session graph,
ranked by how many papers support the connecting edge, and appends them
(plus their edges to anything already shown) around the node. Repeated
clicks page through further neighbors; Undo removes the last batch.
"""
from __future__ import annotations

import math

from dash import Input, Output, State, callback_context, no_update

from netmedex.cytoscape_js import create_cytoscape_edge, create_cytoscape_node
from netmedex.utils import generate_stable_id
from webapp.callbacks.graph_utils import load_graph_cached
from webapp.utils import SessionPathError, resolve_session_savepath

MAX_EXPAND_HISTORY = 20


def _edge_support(data: dict) -> int:
    return len(data.get("relations") or {})


def _max_confidence(data: dict) -> float:
    best = 0.0
    for by_rel in (data.get("confidences") or {}).values():
        for conf in by_rel.values():
            if conf is not None and conf > best:
                best = conf
    return best


def rank_neighbors(G, node, exclude: set, node_types: list[str] | None, min_support: int):
    """Neighbors of ``node`` not yet shown, strongest connection first."""
    candidates = []
    for nb in G.neighbors(node):
        if nb in exclude:
            continue
        if node_types and G.nodes[nb].get("type") not in node_types:
            continue
        data = G.edges[node, nb]
        support = _edge_support(data)
        if support < min_support:
            continue
        candidates.append((support, _max_confidence(data), G.degree(nb), nb))
    candidates.sort(reverse=True)
    return [nb for *_, nb in candidates]


def build_expansion_elements(G, center, new_nodes, shown_ids: dict, center_pos):
    """Cytoscape elements for ``new_nodes`` and every edge linking them to the
    center, to each other, or to an already-shown node. ``shown_ids`` maps raw
    node id -> element id currently on screen (kept so edges attach to them)."""
    H = G.subgraph(set(new_nodes) | set(shown_ids)).copy()
    for n, data in H.nodes(data=True):
        data["_id"] = shown_ids.get(n) or generate_stable_id(f"node_{n}")
        if isinstance(data.get("name"), str):
            data["name"] = data["name"].lower()

    cx, cy = center_pos
    radius = 180 + 6 * len(new_nodes)
    elements = []
    for i, n in enumerate(new_nodes):
        angle = 2 * math.pi * i / max(len(new_nodes), 1)
        H.nodes[n]["pos"] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        elements.append(
            create_cytoscape_node((n, H.nodes[n]), size=30, degree=G.degree(n))
        )

    new_set = set(new_nodes)
    for u, v, data in H.edges(data=True):
        if u not in new_set and v not in new_set:
            continue  # already on screen (or deliberately pruned there)
        data = dict(data)
        data["_id"] = generate_stable_id(f"edge_{u}_{v}")
        elements.append(create_cytoscape_edge((u, v, data), H, with_id=True))
    return elements


def callbacks(app):
    @app.callback(
        Output("cy", "elements", allow_duplicate=True),
        Output("expand-node-status", "children"),
        Output("expand-node-history", "data"),
        Input("expand-node-btn", "n_clicks"),
        Input("expand-node-undo-btn", "n_clicks"),
        # Same undo from the Connect panel: Node Info (and its Undo) hides as
        # soon as the view changes and the selection is lost.
        Input("connect-undo-btn", "n_clicks"),
        State("cy", "tapNode"),
        State("cy", "elements"),
        State("current-session-path", "data"),
        State("expand-node-count", "value"),
        State("expand-node-types", "value"),
        State("expand-node-multi-pmid", "value"),
        State("expand-node-history", "data"),
        prevent_initial_call=True,
    )
    def expand_node(_expand, _undo, _connect_undo, tap_node, elements, session_data, count, node_types,
                    multi_pmid, history):
        elements = elements or []
        history = history or []
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0]

        if trigger in ("expand-node-undo-btn", "connect-undo-btn"):
            if not history:
                return no_update, "Nothing to undo.", no_update
            last = history[-1]
            drop_nodes = set(last["nodes"])
            drop_edges = set(last["edges"])
            kept = [
                el for el in elements
                if el.get("data", {}).get("id") not in drop_nodes | drop_edges
            ]
            return kept, f"Removed {len(drop_nodes)} nodes added from {last['label']}.", history[:-1]

        if not tap_node or not tap_node.get("data"):
            return no_update, "Select a node first.", no_update
        center = tap_node["data"].get("raw_node_id")
        label = tap_node["data"].get("label", center)
        try:
            graph_path = resolve_session_savepath(session_data)["graph"]
            G = load_graph_cached(graph_path)
        except (SessionPathError, OSError) as e:
            return no_update, f"Graph unavailable: {e}", no_update
        if center not in G:
            return no_update, f"{label} is not in the full graph.", no_update

        shown_ids = {
            el["data"]["raw_node_id"]: el["data"]["id"]
            for el in elements
            if "raw_node_id" in el.get("data", {})
        }
        min_support = 2 if multi_pmid else 1
        ranked = rank_neighbors(G, center, set(shown_ids), node_types or None, min_support)
        new_nodes = ranked[: int(count or 10)]
        if not new_nodes:
            hidden = sum(1 for nb in G.neighbors(center) if nb not in shown_ids)
            hint = " Try unticking the ≥2-paper filter or clearing the type filter." if hidden else ""
            return no_update, f"No more neighbors to add for {label}.{hint}", no_update

        pos = tap_node.get("position") or {}
        new_elements = build_expansion_elements(
            G, center, new_nodes, shown_ids, (pos.get("x", 0.0), pos.get("y", 0.0))
        )
        added_nodes = [el["data"]["id"] for el in new_elements if "source" not in el["data"]]
        added_edges = [el["data"]["id"] for el in new_elements if "source" in el["data"]]
        history = (history + [{"label": label, "nodes": added_nodes, "edges": added_edges}])[
            -MAX_EXPAND_HISTORY:
        ]
        remaining = len(ranked) - len(new_nodes)
        status = (
            f"Added {len(new_nodes)} neighbors of {label} "
            f"({len(added_edges)} edges); {remaining} more available."
        )
        return elements + new_elements, status, history
