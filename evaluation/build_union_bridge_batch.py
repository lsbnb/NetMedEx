#!/usr/bin/env python3
"""Fetch and freeze source/target/pair union corpora for bridge evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from evaluation.run_formal_50 import pubmed_esearch
from netmedex.pubtator import PubTatorAPI


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def round_robin_unique(strata: dict[str, list[str]]) -> list[str]:
    result = []
    seen = set()
    maximum = max((len(pmids) for pmids in strata.values()), default=0)
    for index in range(maximum):
        for pmids in strata.values():
            if index < len(pmids) and pmids[index] not in seen:
                seen.add(pmids[index])
                result.append(pmids[index])
    return result


def pubmed_publication_years(pmids: list[str]) -> dict[str, int | None]:
    """Resolve NCBI's canonical PubMed publication year for a date-leak audit."""
    years: dict[str, int | None] = {}
    for index in range(0, len(pmids), 100):
        batch = pmids[index : index + 100]
        query = urllib.parse.urlencode(
            {"db": "pubmed", "retmode": "json", "id": ",".join(batch)}
        )
        with urllib.request.urlopen(
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{query}",
            timeout=60,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))["result"]
        for pmid in batch:
            match = re.search(r"(?:19|20)\d{2}", str(result.get(pmid, {}).get("pubdate", "")))
            years[pmid] = int(match.group()) if match else None
    return years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-batch",
        type=Path,
        default=Path("evaluation/formal/bridge_withheld_endpoint_only_dev_v1"),
    )
    parser.add_argument(
        "--query-spec",
        type=Path,
        default=Path("evaluation/formal/union_corpus_query_spec_v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/formal/bridge_withheld_union_dev_v1"),
    )
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument(
        "--max-pub-year",
        type=int,
        help="Hard-filter every PMID using NCBI ESummary publication year after search.",
    )
    args = parser.parse_args()

    spec = json.loads(args.query_spec.read_text(encoding="utf-8"))
    per_stratum = int(spec["per_stratum_articles"])
    selected_ids = args.question_id or list(spec["questions"])
    query_by_id = {
        row["question_id"]: dict(row)
        for row in read_csv(args.source_batch / "queries.csv")
    }
    metadata_by_id = {
        row["question_id"]: dict(row)
        for row in read_csv(args.source_batch / "questions_metadata.csv")
    }
    missing = sorted(
        set(selected_ids) - set(query_by_id) | set(selected_ids) - set(spec["questions"])
    )
    if missing:
        raise ValueError(f"Unknown question IDs: {missing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    query_rows = [query_by_id[qid] for qid in selected_ids]
    metadata_rows = [metadata_by_id[qid] for qid in selected_ids]
    write_csv(args.output_dir / "queries.csv", query_rows)
    write_csv(args.output_dir / "questions_metadata.csv", metadata_rows)

    question_records = []
    artifact_paths = [args.output_dir / "queries.csv", args.output_dir / "questions_metadata.csv"]
    for question_id in selected_ids:
        question_spec = spec["questions"][question_id]
        stratum_queries = {
            key: question_spec[key] for key in ("source", "target", "endpoint_pair")
        }
        normalized_queries = " ".join(normalized(query) for query in stratum_queries.values())
        leaks = [
            mediator
            for mediator in question_spec.get("forbidden_mediators", [])
            if normalized(mediator) in normalized_queries
        ]
        if leaks:
            raise ValueError(f"{question_id} retrieval query leaks mediators: {leaks}")

        strata = {
            name: pubmed_esearch(query, per_stratum)
            for name, query in stratum_queries.items()
        }
        union_pmids = round_robin_unique(strata)
        publication_years = pubmed_publication_years(union_pmids)
        date_excluded_pmids = []
        if args.max_pub_year is not None:
            date_excluded_pmids = [
                pmid
                for pmid in union_pmids
                if publication_years.get(pmid) is None
                or publication_years[pmid] > args.max_pub_year
            ]
            union_pmids = [pmid for pmid in union_pmids if pmid not in date_excluded_pmids]
        if not union_pmids:
            raise RuntimeError(f"No PubMed records for {question_id}")
        collection = PubTatorAPI(
            query=None,
            pmid_list=union_pmids,
            sort="score",
            request_format="biocjson",
            max_articles=len(union_pmids),
            full_text=False,
            queue=None,
        ).run()
        fetched_pmids = [str(article.pmid) for article in collection.articles]
        question_dir = args.output_dir / "questions" / question_id
        question_dir.mkdir(parents=True, exist_ok=True)
        corpus_path = question_dir / "corpus.pubtator"
        corpus_path.write_text(
            collection.to_pubtator_str(annotation_use_identifier_name=True),
            encoding="utf-8",
        )
        manifest = {
            "question_id": question_id,
            "corpus_strategy": "source_target_endpoint_pair_union",
            "same_union_corpus_for_text_and_hybrid": True,
            "per_stratum_articles": per_stratum,
            "stratum_queries": stratum_queries,
            "forbidden_mediators": question_spec.get("forbidden_mediators", []),
            "mediator_leaks": leaks,
            "stratum_pmids": strata,
            "union_pmids_requested": union_pmids,
            "fetched_pmids": fetched_pmids,
            "publication_years": publication_years,
            "max_pub_year": args.max_pub_year,
            "date_excluded_pmids": date_excluded_pmids,
        }
        manifest_path = question_dir / "corpus_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifact_paths.extend([corpus_path, manifest_path])
        question_records.append(
            {
                "question_id": question_id,
                "document_count": len(fetched_pmids),
                "requested_union_count": len(union_pmids),
                "stratum_unique_counts": {
                    name: len(set(pmids)) for name, pmids in strata.items()
                },
                "corpus_sha256": sha256(corpus_path),
            }
        )

    freeze = {
        "name": "netmedex-bridge-withheld-union-development-v1",
        "status": "frozen_before_semantic_graph_generation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "independent_holdout": False,
        "same_union_corpus_for_text_and_hybrid": True,
        "text_context_top_k": 10,
        "max_pub_year": args.max_pub_year,
        "query_spec": str(args.query_spec),
        "query_spec_sha256": sha256(args.query_spec),
        "questions": question_records,
        "checksums": {
            str(path.relative_to(args.output_dir)): sha256(path) for path in artifact_paths
        },
    }
    (args.output_dir / "freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Frozen union corpus: "
        + ", ".join(
            f"{row['question_id']}={row['document_count']} docs"
            for row in question_records
        )
    )


if __name__ == "__main__":
    main()
