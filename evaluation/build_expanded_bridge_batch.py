#!/usr/bin/env python3
"""Fetch and freeze a larger corpus for eligible bridge-withheld questions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.run_formal_50 import pubmed_esearch_with_relaxation
from netmedex.pubtator import PubTatorAPI


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty question batch")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-batch",
        type=Path,
        default=Path("evaluation/formal/bridge_withheld_dev_v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/formal/bridge_withheld_expanded_dev_v1"),
    )
    parser.add_argument("--question-id", action="append", required=True)
    parser.add_argument(
        "--query-override",
        action="append",
        default=[],
        metavar="QUESTION_ID=PUBMED_QUERY",
        help="Replace a mediator-leaking retrieval query before corpus freeze.",
    )
    parser.add_argument("--max-articles", type=int, default=40)
    args = parser.parse_args()

    query_by_id = {
        row["question_id"]: dict(row)
        for row in read_csv(args.source_batch / "queries.csv")
    }
    metadata_by_id = {
        row["question_id"]: row
        for row in read_csv(args.source_batch / "questions_metadata.csv")
    }
    missing = [qid for qid in args.question_id if qid not in query_by_id]
    if missing:
        raise ValueError(f"Unknown question IDs: {missing}")
    overrides = {}
    for value in args.query_override:
        question_id, separator, query = value.partition("=")
        if not separator or not question_id.strip() or not query.strip():
            raise ValueError(f"Invalid --query-override: {value!r}")
        overrides[question_id.strip()] = query.strip()
    unknown_overrides = sorted(set(overrides) - set(args.question_id))
    if unknown_overrides:
        raise ValueError(
            f"Query overrides supplied for unselected questions: {unknown_overrides}"
        )
    for question_id, query in overrides.items():
        query_by_id[question_id]["pubmed_query"] = query

    args.output_dir.mkdir(parents=True, exist_ok=True)
    query_rows = [query_by_id[qid] for qid in args.question_id]
    metadata_rows = [metadata_by_id[qid] for qid in args.question_id]
    write_csv(args.output_dir / "queries.csv", query_rows)
    write_csv(args.output_dir / "questions_metadata.csv", metadata_rows)

    question_records = []
    corpus_paths = []
    for qid in args.question_id:
        row = query_by_id[qid]
        pmids, effective_query, attempts = pubmed_esearch_with_relaxation(
            row["pubmed_query"], args.max_articles
        )
        if not pmids:
            raise RuntimeError(f"No PubMed records for {qid}")
        collection = PubTatorAPI(
            query=None,
            pmid_list=pmids,
            sort="score",
            request_format="biocjson",
            max_articles=args.max_articles,
            full_text=False,
            queue=None,
        ).run()
        question_dir = args.output_dir / "questions" / qid
        question_dir.mkdir(parents=True, exist_ok=True)
        corpus_path = question_dir / "corpus.pubtator"
        corpus_path.write_text(
            collection.to_pubtator_str(annotation_use_identifier_name=True),
            encoding="utf-8",
        )
        fetched_pmids = [str(article.pmid) for article in collection.articles]
        manifest = {
            "question_id": qid,
            "pubmed_query": row["pubmed_query"],
            "effective_pubmed_query": effective_query,
            "query_attempts": attempts,
            "esearch_pmids": pmids,
            "fetched_pmids": fetched_pmids,
        }
        manifest_path = question_dir / "corpus_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        corpus_paths.extend([corpus_path, manifest_path])
        question_records.append(
            {
                "question_id": qid,
                "document_count": len(fetched_pmids),
                "corpus_sha256": sha256(corpus_path),
            }
        )

    freeze = {
        "name": "netmedex-bridge-withheld-expanded-development-v1",
        "status": "frozen_before_semantic_graph_generation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "independent_holdout": False,
        "max_articles": args.max_articles,
        "source_batch": str(args.source_batch),
        "mediator_blind_retrieval_queries": True,
        "query_overrides": overrides,
        "questions": question_records,
        "checksums": {
            "queries.csv": sha256(args.output_dir / "queries.csv"),
            "questions_metadata.csv": sha256(
                args.output_dir / "questions_metadata.csv"
            ),
            **{
                str(path.relative_to(args.output_dir)): sha256(path)
                for path in corpus_paths
            },
        },
    }
    (args.output_dir / "freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Frozen {len(question_records)} questions in {args.output_dir}: "
        + ", ".join(
            f"{row['question_id']}={row['document_count']} docs"
            for row in question_records
        )
    )


if __name__ == "__main__":
    main()
