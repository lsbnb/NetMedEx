from __future__ import annotations

from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_graph_data import PubTatorNode


def _builder() -> PubTatorGraphBuilder:
    return PubTatorGraphBuilder(node_type="all", edge_method="co-occurrence")


def test_numeric_only_node_name_is_rejected():
    """PubTator3's upstream NER occasionally annotates a bare numeric fragment (a truncated
    identifier or dosage figure) as an entity mention. A purely numeric string is never a valid
    biomedical entity display name, so it must not surface as a graph node."""
    builder = _builder()
    nodes = {
        "MESH:D000409_Chemical": PubTatorNode(
            mesh="D000409", type="Chemical", name="0409", pmid="12345"
        ),
        "MESH:D002_Gene": PubTatorNode(mesh="D002", type="Gene", name="runx2", pmid="12345"),
    }

    builder._add_nodes(nodes)

    assert "MESH:D002_Gene" in builder.graph.nodes
    assert "MESH:D000409_Chemical" not in builder.graph.nodes


def test_leading_zero_numeric_name_is_rejected():
    builder = _builder()
    nodes = {
        "X_Chemical": PubTatorNode(mesh="X", type="Chemical", name="  0409  ", pmid="1"),
    }

    builder._add_nodes(nodes)

    assert "X_Chemical" not in builder.graph.nodes


def test_alphanumeric_gene_symbol_is_kept():
    """A real gene symbol like 'CDK2' or an isoform label like 'IL-6' must not be caught by the
    numeric-only filter -- only names with *no* letters at all should be rejected."""
    builder = _builder()
    nodes = {
        "MESH:D1_Gene": PubTatorNode(mesh="D1", type="Gene", name="CDK2", pmid="1"),
        "MESH:D2_Chemical": PubTatorNode(mesh="D2", type="Chemical", name="IL-6", pmid="1"),
    }

    builder._add_nodes(nodes)

    assert "MESH:D1_Gene" in builder.graph.nodes
    assert "MESH:D2_Chemical" in builder.graph.nodes
