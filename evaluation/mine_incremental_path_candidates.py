#!/usr/bin/env python3
"""Mine frozen runs for high-precision two-hop candidates before paid generation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from netmedex.claim_verifier import relation_supported_by_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("evaluation/formal/runs"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/formal/incremental_path_candidates_v2.csv"),
    )
    args = parser.parse_args()

    rows = []
    seen = set()
    for result_path in sorted(args.runs_dir.glob("*/questions/*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            continue
        text_pmids = {
            str(record.get("pmid"))
            for record in result.get("rankings", {}).get("traditional_rag", [])
            if isinstance(record, dict)
        }
        for path in result.get("graph", {}).get("paths", []):
            if len(path.get("node_ids", [])) != 3 or not path.get("claim_safe"):
                continue
            relations = path.get("relations", [])
            quote_groups = path.get("edge_evidence_quotes", [])
            if len(relations) != 2 or len(quote_groups) != 2:
                continue
            quote_aligned = all(
                quotes
                and any(
                    relation_supported_by_text(str(quote), relation)
                    for quote in quotes
                )
                for relation, quotes in zip(relations, quote_groups)
            )
            if not quote_aligned:
                continue
            pmids = {
                str(pmid)
                for group in path.get("edge_pmids", [])
                for pmid in group
            }
            outside_pmids = sorted(pmids - text_pmids)
            if not outside_pmids:
                continue
            signature = (
                result.get("question_id"),
                tuple(path.get("node_ids", [])),
                tuple(relations),
                tuple(sorted(pmids)),
            )
            if signature in seen:
                continue
            seen.add(signature)
            names = path.get("names", [])
            rows.append(
                {
                    "question_id": result.get("question_id", ""),
                    "question": result.get("question", ""),
                    "source": names[0] if names else "",
                    "bridge": names[1] if len(names) > 1 else "",
                    "target": names[2] if len(names) > 2 else "",
                    "relations": "|".join(map(str, relations)),
                    "supporting_pmids": "|".join(sorted(pmids)),
                    "outside_text_top_k_pmids": "|".join(outside_pmids),
                    "path_score": path.get("score", ""),
                    "source_result": str(result_path),
                    "requires_semantic_non_equivalence_review": True,
                    "requires_nontrivial_bridge_review": True,
                }
            )

    rows.sort(key=lambda row: (-float(row["path_score"] or 0), row["question_id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["question_id"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} candidates to {args.output}")


if __name__ == "__main__":
    main()
