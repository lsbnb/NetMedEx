#!/usr/bin/env python3
"""Run A-E replay with one Terra graph-extraction pass and Luna answers.

The graph stage uses the frozen corpora and persists one semantic graph per question.  The
profile stages reuse those local graphs, so C/D/E only recompute exposure/gating and answer
generation; they do not repeat semantic extraction.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROFILES = ("A_text_only", "B_entity_validated", "C_one_hop", "D_two_hop", "E_verified_gated_two_hop")


def runner_command(repo_root: Path, *, queries: Path, questions_metadata: Path, run_dir: Path,
                   model: str, profile: str, corpora_dir: Path, expected_count: int,
                   reuse_graphs_dir: Path | None = None, persist_graph: bool = False,
                   skip_answer_generation: bool = False) -> list[str]:
    cmd = [
        sys.executable, str(repo_root / "evaluation" / "run_formal_50.py"),
        "--queries", str(queries), "--questions-metadata", str(questions_metadata),
        "--expected-question-count", str(expected_count), "--run-dir", str(run_dir),
        "--model", model, "--hybrid-profile", profile,
        "--reuse-corpora-dir", str(corpora_dir),
    ]
    if reuse_graphs_dir is not None:
        cmd += ["--reuse-graphs-dir", str(reuse_graphs_dir)]
    if persist_graph:
        cmd.append("--persist-graph")
    if skip_answer_generation:
        cmd.append("--skip-answer-generation")
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-dir", type=Path, default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra"))
    parser.add_argument("--output-root", type=Path, default=Path("evaluation/formal/runs/formal-v1-ae-replay-terra-graphs-luna-answers-v1"))
    parser.add_argument("--queries", type=Path, default=Path("evaluation/formal/formal_run_queries_q001_q010.csv"))
    parser.add_argument("--questions-metadata", type=Path, default=Path("evaluation/formal/questions.csv"))
    parser.add_argument("--expected-question-count", type=int, default=10)
    parser.add_argument("--graph-model", default="gpt-5.6-terra")
    parser.add_argument("--answer-model", default="gpt-5.6-luna")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    corpora_dir = args.source_run_dir / "questions"
    graph_run = args.output_root / "terra_graphs"
    manifest_path = args.output_root / "replay_manifest.json"
    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "benchmark": "formal-v1-ae-replay-terra-graphs-luna-answers",
        "status": "running", "replay_version": "v1",
        "source_corpus_dir": str(corpora_dir), "output_root": str(args.output_root),
        "graph_model": args.graph_model, "answer_model": args.answer_model,
        "profiles": list(PROFILES), "expected_question_count": args.expected_question_count,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    graph_cmd = runner_command(
        repo_root, queries=args.queries, questions_metadata=args.questions_metadata,
        run_dir=graph_run, model=args.graph_model, profile="B_entity_validated",
        corpora_dir=corpora_dir, expected_count=args.expected_question_count,
        persist_graph=True, skip_answer_generation=True,
    )
    if args.force:
        graph_cmd.append("--force")
    subprocess.run(graph_cmd, cwd=repo_root, check=True)

    for profile in PROFILES:
        run_dir = args.output_root / profile
        cmd = runner_command(
            repo_root, queries=args.queries, questions_metadata=args.questions_metadata,
            run_dir=run_dir, model=args.answer_model, profile=profile,
            corpora_dir=corpora_dir, expected_count=args.expected_question_count,
            reuse_graphs_dir=graph_run / "questions" if profile != "A_text_only" else None,
        )
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, cwd=repo_root, check=True)

    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
