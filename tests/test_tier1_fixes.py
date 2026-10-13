from __future__ import annotations

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever, _contains_word
from netmedex.pubtator_data import PubTatorAnnotation
from netmedex.pubtator_graph_data import NonMeshNodeCollection


def test_whole_word_matching_allows_plurals_but_not_embedded_words():
    assert _contains_word("how do exosomes act", "exosome")
    assert _contains_word("role of ast in liver injury", "ast")
    assert not _contains_word("contrast-enhanced imaging", "ast")
    assert not _contains_word("salt intake", "alt")


def test_retriever_ignores_one_and_two_letter_names():
    G = nx.Graph()
    G.add_node("noise", name="a", type="Chemical", aliases=set())
    G.add_node("ast", name="ast", type="Gene", aliases=set())
    G.add_edge("noise", "ast")
    r = GraphRetriever(G)
    assert r.find_relevant_nodes("Is AST a marker of liver injury?") == ["ast"]
    assert r.find_relevant_nodes("a contrast study") == []


def test_same_name_different_type_tie_is_deterministic():
    def collection(order):
        c = NonMeshNodeCollection()
        for t in order:
            c.add_node(PubTatorAnnotation(pmid="1", start=0, end=1, name="Exo",
                                          identifier_name=None, type=t, mesh="-"))
        return set(c.to_clean_pubtator_nodes())
    # one mention each (a tie): the kept node must not depend on insertion/hash order
    assert collection(["Chemical", "Disease"]) == collection(["Disease", "Chemical"])


def test_display_name_is_the_most_used_mention_and_cutoff_counts_papers():
    from netmedex.pubtator_data import PubTatorArticle

    builder = PubTatorGraphBuilder(node_type="all")
    mentions = ["sora", "sorafenib", "sorafenib", "sorafenib"]
    for i, name in enumerate(mentions):
        ann = [PubTatorAnnotation(pmid=str(i), start=0, end=4, name=name, identifier_name=None,
                                  type="Chemical", mesh="MESH:D000077157"),
               PubTatorAnnotation(pmid=str(i), start=10, end=13, name="HCC", identifier_name=None,
                                  type="Disease", mesh="MESH:D006528")]
        builder.add_article(PubTatorArticle(pmid=str(i), date=None, journal=None, doi=None,
                                            title="t", abstract="a", annotations=ann, relations=[]))
    G = builder.build(edge_weight_cutoff=0)
    assert G.nodes["MESH:D000077157_Chemical"]["name"] == "sorafenib"   # was "sora" (first seen)
    assert "sora" in G.nodes["MESH:D000077157_Chemical"]["aliases"]
    edge = G.edges["MESH:D000077157_Chemical", "MESH:D006528_Disease"]
    assert edge["weighted_num_relations"] == 4
    H = G.copy()
    PubTatorGraphBuilder._remove_edges_by_weight(H, [5, 20])   # needs 5 papers: removed
    assert H.number_of_edges() == 0
    PubTatorGraphBuilder._remove_edges_by_weight(G, [4, 20])   # 4 papers: kept
    assert G.number_of_edges() == 1
