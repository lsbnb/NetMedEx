from __future__ import annotations

import networkx as nx

from netmedex.graph import PubTatorGraphBuilder
from netmedex.node_merge import merge_duplicate_nodes
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


def _article(pmid, gene_id, gene_name):
    ann = [PubTatorAnnotation(pmid=pmid, start=0, end=4, name=gene_name, identifier_name=None,
                              type="Gene", mesh=gene_id),
           PubTatorAnnotation(pmid=pmid, start=10, end=13, name="HCC", identifier_name=None,
                              type="Disease", mesh="MESH:D006528")]
    return PubTatorArticle(pmid=pmid, date=None, journal=None, doi=None, title="t", abstract="a",
                           annotations=ann, relations=[])


def _build(merge):
    b = PubTatorGraphBuilder(node_type="all", merge_duplicates=merge)
    for pmid, gid in (("1", "3569"), ("2", "3569"), ("3", "16193"), ("4", "24498")):  # human, mouse, rat
        b.add_article(_article(pmid, gid, "IL-6"))
    return b.build(edge_weight_cutoff=0)


def test_species_orthologs_merge_only_when_enabled():
    off = _build(False)
    assert sum(1 for _, d in off.nodes(data=True) if d["name"] == "il-6") == 3
    on = _build(True)
    il6 = [n for n, d in on.nodes(data=True) if d["name"] == "il-6"]
    assert il6 == ["3569_Gene"]                                    # best-connected id kept
    assert set(on.nodes["3569_Gene"]["merged_ids"]) == {"16193_Gene", "24498_Gene"}
    assert on.nodes["3569_Gene"]["num_articles"] == 4
    assert on.edges["3569_Gene", "MESH:D006528_Disease"]["num_relations"] == 4
    assert on.graph["merge_duplicates"]["nodes_removed"] == 2


def _node(name, ntype, mesh, aliases=()):
    return {"name": name, "type": ntype, "mesh": mesh, "pmids": {"1"}, "aliases": {name, *aliases}}


def test_rules_for_concepts_fragments_and_gene_aliases():
    G = nx.Graph()
    G.add_node("GO:fer", **_node("ferroptosis", "BiologicalProcess", "GO:0097707"))
    G.add_node("KEGG:fer", **_node("ferroptosis", "Pathway", "map04216"))
    G.add_node("fer_d", **_node("ferroptosis", "Disease", "-"))          # mis-typed fragment
    G.add_node("ins_g", **_node("insulin", "Gene", "3630"))
    G.add_node("ins_c", **_node("insulin", "Chemical", "MESH:D007328"))  # gene vs drug: apart
    G.add_node("il6", **_node("il-6", "Gene", "3569", ["interleukin 6"]))
    G.add_node("il6b", **_node("interleukin 6", "Gene", "99", ["il-6"]))  # mutual aliases
    G.add_node("smad2", **_node("smad2", "Gene", "4087", ["smad4"]))     # one-way: noise
    G.add_node("smad4", **_node("smad4", "Gene", "4089"))
    G.add_node("m223", **_node("mir-223", "Gene", "407008", ["mir-22-3p"]))
    G.add_node("m22", **_node("mir-22-3p", "Gene", "100314060", ["mir-223"]))
    G.add_edge("GO:fer", "il6", relations={"1": {"promotes"}})
    stats = merge_duplicate_nodes(G)
    assert {d["name"] for _, d in G.nodes(data=True) if d["name"] == "ferroptosis"} == {"ferroptosis"}
    assert sum(1 for _, d in G.nodes(data=True) if d["name"] == "ferroptosis") == 1
    assert "ins_g" in G and "ins_c" in G
    assert "il6b" not in G and "interleukin 6" in G.nodes["il6"]["aliases"]
    assert {"smad2", "smad4", "m223", "m22"} <= set(G.nodes)
    assert stats == {"name_groups": 1, "gene_alias_pairs": 1, "nodes_removed": 3}
