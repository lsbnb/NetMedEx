#!/usr/bin/env python3
"""Regenerate only blank answers in otherwise complete formal checkpoints."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from evaluation.run_formal_50 import (
        SYSTEMS,
        atomic_json,
        compile_outputs,
        generate_answer,
        init_llm,
        load_queries,
    )
except ModuleNotFoundError:
    from run_formal_50 import (
        SYSTEMS,
        atomic_json,
        compile_outputs,
        generate_answer,
        init_llm,
        load_queries,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("evaluation/formal/formal_run_queries.csv"),
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra"),
    )
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument(
        "--system", choices=SYSTEMS, default="general_llm"
    )
    args = parser.parse_args()

    lock_handle = (args.run_dir / ".run.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"Another runner is active for {args.run_dir}") from exc
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()

    queries = load_queries(args.queries)
    query_by_id = {row["question_id"]: row for row in queries}
    targets = []
    for question_id in sorted(query_by_id):
        result_path = args.run_dir / "questions" / question_id / "result.json"
        if not result_path.exists():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            continue
        if not str(result.get("answers", {}).get(args.system, "")).strip():
            targets.append(question_id)

    manifest_path = args.run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["model"] != args.model:
        raise ValueError("Existing run uses a different model")
    started_at = datetime.now(timezone.utc).isoformat()
    attempts = manifest.setdefault("attempts", [])
    attempt = {
        "attempt_id": f"attempt-{len(attempts) + 1:03d}",
        "type": "answer-only-repair",
        "system": args.system,
        "started_at": started_at,
        "selected_questions": targets,
        "status": "running",
    }
    attempts.append(attempt)
    manifest["status"] = "running"
    manifest["last_resumed_at"] = started_at
    atomic_json(manifest_path, manifest)

    llm = init_llm(args.model)
    for index, question_id in enumerate(targets, start=1):
        row = query_by_id[question_id]
        result_path = args.run_dir / "questions" / question_id / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        print(f"[{index}/{len(targets)}] Repairing {args.system} for {question_id}", flush=True)
        answer = ""
        started = time.monotonic()
        for retry in range(1, 4):
            answer = generate_answer(
                llm,
                system=args.system,
                question=row["question"],
                language=row["language"],
            )
            if answer.strip():
                break
            print(f"{question_id} empty answer, retry {retry}/3", flush=True)
        if not answer.strip():
            attempt["status"] = "failed"
            attempt["error"] = f"{question_id} remained empty after 3 attempts"
            attempt["failed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(manifest_path, manifest)
            raise RuntimeError(attempt["error"])

        result["answers"][args.system] = answer
        result.setdefault("timings_seconds", {})[
            f"answer_{args.system}"
        ] = time.monotonic() - started
        result.setdefault("answer_repair_history", []).append(
            {
                "system": args.system,
                "model": args.model,
                "repaired_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        atomic_json(result_path, result)
        complete, failed = compile_outputs(
            args.run_dir, queries, manifest["run_id"]
        )
        manifest["completed_questions"] = complete
        manifest["failed_questions"] = failed
        manifest["last_checkpoint_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(manifest_path, manifest)

    complete, failed = compile_outputs(args.run_dir, queries, manifest["run_id"])
    completed_at = datetime.now(timezone.utc).isoformat()
    manifest["completed_questions"] = complete
    manifest["failed_questions"] = failed
    manifest["status"] = "complete" if complete == len(queries) and failed == 0 else "incomplete"
    manifest["completed_at"] = completed_at
    attempt["status"] = manifest["status"]
    attempt["completed_at"] = completed_at
    attempt["completed_questions_after_attempt"] = complete
    attempt["failed_questions_after_attempt"] = failed
    atomic_json(manifest_path, manifest)
    print(f"Answer repair finished: complete={complete} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
