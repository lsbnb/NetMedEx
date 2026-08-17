#!/usr/bin/env python3
"""Freeze AI-panel inputs and blinding keys with auditable SHA-256 checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_FILES = [
    Path("evaluation/formal/questions.csv"),
    Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra/system_outputs.csv"),
    Path("evaluation/formal/answer_ratings_worksheet.csv"),
    Path("evaluation/formal/answer_ratings_key.csv"),
    Path("evaluation/formal/hypothesis_ratings_worksheet.csv"),
    Path("evaluation/formal/hypothesis_ratings_key.csv"),
    Path("evaluation/formal/edge_ratings_worksheet_enriched.csv"),
    Path("evaluation/rate_ai_panel.py"),
    Path("evaluation/aggregate_ai_panel.py"),
    Path("evaluation/select_ai_panel_items.py"),
    Path("evaluation/summarize_edge_calibration.py"),
    Path("evaluation/AI_PANEL_PROTOCOL.md"),
    Path("evaluation/run_formal_50.py"),
    Path("netmedex/graph_rag.py"),
    Path("evaluation/formal/ai_panel/edge_ratings_gemini_v2.csv"),
    Path("evaluation/formal/ai_panel/edge_ratings_openai_gpt41_calibration.csv"),
    Path("evaluation/formal/ai_panel/edge_ratings_claude_haiku_calibration.csv"),
    Path("evaluation/formal/ai_panel/edge_rich_panel_consensus.csv"),
    Path("evaluation/formal/ai_panel/edge_rich_panel_summary.json"),
    Path("evaluation/formal/ai_panel/calibration_report.md"),
]


def digest(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/formal/ai_panel/panel_freeze_v1.json"),
    )
    args = parser.parse_args()
    files = args.file or DEFAULT_FILES
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze missing files: {missing}")
    payload = {
        "benchmark": "netmedex-multimodel-ai-panel-v1",
        "status": "frozen",
        "human_expert_review_claimed": False,
        "blinding": {
            "answer_key_private": True,
            "hypothesis_key_private": True,
            "judge_outputs_must_not_include_system_identity": True,
        },
        "files": [digest(path) for path in files],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
