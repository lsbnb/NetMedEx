#!/usr/bin/env python3
"""Extract traceable graph-derived claims into a blinded hidden-information worksheet."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from netmedex.claim_verifier import verify_claim_to_path


PATH_RE = re.compile(r"(?i)PATH(?:\s*[:#*,-]*)\s*([0-9a-f]{16})")
HEADING_RE = re.compile(r"(?i)Graph-derived candidate insights\s*\n")
SECTION_END_RE = re.compile(r"(?im)^\s*(?:---+|\*{0,2}Summary\*{0,2}\s*:?)")


def extract_blocks(answer: str) -> list[str]:
    heading = HEADING_RE.search(answer)
    if not heading:
        return []
    section = answer[heading.end() :]
    end = SECTION_END_RE.search(section)
    if end:
        section = section[: end.start()]
    return [block.strip() for block in re.split(r"(?m)^- ", section) if block.strip()]


def clean_claim(block: str) -> str:
    first_line = block.splitlines()[0].strip()
    first_line = re.sub(r"^\*\*Claim:\*\*\s*", "", first_line, flags=re.I)
    first_line = re.sub(r"\s*[\[(]?PATH\s*[:#*,-].*$", "", first_line, flags=re.I)
    return first_line.strip(" -*")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    rows = []
    keys = []
    for result_path in sorted((args.run_dir / "questions").glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        question_id = result["question_id"]
        if args.only and question_id not in set(args.only):
            continue
        paths = {
            path["path_signature"]: path for path in result.get("graph", {}).get("paths", [])
        }
        hybrid_answer = result.get("answers", {}).get("netmedex_hybrid_rag", "")
        comparator = result.get("answers", {}).get("traditional_rag", "")
        candidate_index = 0
        for block in extract_blocks(hybrid_answer):
            refs = sorted(set(PATH_RE.findall(block)))
            if not refs or any(ref not in paths for ref in refs):
                continue
            claim = clean_claim(block)
            if not claim:
                continue
            for ref in refs:
                if paths[ref].get("incremental_value_class") != "graph_incremental_candidate":
                    continue
                verification = verify_claim_to_path(
                    block, ref, list(paths.values()), claim_id="candidate"
                )
                if verification["verdict"] != "supported":
                    continue
                candidate_index += 1
                claim_id = f"{question_id}-HC{candidate_index:02d}"
                rows.append(
                    {
                        "hidden_claim_id": claim_id,
                        "question_id": question_id,
                        "question": result["question"],
                        "candidate_claim": claim,
                        "candidate_block": block,
                        "path_evidence_json": json.dumps(
                            [paths[ref]], ensure_ascii=False
                        ),
                        "comparison_answer": comparator,
                    }
                )
                keys.append(
                    {
                        "hidden_claim_id": claim_id,
                        "question_id": question_id,
                        "source_system": "netmedex_hybrid_rag",
                        "path_signatures": ref,
                    }
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    with args.key_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(keys[0]) if keys else [])
        if keys:
            writer.writeheader()
            writer.writerows(keys)
    print(f"wrote {len(rows)} traceable hidden-claim candidates across "
          f"{len({row['question_id'] for row in rows})} questions")


if __name__ == "__main__":
    main()
