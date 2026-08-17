#!/usr/bin/env python3
"""Audit structural invariants for a B/C1/C2/D1/D2/D3/Oracle run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ARMS = ("B", "C1", "C2", "D1", "D2", "D3", "Oracle")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _answer(result: dict[str, Any]) -> str:
    answers = result.get("answers", {})
    if len(answers) != 1:
        raise ValueError(f"expected exactly one answer, found {list(answers)}")
    return next(iter(answers.values()))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def audit(run_dir: Path, expected_count: int) -> dict[str, Any]:
    errors: list[str] = []
    results: dict[str, dict[str, dict[str, Any]]] = {}
    arm_summary: dict[str, Any] = {}

    for arm in ARMS:
        question_dir = run_dir / f"arm_{arm}" / "questions"
        arm_results: dict[str, dict[str, Any]] = {}
        for result_path in sorted(question_dir.glob("*/result.json")):
            result = _load(result_path)
            question_id = str(result.get("question_id", result_path.parent.name))
            arm_results[question_id] = result
        results[arm] = arm_results
        statuses = Counter(str(item.get("status")) for item in arm_results.values())
        if len(arm_results) != expected_count:
            errors.append(f"{arm}: expected {expected_count} results, found {len(arm_results)}")
        if statuses != Counter({"complete": expected_count}):
            errors.append(f"{arm}: unexpected statuses {dict(statuses)}")
        arm_summary[arm] = {"result_count": len(arm_results), "statuses": dict(statuses)}

    baseline = {qid: _answer(item) for qid, item in results["B"].items()}
    intervention_sets: dict[str, list[str]] = {}
    unsupported_claims: dict[str, int] = {}
    fallback_exact_matches: dict[str, int] = {}
    selected_path_counts: dict[str, int] = {}
    finish_reasons: dict[str, Counter[str]] = {}
    oracle_audits: dict[str, Any] = {}

    for arm in ARMS:
        interventions: list[str] = []
        unsupported = 0
        exact_fallbacks = 0
        selected_count = 0
        arm_finish_reasons: Counter[str] = Counter()
        for question_id, result in results[arm].items():
            exposure = result.get("evidence_exposure", {})
            decision = exposure.get("integration_decision", {})
            mode = decision.get("mode", "traditional_rag" if arm == "B" else None)
            if mode == "full_hybrid":
                interventions.append(question_id)

            verification = result.get("claim_verification", {})
            unsupported += int(verification.get("unsupported_claim_count", 0) or 0)

            for reason in result.get("answer_finish_reasons", {}).values():
                normalized_reason = str(reason).lower()
                arm_finish_reasons[normalized_reason] += 1
                if normalized_reason in {"length", "max_tokens"}:
                    errors.append(f"{arm}/{question_id}: answer ended because of token limit")

            is_fallback = bool(exposure.get("fallback_answer_reused"))
            if arm != "B" and is_fallback:
                expected = baseline.get(question_id)
                observed = _answer(result)
                if expected is None or observed != expected:
                    errors.append(
                        f"{arm}/{question_id}: fallback answer differs from B "
                        f"({_sha256(observed)} != {_sha256(expected or '')})"
                    )
                else:
                    exact_fallbacks += 1

            signatures = [str(item) for item in exposure.get("answer_context_path_signatures", [])]
            selected_count += len(signatures)
            path_by_signature = {
                str(path.get("path_signature")): path
                for path in result.get("graph", {}).get("paths", [])
            }
            for signature in signatures:
                path = path_by_signature.get(signature)
                if path is None:
                    errors.append(f"{arm}/{question_id}: selected path {signature} not found")
                    continue
                if not path.get("claim_safe"):
                    errors.append(f"{arm}/{question_id}: selected path {signature} is not claim-safe")
                # Alignment eligibility is defined by complete endpoint and requested-bridge
                # coverage.  The composite alignment score additionally penalizes extra
                # bridge nodes, so a valid path can intentionally score below 1.0.  D1 is
                # the preregistered "all safe paths" contrast and therefore does not apply
                # the incremental/query-alignment filter at answer-path selection time.
                if arm != "D1" and (
                    float(path.get("query_endpoint_coverage", 0.0)) < 1.0
                    or float(path.get("requested_bridge_coverage", 0.0)) < 1.0
                ):
                    errors.append(f"{arm}/{question_id}: selected path {signature} is query-misaligned")
                if arm in {"D2", "D3"} and path.get("incremental_value_class") != "graph_incremental_candidate":
                    errors.append(f"{arm}/{question_id}: selected path {signature} is not incremental")

            if arm == "Oracle" and mode == "full_hybrid":
                oracle = exposure.get("oracle_path_selection", {})
                requested = [str(item) for item in oracle.get("requested", [])]
                selected = [str(item) for item in oracle.get("selected", [])]
                oracle_audits[question_id] = {
                    "requested": requested,
                    "selected": selected,
                    "raw_response_count": len(oracle.get("raw_responses", [])),
                }
                if not selected or any(item not in requested for item in selected):
                    errors.append(f"Oracle/{question_id}: invalid local-oracle selection")
                if selected != signatures:
                    errors.append(f"Oracle/{question_id}: oracle selection differs from answer paths")

        intervention_sets[arm] = sorted(interventions)
        unsupported_claims[arm] = unsupported
        fallback_exact_matches[arm] = exact_fallbacks
        selected_path_counts[arm] = selected_count
        finish_reasons[arm] = arm_finish_reasons
        arm_summary[arm].update(
            {
                "intervention_question_ids": sorted(interventions),
                "unsupported_claim_count": unsupported,
                "exact_fallback_count": exact_fallbacks,
                "selected_path_count": selected_count,
                "answer_finish_reasons": dict(arm_finish_reasons),
            }
        )

    expected_interventions = intervention_sets["D2"]
    for arm in ("C1", "C2", "D1", "D3", "Oracle"):
        if intervention_sets[arm] != expected_interventions:
            errors.append(
                f"{arm}: intervention set {intervention_sets[arm]} differs from D2 "
                f"{expected_interventions}"
            )
    if any(unsupported_claims.values()):
        errors.append(f"unsupported graph claims detected: {unsupported_claims}")

    combined_path = run_dir / "hybrid_gain_system_outputs.csv"
    with combined_path.open(newline="", encoding="utf-8") as handle:
        combined_count = sum(1 for _ in csv.DictReader(handle))
    expected_combined = expected_count * len(ARMS)
    if combined_count != expected_combined:
        errors.append(
            f"combined output: expected {expected_combined} rows, found {combined_count}"
        )

    return {
        "status": "pass" if not errors else "fail",
        "run_dir": str(run_dir),
        "expected_question_count": expected_count,
        "combined_output_count": combined_count,
        "arms": arm_summary,
        "shared_intervention_question_ids": expected_interventions,
        "oracle_audits": oracle_audits,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-question-count", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit(args.run_dir, args.expected_question_count)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
