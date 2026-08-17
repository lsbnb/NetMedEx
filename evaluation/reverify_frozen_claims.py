#!/usr/bin/env python3
"""Re-run deterministic claim verification on saved answers without LLM calls."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evaluation.regate_frozen_exposures import corpus_aliases
from netmedex.claim_verifier import verify_answer_graph_claims


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    rows = []
    for result_path in sorted((args.run_dir / "questions").glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            continue
        aliases = corpus_aliases(result_path.with_name("corpus.pubtator"))
        for path in result.get("graph", {}).get("paths", []):
            path["node_aliases"] = [
                sorted(aliases.get(node_id, {name}))
                for node_id, name in zip(
                    path.get("node_ids", []), path.get("names", [])
                )
            ]
        verification = verify_answer_graph_claims(
            result.get("answers", {}).get("netmedex_hybrid_rag", ""),
            result.get("graph", {}).get("paths", []),
        )
        result["claim_verification"] = verification
        atomic_json(result_path, result)
        if verification["claims"]:
            for claim in verification["claims"]:
                rows.append(
                    {
                        "question_id": result["question_id"],
                        "claim_id": claim["claim_id"],
                        "path_id": claim["path_id"],
                        "verdict": claim["verdict"],
                        "reasons": ";".join(claim["reasons"]),
                    }
                )
        else:
            rows.append(
                {
                    "question_id": result["question_id"],
                    "claim_id": "",
                    "path_id": "",
                    "verdict": "no_path_citation",
                    "reasons": "no_path_citations_detected",
                }
            )

    with (args.run_dir / "claim_verification.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["question_id", "claim_id", "path_id", "verdict", "reasons"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Reverified {len(rows)} claim rows with 0 LLM/API calls")


if __name__ == "__main__":
    main()
