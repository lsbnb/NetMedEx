import networkx as nx
from netmedex.graph_rag import GraphRetriever


def test_graph_retriever():
    # Setup sample graph
    G = nx.Graph()
    G.add_node("1", name="GeneA", type="Gene")
    G.add_node("2", name="GeneB", type="Gene")
    G.add_node("3", name="DrugC", type="Chemical")

    G.add_edge("1", "2", relations={"123": {"activates"}}, edge_weight=0.9)
    G.add_edge("2", "3", relations={"124": {"inhibits"}}, edge_weight=0.8)

    retriever = GraphRetriever(G)

    # Test 1: Node finding
    query = "How does DrugC affect GeneA?"
    nodes = retriever.find_relevant_nodes(query)
    print(f"Found nodes: {nodes}")
    assert "1" in nodes  # GeneA
    assert "3" in nodes  # DrugC

    # Test 2: Context retrieval
    context = retriever.get_subgraph_context(nodes)
    print("\nGenerated Context:")
    print(context)

    assert "GeneA" in context
    assert "DrugC" in context
    assert "GeneB" in context  # Should be found in path
    assert "activates" in context
    assert "inhibits" in context


if __name__ == "__main__":
    test_graph_retriever()
    print("\n✅ GraphRetriever Text Passed!")
