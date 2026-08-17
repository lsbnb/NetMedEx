#!/usr/bin/env python3
"""Regenerate paired answers for completed zero-path checkpoints without rebuilding graphs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import networkx as nx

from run_formal_50 import (
    atomic_json,
    build_documents,
    format_text_context,
    generate_answer,
    init_llm,
)
from netmedex.pubtator_parser import PubTatorIO


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--only", action="append", required=True)
    args = parser.parse_args()

    llm = init_llm(args.model)
    for question_id in args.only:
        question_dir = args.run_dir / "questions" / question_id
        result_path = question_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            raise ValueError(f"{question_id} is not a complete checkpoint")
        if int(result.get("graph", {}).get("path_count", -1)) != 0:
            raise ValueError(f"{question_id} is not a zero-path checkpoint")

        collection = PubTatorIO.parse(question_dir / "corpus.pubtator")
        documents = build_documents(collection, nx.Graph())
        rag_view = SimpleNamespace(documents={document.pmid: document for document in documents})
        usage_before = dict(llm.completion_usage_totals)
        repaired_answers = {}
        for system in ("netmedex_hybrid_rag", "traditional_rag"):
            ranking = [
                (item["pmid"], float(item["score"]))
                for item in result["rankings"][system]
            ]
            repaired_answers[system] = generate_answer(
                llm,
                system=system,
                question=result["question"],
                language=result["language"],
                text_context=format_text_context(rag_view, ranking),
                graph_context="",
            )
        usage_after = dict(llm.completion_usage_totals)
        repair_usage = {
            field: usage_after.get(field, 0) - usage_before.get(field, 0)
            for field in set(usage_before) | set(usage_after)
        }
        backup_path = question_dir / "result.pre_zero_path_repair.json"
        if not backup_path.exists():
            backup_path.write_text(result_path.read_text(encoding="utf-8"), encoding="utf-8")
        original_usage = dict(result.get("token_usage", {}))
        result["answers"] = repaired_answers
        result["zero_path_answer_repair"] = {
            "reason": "Prevent fabricated graph-derived claims when evidence gate exposed no paths",
            "model": args.model,
            "token_usage": repair_usage,
        }
        result["token_usage"] = {
            field: original_usage.get(field, 0) + repair_usage.get(field, 0)
            for field in set(original_usage) | set(repair_usage)
        }
        atomic_json(result_path, result)
        print(question_id, repair_usage)


if __name__ == "__main__":
    main()
