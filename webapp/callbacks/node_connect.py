"""Connect any entity of the full graph to the view's core (anchor) nodes.

For a large knowledge graph the view can start with only its core entities
(graph.graph["initial_view"] == "anchors"). A user then names an entity --
any of the full graph's nodes, not just those on screen -- and its best path
to each core node within a hop limit is added to the view. Path cost favours
fewer hops and edges backed by more papers, and penalises detours through
generic hubs (a two-hop link via "patient" or "inflammation" says little), so
the paths shown are the informative ones.
"""
from __future__ import annotations

import math
import threading
import time

import networkx as nx
from dash import Input, Output, State, no_update

from netmedex.cytoscape_js import create_cytoscape_edge, create_cytoscape_node
from netmedex.utils import generate_stable_id
from webapp.callbacks.graph_update import get_layout_config
from webapp.callbacks.graph_utils import get_anchor_nodes, load_graph_cached
from webapp.utils import SessionPathError, resolve_session_savepath

HUB_PENALTY = 0.25  # per intermediate node, times ln(1 + degree)
NEVER_INTERMEDIATE_TYPES = {"Species"}  # "patient", "mice", "human": not a mechanism
MAX_SEARCH_OPTIONS = 30
MAX_EXPAND_HISTORY = 20

_search_index: dict[int, list[tuple[str, str, str, str, int]]] = {}


def _index(G) -> list[tuple[str, str, str, str, int]]:
    """(searchable lowercase text, node id, display name, type, degree) rows."""
    key = id(G)
    if key not in _search_index:
        rows = []
        for n, d in G.nodes(data=True):
            name = str(d.get("name", n))
            texts = {name.lower(), *(str(a).lower() for a in (d.get("aliases") or ()) if a)}
            for t in texts:
                rows.append((t, n, name, str(d.get("type", "")), G.degree(n)))
        _search_index.clear()  # one graph per server process in practice
        _search_index[key] = rows
    return _search_index[key]


def search_nodes(G, text: str, limit: int = MAX_SEARCH_OPTIONS):
    """Exact name/alias match first, then prefix, then substring; well-connected first."""
    q = (text or "").strip().lower()
    if len(q) < 2:
        return []
    best: dict[str, tuple] = {}
    for t, n, name, ntype, deg in _index(G):
        if q not in t:
            continue
        rank = 0 if t == q else 1 if t.startswith(q) else 2
        key = (rank, -deg)
        if n not in best or key < best[n][0]:
            best[n] = (key, name, ntype, deg)
    ordered = sorted(best.items(), key=lambda kv: kv[1][0])[:limit]
    # Same-named entities differ by id (e.g. human/mouse/rat miR-21 are separate
    # NCBI genes), so show the id to tell them apart.
    return [
        {"label": f"{name}  ·  {ntype} {n.rsplit('_', 1)[0]}  ·  {deg} links", "value": n}
        for n, (_, name, ntype, deg) in ordered
    ]


def _edge_cost(G, root):
    """Cost of an edge on a path grown from ``root`` (a core node)."""

    def cost(u, v, data):
        support = len(data.get("relations") or {}) or 1
        c = 1.0 + 1.0 / support
        for x in (u, v):
            if x == root:
                continue
            if G.nodes[x].get("type") in NEVER_INTERMEDIATE_TYPES:
                return None  # hide edge
            c += HUB_PENALTY * math.log1p(G.degree(x))
        return c

    return cost


_core_trees: dict[tuple, dict[str, dict[str, list]]] = {}
_core_trees_lock = threading.Lock()


def core_path_trees(G, anchors: set) -> dict[str, dict[str, list]]:
    """Best path from each core node to every other node, computed once per
    graph (one Dijkstra per core node, ~5 s each on a 180k-edge graph) so that
    connecting any entity afterwards is a lookup.

    Growing the path from the core node penalises the far endpoint too, but by
    the same amount for every path ending there, so the best path to it is
    unchanged."""
    key = (id(G), frozenset(anchors))
    with _core_trees_lock:
        if key not in _core_trees:
            _core_trees.clear()
            _core_trees[key] = {
                a: nx.single_source_dijkstra(G, a, weight=_edge_cost(G, a))[1] for a in anchors
            }
        return _core_trees[key]


def warm_core_paths(graph_path: str) -> None:
    """Precompute the core path trees in the background (called on preload)."""

    def run():
        G = load_graph_cached(graph_path)
        anchors = get_anchor_nodes(G)
        if anchors:
            core_path_trees(G, anchors)

    threading.Thread(target=run, daemon=True).start()


def best_paths_to_anchors(G, source: str, anchors: set, max_hops: int):
    """Best path from ``source`` to each anchor within ``max_hops`` hops."""
    trees = core_path_trees(G, anchors)
    found = {}
    for a in anchors:
        if a == source:
            continue
        path = trees[a].get(source)
        if path and len(path) - 1 <= max_hops:
            found[a] = list(reversed(path))
    return found


def build_path_elements(G, paths: dict, shown_ids: dict, shown_pairs: set):
    """Cytoscape elements for path nodes/edges not already on screen."""
    path_nodes = {n for p in paths.values() for n in p}
    new_nodes = [n for n in path_nodes if n not in shown_ids]
    H = G.subgraph(path_nodes | set(shown_ids)).copy()
    for n, data in H.nodes(data=True):
        data["_id"] = shown_ids.get(n) or generate_stable_id(f"node_{n}")
        if isinstance(data.get("name"), str):
            data["name"] = data["name"].lower()

    # Start new nodes between the core nodes they lead to; layout refines it.
    elements = []
    for i, n in enumerate(sorted(new_nodes)):
        angle = 2 * math.pi * i / max(len(new_nodes), 1)
        H.nodes[n]["pos"] = (150 * math.cos(angle), 150 * math.sin(angle))
        elements.append(create_cytoscape_node((n, H.nodes[n]), size=30, degree=G.degree(n)))

    added_pairs = set()
    for path in paths.values():
        for u, v in zip(path, path[1:]):  # noqa: B905 -- consecutive pairs; py3.9 has no strict=
            pair = frozenset((u, v))
            if pair in shown_pairs or pair in added_pairs:
                continue
            added_pairs.add(pair)
            data = dict(H.edges[u, v])
            data["_id"] = generate_stable_id(f"edge_{u}_{v}")
            elements.append(create_cytoscape_edge((u, v, data), H, with_id=True))
    return elements, new_nodes


def callbacks(app):
    @app.callback(
        Output("connect-node-select", "options"),
        Input("connect-node-select", "search_value"),
        State("connect-node-select", "value"),
        State("connect-node-select", "options"),
        State("current-session-path", "data"),
        prevent_initial_call=True,
    )
    def suggest_nodes(search_value, value, options, session_data):
        if not search_value:
            return no_update
        try:
            G = load_graph_cached(resolve_session_savepath(session_data)["graph"])
        except (SessionPathError, OSError):
            return no_update
        found = search_nodes(G, search_value)
        selected = set(value or [])
        found_values = {o["value"] for o in found}
        # keep already-selected entities in the options so they stay displayed
        found += [o for o in (options or []) if o["value"] in selected - found_values]
        return found

    @app.callback(
        Output("cy", "elements", allow_duplicate=True),
        Output("cy", "layout", allow_duplicate=True),
        Output("connect-node-status", "children"),
        Output("expand-node-history", "data", allow_duplicate=True),
        Input("connect-node-btn", "n_clicks"),
        State("connect-node-select", "value"),
        State("connect-max-hops", "value"),
        State("cy", "elements"),
        State("current-session-path", "data"),
        State("graph-layout", "value"),
        State("fcose-node-repulsion", "value"),
        State("expand-node-history", "data"),
        prevent_initial_call=True,
    )
    def connect_node(_n, sources, max_hops, elements, session_data, layout_name,
                     repulsion, history):
        sources = [sources] if isinstance(sources, str) else (sources or [])
        if not sources:
            return no_update, no_update, "Choose one or more entities first.", no_update
        try:
            G = load_graph_cached(resolve_session_savepath(session_data)["graph"])
        except (SessionPathError, OSError) as e:
            return no_update, no_update, f"Graph unavailable: {e}", no_update
        anchors = get_anchor_nodes(G)
        if not anchors:
            return no_update, no_update, "This graph declares no core nodes.", no_update
        name = lambda n: G.nodes[n].get("name", n)  # noqa: E731
        hops = int(max_hops or 3)

        all_paths, lines = {}, []
        for src in (s for s in sources if s in G):
            paths = best_paths_to_anchors(G, src, anchors, hops)
            if not paths:
                lines.append(f"{name(src)}: no core node within {hops} hops")
                continue
            for a, p in paths.items():
                all_paths[(src, a)] = p
            direct = sorted(name(a) for a, p in paths.items() if len(p) == 2)
            lines.append(
                f"{name(src)}: reaches {len(paths)}/{len(anchors - {src})} core nodes"
                + (f" (direct: {', '.join(direct)})" if direct else "")
            )
        if not all_paths:
            return no_update, no_update, "\n".join(lines), no_update

        elements = elements or []
        shown_ids = {el["data"]["raw_node_id"]: el["data"]["id"]
                     for el in elements if "raw_node_id" in el.get("data", {})}
        raw_by_id = {v: k for k, v in shown_ids.items()}
        shown_pairs = {
            frozenset((raw_by_id.get(el["data"]["source"]), raw_by_id.get(el["data"]["target"])))
            for el in elements if "source" in el.get("data", {})
        }
        new_elements, new_nodes = build_path_elements(G, all_paths, shown_ids, shown_pairs)
        label = ", ".join(name(s) for s in sources[:3]) + ("…" if len(sources) > 3 else "")
        history = ((history or []) + [{
            "label": label,
            "nodes": [el["data"]["id"] for el in new_elements if "source" not in el["data"]],
            "edges": [el["data"]["id"] for el in new_elements if "source" in el["data"]],
        }])[-MAX_EXPAND_HISTORY:]

        all_elements = elements + new_elements
        n_nodes = sum(1 for el in all_elements if "source" not in el.get("data", {}))
        layout = get_layout_config(layout_name or "fcose", repulsion, node_count=n_nodes)
        if layout.get("name") != "preset":
            # Re-run from current positions so the new paths settle in; the
            # timestamp makes Dash see a changed layout and run it again.
            layout = {**layout, "randomize": False, "animate": True, "_run": time.time()}
        status = "\n".join([f"Added {len(new_nodes)} nodes:", *lines])
        return all_elements, layout, status, history
