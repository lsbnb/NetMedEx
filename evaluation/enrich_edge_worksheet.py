#!/usr/bin/env python3
"""Add frozen PubMed abstracts to an existing edge worksheet without rebuilding its graph."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from netmedex.pubtator_parser import PubTatorIO


def enrich(input_path: Path, output_path: Path, corpora_dir: Path) -> int:
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for field in ("supporting_abstracts", "evidence_quotes"):
        if field not in fields:
            fields.insert(fields.index("pmids") if "pmids" in fields else len(fields), field)

    cache: dict[str, dict[str, str]] = {}
    for row in rows:
        qid = row["question_id"]
        if qid not in cache:
            corpus = corpora_dir / qid / "corpus.pubtator"
            if not corpus.exists():
                raise FileNotFoundError(corpus)
            collection = PubTatorIO.parse(corpus)
            cache[qid] = {str(a.pmid): str(a.abstract or "") for a in collection.articles}
        abstracts = cache[qid]
        pmids = [value.strip() for value in row.get("pmids", "").split(";") if value.strip()]
        row["supporting_abstracts"] = "\n\n".join(
            f"PMID {pmid}: {abstracts.get(pmid, '[abstract unavailable]')}" for pmid in pmids
        )
        row.setdefault("evidence_quotes", "")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(output_path)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("evaluation/formal/edge_ratings_worksheet.csv")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/formal/edge_ratings_worksheet_enriched.csv"),
    )
    parser.add_argument(
        "--corpora-dir",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/questions"),
    )
    args = parser.parse_args()
    print(f"Wrote {enrich(args.input, args.output, args.corpora_dir)} enriched edge rows")
    print(args.output)


if __name__ == "__main__":
    main()
