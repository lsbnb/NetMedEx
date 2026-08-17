#!/usr/bin/env python3
"""Build blinded pooled-relevance worksheets without modifying frozen qrels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from netmedex.pubtator_parser import PubTatorIO


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_review_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
    review_fields: set[str],
) -> None:
    if path.exists():
        existing = read_csv(path)
        if any(row.get(field, "").strip() for row in existing for field in review_fields):
            print(f"Preserving review in progress: {path}")
            return
    write_csv(path, fieldnames, rows)


def stable_order(question_id: str, pmid: str) -> str:
    return hashlib.sha256(f"formal-v2:{question_id}:{pmid}".encode()).hexdigest()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def fetch_pubmed_metadata(
    pmids: list[str], batch_size: int = 100, retries: int = 4
) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for start in range(0, len(pmids), batch_size):
        batch = pmids[start : start + batch_size]
        params = urllib.parse.urlencode(
            {
                "db": "pubmed",
                "retmode": "xml",
                "id": ",".join(batch),
                "tool": "netmedex_formal_v2_pool",
            }
        )
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{params}"
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "NetMedEx-formal-v2/1.0"}
                )
                with urllib.request.urlopen(request, timeout=90) as response:
                    root = ET.fromstring(response.read())
                for article in root.findall(".//PubmedArticle"):
                    pmid = element_text(article.find("./MedlineCitation/PMID"))
                    title = element_text(
                        article.find("./MedlineCitation/Article/ArticleTitle")
                    )
                    abstract_parts = []
                    for part in article.findall(
                        "./MedlineCitation/Article/Abstract/AbstractText"
                    ):
                        text = element_text(part)
                        label = part.attrib.get("Label", "")
                        abstract_parts.append(f"{label}: {text}" if label else text)
                    if pmid:
                        metadata[pmid] = {
                            "title": title,
                            "abstract": " ".join(filter(None, abstract_parts)),
                        }
                break
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    raise RuntimeError(
                        f"PubMed metadata fetch failed for batch at {start}: {last_error}"
                    ) from exc
                time.sleep(min(2**attempt, 10))
        time.sleep(0.34)
    return metadata


def load_corpus_metadata(
    questions_root: Path,
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, set[str]]]:
    metadata: dict[tuple[str, str], dict[str, str]] = {}
    corpus_pmids: dict[str, set[str]] = defaultdict(set)
    for corpus_path in sorted(questions_root.glob("Q*/corpus.pubtator")):
        question_id = corpus_path.parent.name
        collection = PubTatorIO.parse(corpus_path)
        for article in collection.articles:
            pmid = str(article.pmid)
            corpus_pmids[question_id].add(pmid)
            metadata[question_id, pmid] = {
                "title": str(article.title or ""),
                "abstract": str(article.abstract or ""),
            }
    return metadata, corpus_pmids


def build_pool(
    questions: list[dict[str, str]],
    qrels: list[dict[str, str]],
    runs: list[dict[str, str]],
    questions_root: Path,
    pool_depth: int,
    supplemental_metadata: dict[str, dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    question_by_id = {row["question_id"]: row for row in questions}
    old_qrels = {
        (row["question_id"], row["pmid"]): row["relevance"] for row in qrels
    }
    metadata, corpus_pmids = load_corpus_metadata(questions_root)

    ranks: dict[tuple[str, str, str], int] = {}
    for row in runs:
        rank = int(row["rank"])
        if rank <= pool_depth:
            ranks[row["question_id"], row["pmid"], row["system"]] = rank

    candidates: dict[str, set[str]] = defaultdict(set)
    for question_id, pmid in old_qrels:
        candidates[question_id].add(pmid)
    for question_id, pmids in corpus_pmids.items():
        candidates[question_id].update(pmids)
    for question_id, pmid, _system in ranks:
        candidates[question_id].add(pmid)

    blinded_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    for question_id in sorted(question_by_id):
        question = question_by_id[question_id]
        ordered_pmids = sorted(
            candidates[question_id],
            key=lambda pmid: (stable_order(question_id, pmid), pmid),
        )
        for index, pmid in enumerate(ordered_pmids, start=1):
            candidate_id = f"{question_id}-C{index:03d}"
            article = metadata.get(
                (question_id, pmid), (supplemental_metadata or {}).get(pmid, {})
            )
            blinded_rows.append(
                {
                    "candidate_id": candidate_id,
                    "question_id": question_id,
                    "domain": question.get("domain", ""),
                    "question": question["question"],
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "abstract": article.get("abstract", ""),
                    "relevance": "",
                    "confidence": "",
                    "exclusion_reason": "",
                    "reviewer_notes": "",
                }
            )
            netmedex_rank = ranks.get(
                (question_id, pmid, "netmedex_hybrid_rag"), ""
            )
            traditional_rank = ranks.get(
                (question_id, pmid, "traditional_rag"), ""
            )
            provenance_rows.append(
                {
                    "candidate_id": candidate_id,
                    "question_id": question_id,
                    "pmid": pmid,
                    "in_formal_v1_qrels": int((question_id, pmid) in old_qrels),
                    "formal_v1_relevance": old_qrels.get((question_id, pmid), ""),
                    "netmedex_rank": netmedex_rank,
                    "traditional_rank": traditional_rank,
                    "in_pubmed_corpus": int(pmid in corpus_pmids.get(question_id, set())),
                    "has_title_abstract": int(bool(article.get("title"))),
                    "requires_human_judgment": 1,
                }
            )
    return blinded_rows, provenance_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--formal-dir", type=Path, default=Path("evaluation/formal")
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("evaluation/formal_v2")
    )
    parser.add_argument("--pool-depth", type=int, default=20)
    parser.add_argument(
        "--fetch-missing-metadata",
        action="store_true",
        help="Fetch missing titles and abstracts from PubMed and cache them.",
    )
    args = parser.parse_args()

    questions = read_csv(args.formal_dir / "questions.csv")
    qrels = read_csv(args.formal_dir / "qrels.csv")
    runs = read_csv(args.run_dir / "retrieval_runs.csv")
    blinded, provenance = build_pool(
        questions,
        qrels,
        runs,
        args.run_dir / "questions",
        args.pool_depth,
    )
    if args.fetch_missing_metadata:
        cache_path = args.output_dir / "pubmed_metadata_cache.json"
        cache = (
            json.loads(cache_path.read_text(encoding="utf-8"))
            if cache_path.exists()
            else {}
        )
        missing_pmids = sorted(
            {
                row["pmid"]
                for row in blinded
                if not row["title"] and row["pmid"] not in cache
            },
            key=int,
        )
        if missing_pmids:
            cache.update(fetch_pubmed_metadata(missing_pmids))
            args.output_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        blinded, provenance = build_pool(
            questions,
            qrels,
            runs,
            args.run_dir / "questions",
            args.pool_depth,
            supplemental_metadata=cache,
        )

    rater_fields = [
        "candidate_id",
        "question_id",
        "domain",
        "question",
        "pmid",
        "title",
        "abstract",
        "relevance",
        "confidence",
        "exclusion_reason",
        "reviewer_notes",
    ]
    provenance_fields = [
        "candidate_id",
        "question_id",
        "pmid",
        "in_formal_v1_qrels",
        "formal_v1_relevance",
        "netmedex_rank",
        "traditional_rank",
        "in_pubmed_corpus",
        "has_title_abstract",
        "requires_human_judgment",
    ]
    review_fields = {"relevance", "confidence", "exclusion_reason", "reviewer_notes"}
    write_review_csv(
        args.output_dir / "expert_rater_1.csv",
        rater_fields,
        blinded,
        review_fields,
    )
    write_review_csv(
        args.output_dir / "expert_rater_2.csv",
        rater_fields,
        blinded,
        review_fields,
    )
    write_csv(args.output_dir / "pool_provenance.csv", provenance_fields, provenance)
    write_review_csv(
        args.output_dir / "adjudication.csv",
        [
            "candidate_id",
            "question_id",
            "pmid",
            "rater_1_relevance",
            "rater_2_relevance",
            "agreement",
            "adjudicated_relevance",
            "adjudicator_id",
            "adjudication_notes",
        ],
        [
            {
                "candidate_id": row["candidate_id"],
                "question_id": row["question_id"],
                "pmid": row["pmid"],
            }
            for row in blinded
        ],
        {"rater_1_relevance", "rater_2_relevance", "adjudicated_relevance"},
    )

    counts = defaultdict(int)
    missing_titles = 0
    missing_abstracts = 0
    for row in blinded:
        counts[row["question_id"]] += 1
        missing_titles += not bool(row["title"])
        missing_abstracts += not bool(row["abstract"])
    write_review_csv(
        args.output_dir / "review_status.csv",
        [
            "question_id",
            "candidate_count",
            "rater_1_status",
            "rater_2_status",
            "adjudication_status",
            "reviewer_assignment",
            "notes",
        ],
        [
            {
                "question_id": question_id,
                "candidate_count": counts[question_id],
                "rater_1_status": "pending",
                "rater_2_status": "pending",
                "adjudication_status": "pending",
            }
            for question_id in sorted(counts)
        ],
        {
            "rater_1_status",
            "rater_2_status",
            "adjudication_status",
            "reviewer_assignment",
            "notes",
        },
    )
    manifest = {
        "benchmark_version": "formal-v2-pooled-draft",
        "status": "awaiting_blinded_human_review",
        "question_count": len(counts),
        "candidate_judgment_count": len(blinded),
        "minimum_candidates_per_question": min(counts.values()),
        "maximum_candidates_per_question": max(counts.values()),
        "mean_candidates_per_question": round(len(blinded) / len(counts), 2),
        "missing_title_count": missing_titles,
        "missing_abstract_count": missing_abstracts,
        "pool_depth": args.pool_depth,
        "sources": [
            "formal-v1 qrels",
            "NetMedEx Hybrid RAG ranking",
            "Traditional RAG ranking",
            "independent PubMed ESearch corpus",
        ],
        "blinding": "System source, rank, and prior relevance are excluded from rater files.",
        "formal_v1_modified": False,
    }
    (args.output_dir / "pool_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
