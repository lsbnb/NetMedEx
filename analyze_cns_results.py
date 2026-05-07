import json
import collections
import os

file_path = "/home/cylin/NetMedEx/brain_network/CNS_Tumors_Pediatric_Semantic.json"


def analyze_cns_cytoscape(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return

    with open(path, "r") as f:
        data = json.load(f)

    elements = data.get("elements", {})
    nodes = elements.get("nodes", [])
    edges = elements.get("edges", [])

    print(f"Total Nodes: {len(nodes)}")
    print(f"Total Edges: {len(edges)}")

    # Analyze Nodes
    node_types = collections.Counter()
    for node in nodes:
        node_data = node.get("data", {})
        node_types[node_data.get("node_type", "Unknown")] += 1

    print("\nNode Type Distribution:")
    for ntype, count in node_types.items():
        print(f"- {ntype}: {count}")

    # Analyze Edges
    top_relations = collections.Counter()
    top_entities = collections.Counter()

    for edge in edges:
        edge_data = edge.get("data", {})
        source = edge_data.get("source_name")
        target = edge_data.get("target_name")
        relation = edge_data.get("relation_display") or edge_data.get("interaction")

        if source:
            top_entities[source] += 1
        if target:
            top_entities[target] += 1

        if relation:
            top_relations[relation] += 1

    print("\nTop 15 Research Entities (by edge frequency):")
    for entity, count in top_entities.most_common(15):
        print(f"- {entity}: {count}")

    print("\nTop 10 Relation Types Identified:")
    for rel, count in top_relations.most_common(10):
        print(f"- {rel}: {count}")


if __name__ == "__main__":
    analyze_cns_cytoscape(file_path)
