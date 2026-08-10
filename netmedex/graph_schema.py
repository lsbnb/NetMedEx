"""Version markers for detecting frozen graphs that predate ontology NER."""

from __future__ import annotations

CURRENT_GRAPH_SCHEMA_VERSION = 2
CURRENT_NER_SCHEMA_VERSION = "pubtator-go-hpo-kegg-reactome-v1"


def graph_schema_status(graph) -> dict:
    graph_version = graph.graph.get("graph_schema_version")
    ner_version = graph.graph.get("ner_schema_version")
    reasons = []
    if graph_version != CURRENT_GRAPH_SCHEMA_VERSION:
        reasons.append("graph_schema_version_mismatch")
    if ner_version != CURRENT_NER_SCHEMA_VERSION:
        reasons.append("ner_schema_version_mismatch")
    return {
        "current": not reasons,
        "rebuild_required": bool(reasons),
        "graph_schema_version": graph_version,
        "ner_schema_version": ner_version,
        "expected_graph_schema_version": CURRENT_GRAPH_SCHEMA_VERSION,
        "expected_ner_schema_version": CURRENT_NER_SCHEMA_VERSION,
        "reasons": reasons,
    }
