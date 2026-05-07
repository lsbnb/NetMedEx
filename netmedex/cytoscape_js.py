from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
import re
import time
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
    # Load vendor JS files for embedding
    vendor_dir = Path(__file__).parent / "vendor"
    js_contents = {}
    js_files = {
        "cytoscape_js_lib": "cytoscape.min.js",
        "layout_base_js": "layout-base.js",
        "cose_base_js": "cose-base.js",
        "fcose_js": "cytoscape-fcose.js",
    }

    for key, filename in js_files.items():
        filepath = vendor_dir / filename
        if filepath.exists():
            with open(filepath, encoding="utf-8") as f:
                js_contents[key] = f.read()
        else:
            logger.warning(
                f"Vendor JS file not found: {filepath}. HTML export may rely on CDNs if template defaults are kept."
            )
            js_contents[key] = ""  # Fallback logic handled in template or keep as empty

    with open(savepath, "w", encoding="utf-8") as f:
        cytoscape_js = create_cytoscape_js(G, style="cyjs")
        f.write(
            HTML_TEMPLATE.format(
                cytoscape_js=json.dumps(cytoscape_js), layout=layout, **js_contents
            )
        )


def save_as_json(G: nx.Graph, savepath: str):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G, style="dash")
        f.write(json.dumps(cytoscape_js))


def create_cytoscape_js(G: nx.Graph, style: Literal["dash", "cyjs"] = "cyjs"):
    """
    Creates Cytoscape JSON with paranoid ID validation and REAL-TIME PRINTING for debugging.
    """
    start_t = time.time()
    print(f"\n>>> [CYJS-DEBUG] Starting export at {start_t}")

    # Track exactly which node IDs (UUIDs) we are sending to the browser
    final_node_uuids = set()
    valid_nodes_for_export = []

    skipped_missing_id = 0
    skipped_duplicates = 0

    # 1. Collect and Validate Nodes
    for node_id, node_attr in G.nodes(data=True):
        uuid = node_attr.get("_id")
        if not uuid:
            print(f">>> [CYJS-DEBUG] Skipping node {node_id}: No '_id' attribute.")
            skipped_missing_id += 1
            continue

        if "pmids" not in node_attr:
            print(f">>> [CYJS-DEBUG] Skipping node {node_id}: No 'pmids' attribute.")
            skipped_missing_id += 1
            continue

        if uuid in final_node_uuids:
            skipped_duplicates += 1
            continue

        final_node_uuids.add(uuid)
        valid_nodes_for_export.append((node_id, node_attr))

    # 2. Collect and Filter Edges
    valid_edges_for_export = []
    skipped_missing_source = 0
    skipped_missing_target = 0

    for u, v, edge_attr in G.edges(data=True):
        source_uuid = G.nodes[u].get("_id")
        target_uuid = G.nodes[v].get("_id")

        if not source_uuid or source_uuid not in final_node_uuids:
            skipped_missing_source += 1
            # print(f">>> [CYJS-DEBUG] Edge filtered: source {source_uuid} not in nodes.")
            continue

        if not target_uuid or target_uuid not in final_node_uuids:
            skipped_missing_target += 1
            # print(f">>> [CYJS-DEBUG] Edge filtered: target {target_uuid} not in nodes.")
            continue

        valid_edges_for_export.append((u, v, edge_attr))

    # Calculate edge type counts for debugging
    edge_types = defaultdict(int)
    for _, _, d in valid_edges_for_export:
        edge_types[d.get("type", "unknown")] += 1

    print(
        f">>> [CYJS-DEBUG] Summary: Nodes({len(valid_nodes_for_export)}), Edges({len(valid_edges_for_export)}). "
        f"Types: {dict(edge_types)}. "
        f"Filtered: MissingID={skipped_missing_id}, Dups={skipped_duplicates}, "
        f"NoSource={skipped_missing_source}, NoTarget={skipped_missing_target}"
    )

    # Calculate node degrees for sizing
    node_degrees = {node_id: G.degree(node_id) for node_id, _ in valid_nodes_for_export}
    if node_degrees:
        min_deg = min(node_degrees.values())
        max_deg = max(node_degrees.values())
    else:
        min_deg = max_deg = 0

    MIN_SIZE, MAX_SIZE = 25, 65

    def get_node_size(nid):
        deg = node_degrees.get(nid, 0)
        if max_deg == min_deg:
            return MIN_SIZE
        norm = (deg - min_deg) / (max_deg - min_deg)
        return MIN_SIZE + (norm * (MAX_SIZE - MIN_SIZE))

    # Convert to Cytoscape format
    nodes_json = [
        create_cytoscape_node(
            (nid, attr), size=get_node_size(nid), degree=node_degrees.get(nid, 0)
        )
        for nid, attr in valid_nodes_for_export
    ]
    edges_json = [
        create_cytoscape_edge((u, v, attr), G, with_id=True)
        for u, v, attr in valid_edges_for_export
    ]

    print(f">>> [CYJS-DEBUG] Export finished in {time.time() - start_t:.4f}s")

    if style == "cyjs":
        return nodes_json + edges_json
    return {"elements": {"nodes": nodes_json, "edges": edges_json}}


def create_cytoscape_node(node, size=25, degree=0):
    def convert_shape(shape):
        return SHAPE_JS_MAP.get(shape, shape).lower()

    node_id, node_attr = node
    is_community_node = bool(COMMUNITY_NODE_PATTERN.search(str(node_id)))
    node_type = "Community" if is_community_node else node_attr["type"]
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
            "node_type": node_type,
            "is_community": is_community_node,
            "node_size": size,
            "degree": degree,
        },
        "position": {
            "x": round(node_attr["pos"][0], 3) if "pos" in node_attr else 0,
            "y": round(node_attr["pos"][1], 3) if "pos" in node_attr else 0,
        },
    }

    if COMMUNITY_NODE_PATTERN.search(str(node_id)):
        node_info["classes"] = "top-center"

    return node_info


def _convert_sets_to_lists(obj):
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: _convert_sets_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_sets_to_lists(item) for item in obj]
    return obj


def _extract_primary_relation(edge_attr: dict) -> tuple[str, float]:
    if "confidences" in edge_attr and edge_attr["confidences"]:
        relation_confidences = {}
        for pmid_confidences in edge_attr["confidences"].values():
            for relation, confidence in pmid_confidences.items():
                if relation not in relation_confidences:
                    relation_confidences[relation] = []
                relation_confidences[relation].append(confidence)
        avg_confidences = {
            rel: sum(confs) / len(confs) for rel, confs in relation_confidences.items()
        }
        if avg_confidences:
            primary_relation = max(avg_confidences, key=avg_confidences.get)
            return normalize_relation_type(primary_relation), avg_confidences[primary_relation]

    if "relations" in edge_attr and edge_attr["relations"]:
        all_relations = set()
        for relations in edge_attr["relations"].values():
            if isinstance(relations, (set, list)):
                all_relations.update(relations)
            elif isinstance(relations, str):
                all_relations.add(relations)

        if len(all_relations) > 1 and "co-mention" in all_relations:
            all_relations.remove("co-mention")

        if all_relations:
            for rel in all_relations:
                if rel != "co-mention":
                    return normalize_relation_type(rel), 0.5
            return normalize_relation_type(list(all_relations)[0]), 0.5

    return "interacts_with", 0.0


def create_cytoscape_edge(edge, G, with_id=True):
    node_id_1, node_id_2, edge_attr = edge
    if edge_attr["type"] == "community":
        pmids = list(edge_attr["pmids"])
    else:
        pmids = list(edge_attr["relations"].keys())

    primary_relation, confidence = _extract_primary_relation(edge_attr)
    is_directional = is_directional_relation(primary_relation)
    relation_display = get_relation_display_name(primary_relation)

    source_id = G.nodes[node_id_1]["_id"]
    target_id = G.nodes[node_id_2]["_id"]
    source_name = G.nodes[node_id_1]["name"]
    target_name = G.nodes[node_id_2]["name"]

    if "source_id" in edge_attr:
        if edge_attr["source_id"] != node_id_1:
            source_id, target_id = target_id, source_id
            source_name, target_name = target_name, source_name

    relations = _convert_sets_to_lists(edge_attr.get("relations", {}))

    # Robust edge type resolution:
    # - keep explicit types as-is
    # - infer semantic when confidence metadata exists
    # - default to "node" for unknown/legacy values
    raw_edge_type = edge_attr.get("type")
    if raw_edge_type in {"node", "semantic", "community"}:
        resolved_edge_type = raw_edge_type
    else:
        resolved_edge_type = "semantic" if edge_attr.get("confidences") else "node"

    edge_data = {
        "source": source_id,
        "target": target_id,
        "label": relation_display,
        "weight": round(max(float(edge_attr["edge_width"] or 0), 1), 1),
        "pmids": pmids,
        "edge_type": resolved_edge_type,
        "relations": relations,
        "primary_relation": primary_relation,
        "relation_display": relation_display,
        "relation_confidence": round(confidence, 2) if confidence > 0 else None,
        "source_name": source_name,
        "target_name": target_name,
        "confidences": edge_attr.get("confidences", None),
        "evidences": edge_attr.get("evidences", None),
    }

    if is_directional:
        edge_data["is_directional"] = True

    edge_info = {"data": edge_data}
    if with_id:
        # NOTE: Using a timestamp-based suffix here could force a redraw, but let's stick to stable IDs first
        # and just ensure they are valid.
        edge_info["data"]["id"] = edge_attr["_id"]

    return edge_info
