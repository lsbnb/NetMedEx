#!/usr/bin/env python3
"""Compose D-v3 from six incremental answers and exact C fallback for all other items."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


INCREMENTAL_IDS = {"PP014", "PP015", "PP016", "PP018", "PP019", "PP020"}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abcd", type=Path, required=True)
    parser.add_argument("--dv2", type=Path, required=True)
    parser.add_argument("--dv3-six", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = read(args.abcd)
    by_arm = {(row["question_id"], row["arm"]): row["answer"] for row in base}
    dv2 = {row["question_id"]: row["answer"] for row in read(args.dv2)}
    dv3_six = {row["question_id"]: row["answer"] for row in read(args.dv3_six)}
    if set(dv3_six) != INCREMENTAL_IDS:
        raise RuntimeError(f"D-v3 incremental IDs mismatch: {sorted(dv3_six)}")
    qids = sorted({qid for qid, arm in by_arm if arm == "B"})
    rows = []
    for qid in qids:
        rows.extend(
            [
                {"question_id": qid, "system": "traditional_text_rag", "answer": by_arm[(qid, "B")]},
                {"question_id": qid, "system": "structured_all_path_dv2", "answer": dv2[qid]},
                {
                    "question_id": qid,
                    "system": "incremental_routed_dv3",
                    "answer": dv3_six[qid] if qid in INCREMENTAL_IDS else by_arm[(qid, "C")],
                },
            ]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question_id", "system", "answer"])
        writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} answers; D-v3 graph intervention={len(INCREMENTAL_IDS)}/{len(qids)}")


if __name__ == "__main__": main()
