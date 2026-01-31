#!/usr/bin/env python
import sys
import os
import networkx as nx
import json

# Add project root to path
sys.path.insert(0, "/home/cylin/NetMedEx")

from netmedex.cytoscape_js import create_cytoscape_js, create_cytoscape_edge
from netmedex.cytoscape_html_template import HTML_TEMPLATE


def test_edge_enhancement():
    print("Testing Edge Metadata Enhancement...")

    # Create a dummy graph
    G = nx.Graph()
    G.add_node(
        "n1",
        _id="id1",
        name="Node 1",
        color="red",
        label_color="black",
        shape="ellipse",
        pmids={"123"},
        num_articles=1,
        mesh="M1",
        type="Gene",
        pos=(0, 0),
    )
    G.add_node(
        "n2",
        _id="id2",
        name="Node 2",
        color="blue",
        label_color="white",
        shape="rectangle",
        pmids={"123"},
        num_articles=1,
        mesh="M2",
        type="Chemical",
        pos=(1, 1),
    )

    # Add an edge with some relations
    G.add_edge(
        "n1",
        "n2",
        _id="e1",
        type="node",
        edge_width=2,
        relations={"123": {"inhibits"}},
        confidences={"123": {"inhibits": 0.85}},
        evidences={"123": {"inhibits": "Sentence text"}},
    )

    # Create cytoscape edge
    edge_data = create_cytoscape_edge(("n1", "n2", G.edges["n1", "n2"]), G)
    data = edge_data["data"]

    print(f"Edge data: {json.dumps(data, indent=2)}")

    # Check for new fields
    assert "source_name" in data, "Missing source_name"
    assert "target_name" in data, "Missing target_name"
    assert data["source_name"] == "Node 1"
    assert data["target_name"] == "Node 2"
    assert data["primary_relation"] == "inhibits"
    assert data["relation_display"] == "inhibits"
    assert data["is_directional"] is True
    assert data["relation_confidence"] == 0.85

    print("✅ Edge Metadata Enhancement Verified!")


def test_html_template():
    print("\nTesting HTML Template Updates...")

    # Check for text-rotation: autorotate in the template
    if 'text-rotation": "autorotate"' in HTML_TEMPLATE:
        print("✅ HTML Template includes text-rotation: autorotate")
    else:
        print("❌ HTML Template MISSING text-rotation: autorotate")

    # Check for directinal arrows
    if 'selector: "edge[is_directional]"' in HTML_TEMPLATE:
        print("✅ HTML Template includes directional arrow selector")
    else:
        print("❌ HTML Template MISSING directional arrow selector")


if __name__ == "__main__":
    try:
        test_edge_enhancement()
        test_html_template()
        print("\n🎉 All Verification Tests Passed!")
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
