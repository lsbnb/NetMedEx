#!/usr/bin/env python3
"""Build deterministic path claims for pre-generation semantic selection."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def path_claim(path: dict) -> str:
    names = list(map(str, path.get("names", [])))
    relations = list(map(str, path.get("relations", [])))
    if len(names) < 3 or len(names) > 5 or len(relations) != len(names) - 1:
        return ""
    return "; ".join(
        f"{names[index]} {relations[index]} {names[index + 1]}"
        for index in range(len(relations))
    ) + "."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    rows = []
    selected = set(args.only)
    for result_path in sorted((args.run_dir / "questions").glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        question_id = str(result.get("question_id", result_path.parent.name))
        if selected and question_id not in selected:
            continue
        comparison_answer = result.get("answers", {}).get("traditional_rag", "")
        if not comparison_answer:
            continue
        candidate_index = 0
        for path in result.get("graph", {}).get("paths", []):
            if path.get("incremental_value_class") != "graph_incremental_candidate":
                continue
            claim = path_claim(path)
            if not claim:
                continue
            candidate_index += 1
            pmids = sorted(
                {
                    str(pmid)
                    for group in path.get("edge_pmids", [])
                    for pmid in group
                }
            )
            rows.append(
                {
                    "hidden_claim_id": f"{question_id}-PC{candidate_index:02d}",
                    "question_id": question_id,
                    "question": result.get("question", ""),
                    "candidate_claim": claim,
                    "candidate_block": (
                        f"{claim} PATH {path.get('path_signature', '')}; "
                        f"PMIDs: {', '.join(pmids)}"
                    ),
                    "path_evidence_json": json.dumps([path], ensure_ascii=False),
                    "comparison_answer": comparison_answer,
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["hidden_claim_id"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} deterministic path candidates to {args.output}")


if __name__ == "__main__":
    main()
