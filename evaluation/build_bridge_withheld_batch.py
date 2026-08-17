#!/usr/bin/env python3
"""Build a frozen 10-question development batch with mediator names withheld."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


FORMAL_DIR = Path("evaluation/formal")
OUTPUT_DIR = FORMAL_DIR / "bridge_withheld_dev_v1"
CORPUS_SOURCE = FORMAL_DIR / "runs/formal-v1-gpt-5.6-terra/questions"
SPECS = [
    ("BW001", "Q001", "What evidence-supported intermediates connect icariin to osteoblast differentiation?"),
    ("BW002", "Q004", "Which evidence-supported intermediates connect curcumin to apoptosis?"),
    ("BW003", "Q008", "Which evidence-supported intermediates connect CFTR dysfunction to intestinal inflammation?"),
    ("BW004", "Q016", "Which evidence-supported intermediates connect SMN deficiency to mitochondrial dysfunction?"),
    ("BW005", "Q018", "Which evidence-supported intermediates connect PD-1 blockade to immune-related adverse events?"),
    ("BW006", "Q025", "Which evidence-supported intermediates connect dystrophin deficiency to chronic inflammation?"),
    ("BW007", "Q029", "Which evidence-supported intermediates connect endothelial senescence to atherosclerosis?"),
    ("BW008", "Q037", "Which evidence-supported intermediates connect chronic hepatitis B infection to hepatocellular carcinoma?"),
    ("BW009", "Q041", "哪些具有文獻證據的中介機制可連結 SGLT2 抑制劑與腎臟保護？"),
    ("BW010", "Q050", "Which evidence-supported intermediates connect gut microbiome dysbiosis to bone loss?"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_queries = {
        row["question_id"]: row for row in read_csv(FORMAL_DIR / "formal_run_queries.csv")
    }
    source_metadata = {
        row["question_id"]: row for row in read_csv(FORMAL_DIR / "questions.csv")
    }
    query_rows = []
    metadata_rows = []
    corpus_files = []
    for question_id, source_id, question in SPECS:
        source_query = dict(source_queries[source_id])
        source_query["question_id"] = question_id
        source_query["question"] = question
        query_rows.append(source_query)
        metadata_rows.append(
            {
                "question_id": question_id,
                "question_type": "mechanism",
                "source_question_id": source_id,
            }
        )
        target_dir = OUTPUT_DIR / "questions" / question_id
        target_dir.mkdir(parents=True, exist_ok=True)
        source_corpus = CORPUS_SOURCE / source_id / "corpus.pubtator"
        target_corpus = target_dir / "corpus.pubtator"
        shutil.copy2(source_corpus, target_corpus)
        corpus_files.append(target_corpus)

    query_fields = list(source_queries[SPECS[0][1]])
    write_csv(OUTPUT_DIR / "queries.csv", query_rows, query_fields)
    write_csv(
        OUTPUT_DIR / "questions_metadata.csv",
        metadata_rows,
        ["question_id", "question_type", "source_question_id"],
    )
    freeze = {
        "name": "netmedex-bridge-withheld-development-v1",
        "status": "frozen_before_generation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(SPECS),
        "selection_used_qrels": False,
        "selection_used_prior_answer_scores": False,
        "independent_holdout": False,
        "purpose": "Develop contrastive graph-incremental selection; mediator terms are withheld from prompts.",
        "rules": [
            "Each prompt names source and target but not the expected bridge.",
            "Corpora are copied unchanged from the frozen formal-v1 run.",
            "This is a development batch and cannot establish independent superiority.",
        ],
        "questions": [
            {"question_id": qid, "source_question_id": source, "question": question}
            for qid, source, question in SPECS
        ],
        "checksums": {
            "queries.csv": checksum(OUTPUT_DIR / "queries.csv"),
            "questions_metadata.csv": checksum(OUTPUT_DIR / "questions_metadata.csv"),
            **{
                str(path.relative_to(OUTPUT_DIR)): checksum(path) for path in corpus_files
            },
        },
    }
    (OUTPUT_DIR / "freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Frozen {len(SPECS)} bridge-withheld development questions in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
