from __future__ import annotations

import pickle

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder
from webapp.callbacks import graph_utils
from webapp.callbacks.node_expand import build_expansion_elements, rank_neighbors


def _node(name, ntype="Gene", pmids=("1",)):
    return {
        "name": name, "type": ntype, "mesh": "-", "pmids": set(pmids),
        "num_articles": len(pmids), "weighted_num_articles": len(pmids),
        "color": "#000", "label_color": "#000", "shape": "ELLIPSE", "aliases": {name},
    }


def _edge(pmids, conf=0.9, rel="associated_with"):
    return {
        "type": "semantic",
        "relations": {p: {rel} for p in pmids},
        "confidences": {p: {rel: conf} for p in pmids},
        "evidences": {p: {rel: "quote"} for p in pmids},
        "num_relations": len(pmids), "weighted_num_relations": len(pmids),
        "edge_weight": 1.0, "edge_width": 1.0, "npmi": 0.5,
    }


def _graph():
    G = nx.Graph()
    G.add_node("hub", **_node("Hub", "Disease", pmids=("1", "2", "3", "4")))
    G.add_node("strong", **_node("Strong"))
    G.add_node("weak", **_node("Weak"))
    G.add_node("drug", **_node("Drug", "Chemical"))
    G.add_node("shown", **_node("Shown"))
    G.add_edge("hub", "strong", **_edge(["1", "2", "3"]))
    G.add_edge("hub", "weak", **_edge(["1"]))
    G.add_edge("hub", "drug", **_edge(["1", "2"]))
    G.add_edge("hub", "shown", **_edge(["4"]))
    G.add_edge("strong", "shown", **_edge(["2", "3"]))
    G.graph["pmid_title"] = {p: f"t{p}" for p in "1234"}
    return G


def test_rank_neighbors_orders_by_paper_support_and_filters():
    G = _graph()
    assert rank_neighbors(G, "hub", {"shown"}, None, 1) == ["strong", "drug", "weak"]
    # >=2-paper filter drops single-paper edges
    assert rank_neighbors(G, "hub", {"shown"}, None, 2) == ["strong", "drug"]
    # type filter
    assert rank_neighbors(G, "hub", {"shown"}, ["Chemical"], 1) == ["drug"]
    # already-shown nodes are never re-added (so repeat clicks page onward)
    assert rank_neighbors(G, "hub", {"shown", "strong", "drug"}, None, 1) == ["weak"]


def test_expansion_links_new_nodes_to_center_and_already_shown_nodes():
    G = _graph()
    shown_ids = {"hub": "HUB_ID", "shown": "SHOWN_ID"}
    els = build_expansion_elements(G, "hub", ["strong"], shown_ids, (100.0, 50.0))
    nodes = [e for e in els if "source" not in e["data"]]
    edges = [e for e in els if "source" in e["data"]]
    assert [n["data"]["raw_node_id"] for n in nodes] == ["strong"]
    # edges reuse the on-screen ids of existing nodes
    ends = {frozenset((e["data"]["source"], e["data"]["target"])) for e in edges}
    strong_id = nodes[0]["data"]["id"]
    assert ends == {frozenset(("HUB_ID", strong_id)), frozenset(("SHOWN_ID", strong_id))}
    # edges between two already-shown nodes are not duplicated
    assert not any({e["data"]["source"], e["data"]["target"]} == {"HUB_ID", "SHOWN_ID"} for e in edges)
    # placed around the clicked node, not at the origin
    assert nodes[0]["position"] != {"x": 0, "y": 0}
    # the cached full graph is not mutated
    assert G.nodes["strong"]["name"] == "Strong"


def test_graph_cache_reuses_until_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "g.pickle"
    path.write_bytes(pickle.dumps(_graph()))
    loads = []
    real_load = graph_utils.load_graph
    monkeypatch.setattr(graph_utils, "load_graph", lambda p: loads.append(p) or real_load(p))
    graph_utils._GRAPH_CACHE.clear()
    a = graph_utils.load_graph_cached(str(path))
    b = graph_utils.load_graph_cached(str(path))
    assert a is b and len(loads) == 1
    G2 = _graph()
    G2.add_node("extra", **_node("Extra"))
    path.write_bytes(pickle.dumps(G2))
    c = graph_utils.load_graph_cached(str(path))
    assert "extra" in c and len(loads) == 2


def test_declared_anchor_nodes_override_query_matching():
    G = _graph()
    G.graph["query"] = "hub weak"
    assert graph_utils.get_anchor_nodes(G) == PubTatorGraphBuilder.find_query_anchor_nodes(G, "hub weak")
    G.graph["anchor_nodes"] = ["drug", "not-in-graph"]
    assert graph_utils.get_anchor_nodes(G) == {"drug"}


# --- Connect to core nodes -------------------------------------------------

from webapp.callbacks import node_connect  # noqa: E402


def _core_graph():
    """core1/core2 are anchors. 'x' reaches core1 via a generic hub (1 paper per
    edge, huge degree) or via a specific gene (2 hops, well supported); 'pt' is
    a Species shortcut that must never be used."""
    G = nx.Graph()
    for n, t in [("core1", "Disease"), ("core2", "Chemical"), ("x", "Gene"),
                 ("hub", "BiologicalProcess"), ("gene", "Gene"), ("pt", "Species"),
                 ("far1", "Gene"), ("far2", "Gene")]:
        G.add_node(n, **_node(n.upper(), t))
    G.nodes["x"]["aliases"] = {"X", "mir-x"}
    for i in range(200):  # make 'hub' a generic hub
        G.add_node(f"leaf{i}", **_node(f"L{i}"))
        G.add_edge("hub", f"leaf{i}", **_edge(["9"]))
    G.add_edge("x", "hub", **_edge(["1"]))
    G.add_edge("hub", "core1", **_edge(["1"]))
    G.add_edge("x", "gene", **_edge(["1", "2", "3"]))
    G.add_edge("gene", "core1", **_edge(["1", "2", "3"]))
    G.add_edge("x", "pt", **_edge(["1", "2", "3", "4"]))
    G.add_edge("pt", "core2", **_edge(["1", "2", "3", "4"]))
    G.add_edge("x", "far1", **_edge(["5"]))
    G.add_edge("far1", "far2", **_edge(["5"]))
    G.add_edge("far2", "core2", **_edge(["5"]))
    G.graph["anchor_nodes"] = ["core1", "core2"]
    return G


def test_paths_avoid_generic_hubs_and_species_and_respect_hop_limit():
    node_connect._core_trees.clear()
    G = _core_graph()
    anchors = graph_utils.get_anchor_nodes(G)
    paths = node_connect.best_paths_to_anchors(G, "x", anchors, 3)
    assert paths["core1"] == ["x", "gene", "core1"]          # not via 'hub'
    assert paths["core2"] == ["x", "far1", "far2", "core2"]  # not via Species 'pt'
    assert "core2" not in node_connect.best_paths_to_anchors(G, "x", anchors, 2)


def test_search_ranks_exact_then_prefix_and_matches_aliases():
    G = _core_graph()
    node_connect._search_index.clear()
    assert node_connect.search_nodes(G, "mir-x")[0]["value"] == "x"
    assert node_connect.search_nodes(G, "core")[0]["value"] in {"core1", "core2"}
    assert node_connect.search_nodes(G, "c") == []  # too short to search


def test_path_elements_add_only_missing_nodes_and_edges():
    node_connect._core_trees.clear()
    G = _core_graph()
    paths = node_connect.best_paths_to_anchors(G, "x", graph_utils.get_anchor_nodes(G), 3)
    shown = {"core1": "C1", "core2": "C2"}
    els, new_nodes = node_connect.build_path_elements(G, {("x", k): v for k, v in paths.items()},
                                                      shown, set())
    assert set(new_nodes) == {"x", "gene", "far1", "far2"}
    edges = [e for e in els if "source" in e["data"]]
    assert len(edges) == 5  # x-gene, gene-core1, x-far1, far1-far2, far2-core2
    assert any("C1" in (e["data"]["source"], e["data"]["target"]) for e in edges)


def test_initial_view_anchors_keeps_only_core_nodes_even_if_isolated(tmp_path):
    G = _core_graph()
    G.graph["initial_view"] = "anchors"
    path = tmp_path / "g.pickle"
    path.write_bytes(pickle.dumps(G))
    graph_utils._GRAPH_CACHE.clear()
    view = graph_utils.rebuild_graph(1, [0, 20], "html", str(path))
    assert set(view.nodes) == {"core1", "core2"}  # no edge between them, both kept


def test_node_rag_indexes_more_nodes_than_one_chromadb_batch():
    """Regression: NodeRAG used to add every node in one collection.add(), which
    ChromaDB rejects above 5,461 records -- a 36k-article graph has ~30k nodes,
    so `netmedex chat -g` crashed before answering anything."""
    from netmedex.node_rag import GraphNode, NodeRAG

    class FakeCollection:
        def __init__(self):
            self.sizes = []

        def add(self, documents, metadatas, ids):
            if len(ids) > 5461:
                raise ValueError(f"Batch size of {len(ids)} is greater than max batch size of 5461")
            self.sizes.append(len(ids))

        def count(self):
            return sum(self.sizes)

    class FakeClient:
        def __init__(self):
            self.collection = FakeCollection()

        def get_or_create_collection(self, **kwargs):
            return self.collection

        def reset(self):
            pass

    rag = NodeRAG(llm_client=None)
    rag.client = FakeClient()
    nodes = [GraphNode(node_id=f"n{i}", name=f"entity {i}", type="Gene", metadata={})
             for i in range(12_000)]
    assert rag.index_nodes(nodes) == 12_000
    assert sum(rag.client.collection.sizes) == 12_000
    assert max(rag.client.collection.sizes) <= 5461
