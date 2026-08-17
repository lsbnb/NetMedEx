#!/usr/bin/env python3
"""Reconstruct real NetMedEx graph edges/2-hop paths and build an edge_ratings worksheet.

The frozen formal-v1-gpt-5.6-terra run only persisted edge_count/path_count summaries per
question, not the actual edge tuples -- this rebuilds the graph from each question's already-saved
corpus.pubtator (no PubTator network refetch) using the same PubTatorGraphBuilder/GraphRetriever
parameters as run_formal_50.py, then extracts the real (source, target, relation, supporting PMIDs)
edges that appear on 2-hop retrieval paths.

edge_method="semantic" calls the same LLM (OpenAI gpt-5.6-terra) used in the original run to derive
semantic edges -- this is not free, unlike a co-occurrence rebuild.

Unlike hypothesis_ratings, this has no traditional_rag counterpart -- Traditional RAG has no graph,
so this worksheet audits NetMedEx's own graph-edge quality rather than a head-to-head comparison.
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.node_rag import GraphNode, NodeRAG
from netmedex.pubtator_parser import PubTatorIO
from webapp.llm import LLMClient

WORKSHEET_FIELDS = [
    "question_id",
    "domain",
    "question",
    "edge_id",
    "source",
    "target",
    "relation_type",
    "supporting_titles",
    "supporting_abstracts",
    "evidence_quotes",
    "pmids",
    "min_hop_count",
    "max_path_score",
    "rater_id",
    "biologically_meaningful",
    "relation_type_correct",
    "notes",
]


def read_questions(path: Path, question_ids: list[str]) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {row["question_id"]: row for row in csv.DictReader(handle)}
    missing = [qid for qid in question_ids if qid not in rows]
    if missing:
        raise ValueError(f"Question IDs not found in {path}: {missing}")
    return {qid: rows[qid] for qid in question_ids}


def init_llm(model: str) -> LLMClient:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    client = LLMClient()
    client.initialize_client(
        provider="openai",
        api_key=api_key,
        base_url="https://api.openai.com/v1",
        model=model,
    )
    return client


def init_verifier_llm(provider: str, model: str | None) -> LLMClient:
    """Build a verifier client, independent from the primary extraction client -- verifying a
    candidate edge against its evidence quote is a smaller task than the original extraction, so
    a different model/provider is more likely to catch an error than the same model re-asked.

    initialize_client() only overrides base_url when one is explicitly passed -- it does not
    derive the right endpoint from `provider` on its own -- so each provider's base_url must be
    passed explicitly here (same constants webapp.llm.initialize_llm_client_from_settings uses).
    """
    from webapp.llm import ANTHROPIC_BASE_URL, GEMINI_OPENAI_BASE_URL, OPENAI_BASE_URL

    client = LLMClient()
    if provider == "google":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY is missing for the verifier")
        client.initialize_client(
            provider="google",
            api_key=api_key,
            base_url=GEMINI_OPENAI_BASE_URL,
            model=model or "gemini-3.1-pro-preview",
        )
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is missing for the verifier")
        client.initialize_client(
            provider="anthropic", api_key=api_key, base_url=ANTHROPIC_BASE_URL, model=model or "claude-opus-5"
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing for the verifier")
        client.initialize_client(
            provider="openai",
            api_key=api_key,
            base_url=OPENAI_BASE_URL,
            model=model or "gpt-5.6-sol",
        )
    return client


def build_node_rag(llm: LLMClient, graph, collection_name: str) -> NodeRAG | None:
    """Build a semantic node index, mirroring netmedex/chat_bridge.py's construction pattern.

    Uses ChromaDB's bundled local embedding model (not an LLM API call), so this is cheap. Falls
    back to None on any failure, same as chat_bridge.py -- substring-only matching still runs.
    """
    try:
        node_rag = NodeRAG(llm, collection_name=collection_name)
        graph_nodes = [
            GraphNode(
                node_id=str(node_id),
                name=str(data.get("name", node_id)),
                type=str(data.get("type", "Entity")),
                metadata=data,
            )
            for node_id, data in graph.nodes(data=True)
        ]
        node_rag.index_nodes(graph_nodes)
        return node_rag
    except Exception as exc:
        print(f"  NodeRAG indexing failed, falling back to substring-only matching: {exc}")
        return None


def extract_edges_for_question(
    corpus_path: Path,
    question_text: str,
    llm: LLMClient,
    semantic_threshold: float,
    max_hops: int,
    top_k_paths: int,
    question_id: str,
    use_node_rag: bool = True,
    verify_relations: bool = False,
    verifier_llm: LLMClient | None = None,
) -> list[dict[str, Any]]:
    collection = PubTatorIO.parse(corpus_path)
    title_by_pmid = {str(a.pmid): str(a.title or "") for a in collection.articles}
    abstract_by_pmid = {str(a.pmid): str(a.abstract or "") for a in collection.articles}

    graph_builder = PubTatorGraphBuilder(
        node_type="all",
        edge_method="semantic",
        llm_client=llm,
        semantic_threshold=semantic_threshold,
        verify_relations=verify_relations,
        verifier_llm_client=verifier_llm,
    )
    graph_builder.add_collection(collection)
    graph = graph_builder.build(
        pmid_weights=None, weighting_method="freq", edge_weight_cutoff=1, community=False, max_edges=0
    )

    node_rag = (
        build_node_rag(llm, graph, collection_name=f"edge_ratings_{question_id.lower()}")
        if use_node_rag
        else None
    )
    retriever = GraphRetriever(graph, node_rag=node_rag)
    nodes = retriever.find_relevant_nodes(question_text)
    if not nodes:
        return []
    _context, paths = retriever.get_subgraph_context_with_paths(
        nodes, query=question_text, max_hops=max_hops
    )

    # Dedupe hops across all returned paths -- the same (source, target, relation) edge can appear
    # in multiple candidate paths. Keep the smallest hop_count and largest score seen for it.
    by_edge: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in paths[:top_k_paths]:
        names = path.get("names", [])
        relations = path.get("relations", [])
        edge_pmids = path.get("edge_pmids", [])
        node_ids = path.get("node_ids", [])
        hop_count = path.get("hop_count", len(names) - 1)
        score = path.get("score", 0.0)
        for i, relation in enumerate(relations):
            if i + 1 >= len(names):
                continue
            source, target = names[i], names[i + 1]
            pmids = sorted(set(map(str, edge_pmids[i] if i < len(edge_pmids) else [])))
            key = (source, target, relation)
            entry = by_edge.setdefault(
                key,
                {
                    "source": source,
                    "target": target,
                    "relation_type": relation,
                    "pmids": set(),
                    "evidence_quotes": set(),
                    "min_hop_count": hop_count,
                    "max_path_score": score,
                },
            )
            entry["pmids"].update(pmids)
            if i + 1 < len(node_ids) and graph.has_edge(node_ids[i], node_ids[i + 1]):
                edge_data = graph.edges[node_ids[i], node_ids[i + 1]]
                evidence_by_pmid = edge_data.get("evidences", {})
                for pmid in pmids:
                    relation_evidence = evidence_by_pmid.get(pmid, {})
                    quote = relation_evidence.get(relation)
                    if quote:
                        entry["evidence_quotes"].add(f"PMID {pmid}: {quote}")
            entry["min_hop_count"] = min(entry["min_hop_count"], hop_count)
            entry["max_path_score"] = max(entry["max_path_score"], score)

    edges = []
    for entry in by_edge.values():
        pmids = sorted(entry["pmids"])
        titles = "; ".join(title_by_pmid.get(pmid, f"[title unavailable for PMID {pmid}]") for pmid in pmids)
        abstracts = "\n\n".join(
            f"PMID {pmid}: {abstract_by_pmid.get(pmid, '[abstract unavailable]')}" for pmid in pmids
        )
        edges.append(
            {
                "source": entry["source"],
                "target": entry["target"],
                "relation_type": entry["relation_type"],
                "pmids": ";".join(pmids),
                "supporting_titles": titles,
                "supporting_abstracts": abstracts,
                "evidence_quotes": "\n".join(sorted(entry["evidence_quotes"])),
                "min_hop_count": entry["min_hop_count"],
                "max_path_score": round(entry["max_path_score"], 4),
            }
        )
    edges.sort(key=lambda e: (e["min_hop_count"], -e["max_path_score"]))
    return edges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions", type=Path, default=Path("evaluation/formal/questions.csv")
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/questions"),
    )
    parser.add_argument("--output", type=Path, default=Path("evaluation/formal/edge_ratings_worksheet.csv"))
    parser.add_argument(
        "--question-ids",
        nargs="+",
        default=[
            "Q001", "Q004", "Q008", "Q011", "Q015", "Q016", "Q018", "Q022", "Q023", "Q025",
            "Q028", "Q029", "Q031", "Q034", "Q035", "Q037", "Q040", "Q048", "Q050",
        ],
        help="Defaults to the 19-question hypothesis/two_hop_path + mechanism stratum.",
    )
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--semantic-threshold", type=float, default=0.5)
    parser.add_argument("--max-hops", type=int, default=2)
    parser.add_argument("--top-k-paths", type=int, default=20)
    parser.add_argument(
        "--no-node-rag",
        action="store_true",
        help="Disable the semantic NodeRAG fallback and use substring-only matching (old behavior).",
    )
    parser.add_argument(
        "--verify-relations",
        action="store_true",
        help="Enable the v1.4 relation-direction verification pass (second LLM call per article).",
    )
    parser.add_argument(
        "--verifier-provider",
        default="google",
        choices=["openai", "google", "anthropic"],
        help="Provider for the verifier LLM. Defaults to google (Gemini) -- a different provider "
        "than the primary --model (openai) so verification is by an independent model.",
    )
    parser.add_argument("--verifier-model", default=None)
    args = parser.parse_args()

    load_dotenv(override=True)
    llm = init_llm(args.model)
    verifier_llm = (
        init_verifier_llm(args.verifier_provider, args.verifier_model)
        if args.verify_relations
        else None
    )
    questions = read_questions(args.questions, args.question_ids)

    all_rows: list[dict[str, str]] = []
    for idx, qid in enumerate(args.question_ids, 1):
        q = questions[qid]
        corpus_path = args.runs_dir / qid / "corpus.pubtator"
        if not corpus_path.exists():
            raise FileNotFoundError(f"{corpus_path} not found -- run the formal run first")

        print(f"[{idx}/{len(args.question_ids)}] Rebuilding graph for {qid}...", flush=True)
        started = time.monotonic()
        edges = extract_edges_for_question(
            corpus_path,
            q["question"],
            llm,
            args.semantic_threshold,
            args.max_hops,
            args.top_k_paths,
            question_id=qid,
            use_node_rag=not args.no_node_rag,
            verify_relations=args.verify_relations,
            verifier_llm=verifier_llm,
        )
        print(f"  -> {len(edges)} distinct edges in {time.monotonic() - started:.1f}s", flush=True)

        for i, edge in enumerate(edges, 1):
            all_rows.append(
                {
                    "question_id": qid,
                    "domain": q["domain"],
                    "question": q["question"],
                    "edge_id": f"{qid}-E{i:02d}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "relation_type": edge["relation_type"],
                    "supporting_titles": edge["supporting_titles"],
                    "supporting_abstracts": edge["supporting_abstracts"],
                    "evidence_quotes": edge["evidence_quotes"],
                    "pmids": edge["pmids"],
                    "min_hop_count": edge["min_hop_count"],
                    "max_path_score": edge["max_path_score"],
                    "rater_id": "",
                    "biologically_meaningful": "",
                    "relation_type_correct": "",
                    "notes": "",
                }
            )

    # Merge with any existing worksheet rows for questions NOT covered by this run, so re-running
    # on a subset of question-ids (e.g. only the ones that previously found zero paths) doesn't
    # wipe out already-collected edges for the other questions.
    final_rows = list(all_rows)
    if args.output.exists():
        rerun_qids = set(args.question_ids)
        with args.output.open(newline="", encoding="utf-8") as handle:
            preserved = [
                row for row in csv.DictReader(handle) if row["question_id"] not in rerun_qids
            ]
        final_rows = preserved + all_rows

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerows(final_rows)
    all_rows = final_rows

    total_qids = sorted(set(row["question_id"] for row in all_rows))
    print(f"\nWrote {len(all_rows)} candidate edges across {len(total_qids)} questions total "
          f"(this run covered {len(args.question_ids)}).")
    print(f"Worksheet: {args.output}")


if __name__ == "__main__":
    main()
