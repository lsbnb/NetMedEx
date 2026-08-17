#!/usr/bin/env python3
"""Replay the frozen formal-v1 corpus into a versioned A-E ablation workspace.

This wrapper does not touch the legacy completed run. Instead, it reuses the already-frozen
per-question ``corpus.pubtator`` files from a source formal run and replays the five formal
ablation profiles into separate, versioned subdirectories so path-level and evidence-exposure
artifacts are produced explicitly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROFILES = (
    "A_text_only",
    "B_entity_validated",
    "C_one_hop",
    "D_two_hop",
    "E_verified_gated_two_hop",
)

DEFAULT_SOURCE_RUN_DIR = Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra")
DEFAULT_OUTPUT_ROOT = Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra-ae-replay-v1")
DEFAULT_QUERIES = Path("evaluation/formal/formal_run_queries.csv")
DEFAULT_QUESTIONS = Path("evaluation/formal/questions.csv")
DEFAULT_MODEL = "gpt-5.6-terra"


def build_profile_run_dir(output_root: Path, profile: str) -> Path:
    return output_root / profile


def build_runner_command(
    repo_root: Path,
    source_run_dir: Path,
    output_root: Path,
    profile: str,
    *,
    model: str,
    queries: Path,
    questions_metadata: Path,
    expected_question_count: int = 50,
    force: bool = False,
    skip_general_llm: bool = False,
    skip_answer_generation: bool = False,
) -> list[str]:
    run_dir = build_profile_run_dir(output_root, profile)
    cmd = [
        sys.executable,
        str(repo_root / "evaluation" / "run_formal_50.py"),
        "--queries",
        str(queries),
        "--questions-metadata",
        str(questions_metadata),
        "--expected-question-count",
        str(expected_question_count),
        "--run-dir",
        str(run_dir),
        "--model",
        model,
        "--hybrid-profile",
        profile,
        "--reuse-corpora-dir",
        str(source_run_dir / "questions"),
    ]
    if force:
        cmd.append("--force")
    if skip_general_llm:
        cmd.append("--skip-general-llm")
    if skip_answer_generation:
        cmd.append("--skip-answer-generation")
    return cmd


def build_replay_manifest(
    source_run_dir: Path,
    output_root: Path,
    profiles: Iterable[str],
    *,
    model: str,
    queries: Path,
    questions_metadata: Path,
    expected_question_count: int = 50,
) -> dict[str, object]:
    return {
        "benchmark": "formal-v1-ae-replay",
        "status": "running",
        "replay_version": "v1",
        "source_run_dir": str(source_run_dir),
        "source_corpus_dir": str(source_run_dir / "questions"),
        "output_root": str(output_root),
        "model": model,
        "queries_file": str(queries),
        "questions_metadata_file": str(questions_metadata),
        "expected_question_count": expected_question_count,
        "profiles": list(profiles),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-dir", type=Path, default=DEFAULT_SOURCE_RUN_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--questions-metadata", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--expected-question-count", type=int, default=50)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--profile", action="append", choices=PROFILES, dest="profiles")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-general-llm", action="store_true")
    parser.add_argument("--skip-answer-generation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    profiles = args.profiles or list(PROFILES)
    source_questions_dir = args.source_run_dir / "questions"
    if not source_questions_dir.exists():
        raise FileNotFoundError(f"Frozen corpus directory not found: {source_questions_dir}")

    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest or (args.output_root / "ae_replay_manifest.json")
    manifest = build_replay_manifest(
        args.source_run_dir,
        args.output_root,
        profiles,
        model=args.model,
        queries=args.queries,
        questions_metadata=args.questions_metadata,
        expected_question_count=args.expected_question_count,
    )

    if args.dry_run:
        manifest["status"] = "dry_run"
        write_manifest(manifest_path, manifest)
        for profile in profiles:
            cmd = build_runner_command(
                repo_root,
                args.source_run_dir,
                args.output_root,
                profile,
                model=args.model,
                queries=args.queries,
                questions_metadata=args.questions_metadata,
                expected_question_count=args.expected_question_count,
                force=args.force,
                skip_general_llm=args.skip_general_llm,
                skip_answer_generation=args.skip_answer_generation,
            )
            print(" ".join(cmd))
        return

    write_manifest(manifest_path, manifest)

    for profile in profiles:
        run_dir = build_profile_run_dir(args.output_root, profile)
        run_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_runner_command(
            repo_root,
            args.source_run_dir,
            args.output_root,
            profile,
            model=args.model,
            queries=args.queries,
            questions_metadata=args.questions_metadata,
            expected_question_count=args.expected_question_count,
            force=args.force,
            skip_general_llm=args.skip_general_llm,
            skip_answer_generation=args.skip_answer_generation,
        )
        subprocess.run(cmd, cwd=repo_root, check=True)

    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_manifest(manifest_path, manifest)


if __name__ == "__main__":
    main()
