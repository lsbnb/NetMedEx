#!/usr/bin/env python3
"""Run the preregistered four-arm NetMedEx retrieval/answer ablation."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ARMS = {
    "A": {
        "label": "closed_book_llm",
        "system_flag": "--general-answer-only",
        "profile": "A_text_only",
    },
    "B": {
        "label": "traditional_text_rag",
        "system_flag": "--traditional-answer-only",
        "profile": "A_text_only",
    },
    "C": {
        "label": "text_rag_kg_reranking",
        "system_flag": "--hybrid-answer-only",
        "profile": "F_adaptive",
        "suppress_graph_context": True,
    },
    "D": {
        "label": "kg_expansion_reranking_path_answer",
        "system_flag": "--hybrid-answer-only",
        "profile": "F_adaptive",
        "expand": True,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--questions-metadata", type=Path, required=True)
    parser.add_argument("--reuse-corpora-dir", type=Path, required=True)
    parser.add_argument(
        "--reuse-graphs-dir",
        type=Path,
        help="Trusted prebuilt <DIR>/<QID>/graph.pkl used by graph-enabled arms C/D.",
    )
    parser.add_argument(
        "--reuse-exposures-dir",
        type=Path,
        help="Frozen <DIR>/<QID>/result.json paths used by graph-enabled arms C/D.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument(
        "--provider", choices=("openai", "anthropic", "local"), default="local"
    )
    parser.add_argument("--expected-question-count", type=int, required=True)
    parser.add_argument("--max-articles", type=int, default=15)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--answer-max-tokens", type=int, default=1600)
    parser.add_argument("--kg-expansion-articles", type=int, default=15)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--compile-only", action="store_true",
        help="Rebuild the combined CSV from completed arm checkpoints without generation.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    graph_cache = args.output_dir / "graph_cache"
    commands: dict[str, list[str]] = {}
    for arm, config in ARMS.items():
        command = [
            sys.executable,
            "evaluation/run_formal_50.py",
            "--queries",
            str(args.queries),
            "--questions-metadata",
            str(args.questions_metadata),
            "--reuse-corpora-dir",
            str(args.reuse_corpora_dir),
            "--run-dir",
            str(args.output_dir / f"arm_{arm}"),
            "--model",
            args.model,
            "--provider",
            args.provider,
            "--expected-question-count",
            str(args.expected_question_count),
            "--max-articles",
            str(args.max_articles),
            "--top-k",
            str(args.top_k),
            "--answer-max-tokens",
            str(args.answer_max_tokens),
            "--hybrid-profile",
            config["profile"],
            config["system_flag"],
            "--graph-cache-dir",
            str(graph_cache),
        ]
        if config.get("suppress_graph_context"):
            command.append("--suppress-graph-answer-context")
        if config.get("expand"):
            command.extend(["--kg-expansion-articles", str(args.kg_expansion_articles)])
        if args.force:
            command.append("--force")
        if args.reuse_graphs_dir is not None and arm in {"C", "D"}:
            command.extend(["--reuse-graphs-dir", str(args.reuse_graphs_dir)])
        if args.reuse_exposures_dir is not None and arm in {"C", "D"}:
            command.extend(["--reuse-exposures-dir", str(args.reuse_exposures_dir)])
        for question_id in args.only:
            command.extend(["--only", question_id])
        commands[arm] = command

    manifest = {
        "design": ARMS,
        "commands": commands,
        "shared_frozen_corpus": str(args.reuse_corpora_dir),
        "shared_graph_cache": str(graph_cache),
        "shared_prebuilt_graphs": (
            str(args.reuse_graphs_dir) if args.reuse_graphs_dir is not None else None
        ),
        "shared_frozen_exposures": (
            str(args.reuse_exposures_dir)
            if args.reuse_exposures_dir is not None
            else None
        ),
        "provider": args.provider,
        "model": args.model,
        "answer_max_tokens": args.answer_max_tokens,
    }
    (args.output_dir / "ablation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.dry_run:
        for arm, command in commands.items():
            print(arm, " ".join(command))
        return

    if not args.compile_only:
        for arm in ("A", "B", "C", "D"):
            subprocess.run(commands[arm], check=True)

    combined = []
    for arm, config in ARMS.items():
        output_path = args.output_dir / f"arm_{arm}" / "system_outputs.csv"
        with output_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                combined.append(
                    {
                        "arm": arm,
                        "system": config["label"],
                        "question_id": row["question_id"],
                        "answer": row["answer"],
                    }
                )
    with (args.output_dir / "ablation_system_outputs.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["arm", "system", "question_id", "answer"]
        )
        writer.writeheader()
        writer.writerows(combined)


if __name__ == "__main__":
    main()
