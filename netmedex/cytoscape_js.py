from __future__ import annotations

import json
import logging
import re
from typing import Literal

import networkx as nx

from netmedex.cytoscape_html_template import HTML_TEMPLATE
from netmedex.relation_types import (
    is_directional_relation,
    get_relation_display_name,
    normalize_relation_type,
)

logger = logging.getLogger(__name__)

SHAPE_JS_MAP = {"PARALLELOGRAM": "RHOMBOID"}
COMMUNITY_NODE_PATTERN = re.compile(r"^c\d+$")


def save_as_html(G: nx.Graph, savepath: str, layout="preset"):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G, style="cyjs")
        f.write(HTML_TEMPLATE.format(cytoscape_js=json.dumps(cytoscape_js), layout=layout))


def save_as_json(G: nx.Graph, savepath: str):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G, style="dash")
        f.write(json.dumps(cytoscape_js))


def create_cytoscape_js(G: nx.Graph, style: Literal["dash", "cyjs"] = "cyjs"):
    # TODO: Check whether to set id for edges
    with_id = False

    # Filter out invalid nodes (missing required fields) to prevent export errors
    valid_nodes = []
    valid_node_ids = set()  # Track valid node IDs for edge filtering
    invalid_count = 0
    for node in G.nodes(data=True):
        node_id, node_attr = node
        if "_id" not in node_attr:
            logger.warning(f"Skipping node {node_id} during export: missing '_id' field")
            invalid_count += 1
            continue
        if "pmids" not in node_attr:
            logger.warning(f"Skipping node {node_id} during export: missing 'pmids' field")
            invalid_count += 1
            continue
        valid_nodes.append(node)
        valid_node_ids.add(node_id)  # Track this node as valid

    if invalid_count > 0:
        logger.info(f"Filtered out {invalid_count} invalid nodes during graph export")

    # Filter edges to only include those connecting valid nodes
    valid_edges = []
    filtered_edge_count = 0
    for edge in G.edges(data=True):
        node_id_1, node_id_2, edge_attr = edge
        # Only include edge if both nodes are valid
        if node_id_1 in valid_node_ids and node_id_2 in valid_node_ids:
            valid_edges.append(edge)
        else:
            filtered_edge_count += 1

    if filtered_edge_count > 0:
        logger.info(f"Filtered out {filtered_edge_count} edges connected to invalid nodes")

    nodes = [create_cytoscape_node(node) for node in valid_nodes]
    edges = [create_cytoscape_edge(edge, G, with_id) for edge in valid_edges]

    if style == "cyjs":
        elements = nodes + edges
    elif style == "dash":
        elements = {"elements": {"nodes": nodes, "edges": edges}}

    return elements


def create_cytoscape_node(node):
    def convert_shape(shape):
        return SHAPE_JS_MAP.get(shape, shape).lower()

    node_id, node_attr = node

    node_info = {
        "data": {
            "id": node_attr["_id"],
            "parent": node_attr.get("parent", None),
            "color": node_attr["color"],
            "label_color": node_attr["label_color"],
            "label": node_attr["name"],
            "shape": convert_shape(node_attr["shape"]),
            "pmids": list(node_attr["pmids"]),
            "num_articles": node_attr["num_articles"],
            "standardized_id": node_attr["mesh"],
            "node_type": node_attr["type"],
        },
        "position": {
            "x": round(node_attr["pos"][0], 3),
            "y": round(node_attr["pos"][1], 3),
        },
    }

    # Community nodes
    if COMMUNITY_NODE_PATTERN.search(node_attr["_id"]):
        node_info["classes"] = "top-center"

    return node_info


def _convert_sets_to_lists(obj):
    """Recursively convert all sets to lists for JSON serialization"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: _convert_sets_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_sets_to_lists(item) for item in obj]
    return obj


def _extract_primary_relation(edge_attr: dict) -> tuple[str, float]:
    """Extract the primary relation type from edge attributes.

    For semantic edges, finds the relation with highest confidence.
    For co-occurrence edges, returns "co-mention".

    Args:
        edge_attr: Edge attributes dictionary

    Returns:
        Tuple of (relation_type, confidence)
    """
    # Check if this is a semantic edge with confidence scores
    if "confidences" in edge_attr and edge_attr["confidences"]:
        # Find relation with highest average confidence across all PMIDs
        relation_confidences = {}

        for pmid_confidences in edge_attr["confidences"].values():
            for relation, confidence in pmid_confidences.items():
                if relation not in relation_confidences:
                    relation_confidences[relation] = []
                relation_confidences[relation].append(confidence)

        # Calculate average confidence for each relation type
        avg_confidences = {
            rel: sum(confs) / len(confs) for rel, confs in relation_confidences.items()
        }

        if avg_confidences:
            primary_relation = max(avg_confidences, key=avg_confidences.get)
            return normalize_relation_type(primary_relation), avg_confidences[primary_relation]

    # Check the relations dict for co-occurrence or BioREx edges
    if "relations" in edge_attr and edge_attr["relations"]:
        # Get all unique relation types from all PMIDs
        all_relations = set()
        for pmid, relations in edge_attr["relations"].items():
            if isinstance(relations, set):
                all_relations.update(relations)
            elif isinstance(relations, list):
                all_relations.update(relations)
            elif isinstance(relations, str):
                all_relations.add(relations)

        # Remove "co-mention" if other specific relations exist
        if len(all_relations) > 1 and "co-mention" in all_relations:
            all_relations.remove("co-mention")

        if all_relations:
            # Prefer more specific relations over generic ones
            if len(all_relations) == 1:
                return normalize_relation_type(list(all_relations)[0]), 0.5
            else:
                # Multiple relation types - pick the first non-co-mention one
                for rel in all_relations:
                    if rel != "co-mention":
                        return normalize_relation_type(rel), 0.5

    # Default to generic interaction
    return "interacts_with", 0.0


def create_cytoscape_edge(edge, G, with_id=True):
    node_id_1, node_id_2, edge_attr = edge
    if edge_attr["type"] == "community":
        pmids = list(edge_attr["pmids"])
    else:
        pmids = list(edge_attr["relations"].keys())

    # Extract primary relation type and confidence
    primary_relation, confidence = _extract_primary_relation(edge_attr)

    # Determine if this is a directional relationship
    is_directional = is_directional_relation(primary_relation)

    # Get display-friendly relation name
    relation_display = get_relation_display_name(primary_relation)

    # Create edge label with specific relation type
    edge_label = f"{G.nodes[node_id_1]['name']} ({relation_display}) {G.nodes[node_id_2]['name']}"

    # Convert relations dict (may contain sets) to JSON-serializable format
    relations = _convert_sets_to_lists(edge_attr.get("relations", {}))

    edge_info = {
        "data": {
            "source": G.nodes[node_id_1]["_id"],
            "target": G.nodes[node_id_2]["_id"],
            "label": edge_label,
            "weight": round(max(float(edge_attr["edge_width"]), 1), 1),
            "pmids": pmids,
            "edge_type": edge_attr["type"],
            "relations": relations,
            # NEW: Semantic relationship metadata
            "primary_relation": primary_relation,
            "relation_display": relation_display,
            "is_directional": is_directional,
            "relation_confidence": round(confidence, 2) if confidence > 0 else None,
            "source_name": G.nodes[node_id_1]["name"],
            "target_name": G.nodes[node_id_2]["name"],
            # Include semantic metadata for display in edge info panel
            "confidences": edge_attr.get("confidences", None),
            "evidences": edge_attr.get("evidences", None),
        }
    }

    if with_id:
        edge_info["data"]["id"] = edge_attr["_id"]

    return edge_info
