#!/usr/bin/env python3
"""Freeze a 20-item Tier-A path-enriched benchmark without reading answer scores.

This is an efficacy-set builder, not a representative-sampling builder.  Every item is
defined by one pre-existing, evidence-gated path.  The original all-question benchmark
must remain the intention-to-treat estimate of overall system performance.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation/formal/path_positive_20_v1"

# Frozen before answer generation.  Five direct paths and fifteen multi-hop paths,
# twelve of which cross PMID boundaries.  Signatures come only from graph retrieval.
SELECTION = [
    ("90b8236c9fc91254", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q001/result.json"),
    ("a48c9071e59e7e2d", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q004/result.json"),
    ("31f26bea18c6474b", "evaluation/formal/runs/formal-v1-ae-replay-terra-graphs-luna-answers-v1/D_two_hop/questions/Q005/result.json"),
    ("decd42689d2018ff", "evaluation/formal/runs/formal-v1-ae-replay-terra-graphs-luna-answers-v1/D_two_hop/questions/Q007/result.json"),
    ("6b5618526adbdfc6", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q011/result.json"),
    ("726c66af94dc377a", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q001/result.json"),
    ("365a23ddd1189115", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q004/result.json"),
    ("6c6fb0bc25292607", "evaluation/formal/runs/controlled-bridge-bw010-distractors-v1-retrieval/questions/BW010/result.json"),
    ("08b1ba895a663928", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q008/result.json"),
    ("3a03360fb323a847", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q008/result.json"),
    ("499767e1e1703963", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q037/result.json"),
    ("904d67f239f8cb5b", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q037/result.json"),
    ("c37d8f7746362201", "evaluation/formal/runs/abcd20_path_replay_v2/questions/Q037/result.json"),
    ("fa3452511ed7b713", "evaluation/formal/runs/controlled-bridge-reviewed-distractors-v1-bw010-retrieval/questions/BW010/result.json"),
    ("9ed6292d75395474", "evaluation/formal/runs/bridge-withheld-endpoint-only-bw003-v1-retrieval/questions/BW003/result.json"),
    ("57416f2f7b9449cc", "evaluation/formal/runs/bridge-withheld-endpoint-only-bw003-v1-retrieval/questions/BW003/result.json"),
    ("7e9fef4360d43ca1", "evaluation/formal/runs/controlled-bridge-pilot-v3-four-hop-replay/questions/BW008/result.json"),
    ("5724030babeb80f1", "evaluation/temporal_holdout_pilot/discovery_run_v2_date_audited/questions/TH001/result.json"),
    ("67837b72691d2015", "evaluation/temporal_holdout_pilot/discovery_run_v2_date_audited/questions/TH001/result.json"),
    ("5392416d32ad795a", "evaluation/temporal_holdout_pilot/discovery_run_v2_date_audited/questions/TH001/result.json"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_tier_a(path: dict) -> bool:
    supports = path.get("edge_supports") or []
    return (
        path.get("gate_tier") == "A"
        and path.get("claim_safe") is True
        and bool(supports)
        and all(
        support.get("support_tier") == "A"
        and float(support.get("selected_confidence") or 0) >= 0.8
        and bool(support.get("selected_quote"))
        and bool(support.get("quote_relation_aligned"))
            for support in supports
        )
    )


def category(path: dict) -> str:
    hop_count = int(path.get("hop_count") or len(path.get("relations") or []))
    pmids = {
        str(pmid)
        for edge_pmids in path.get("edge_pmids", [])
        for pmid in (edge_pmids or [])
        if pmid
    }
    if hop_count == 1:
        return "direct"
    return "multi_hop_cross_pmid" if len(pmids) > 1 else "multi_hop_same_pmid"


def make_question(path: dict) -> str:
    names = path["names"]
    relations = path["relations"]
    if len(relations) == 1:
        return (
            f"What evidence supports the claim that {names[0]} {relations[0]} "
            f"{names[-1]}, and what are the important study-context limitations?"
        )
    bridges = ", ".join(names[1:-1])
    return (
        f"What evidence supports a mechanistic path from {names[0]} to {names[-1]} "
        f"through {bridges}? Distinguish evidence for each hop from overall inference."
    )


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    corpus_root = OUTPUT / "frozen_corpora"
    exposure_root = OUTPUT / "frozen_exposures"
    expanded_exposure_root = OUTPUT / "frozen_exposures_expanded"
    corpus_root.mkdir(exist_ok=True)
    exposure_root.mkdir(exist_ok=True)
    expanded_exposure_root.mkdir(exist_ok=True)

    question_rows: list[dict] = []
    query_rows: list[dict] = []
    audit_rows: list[dict] = []
    manifest_items: list[dict] = []

    for index, (signature, relative_result) in enumerate(SELECTION, 1):
        qid = f"PP{index:03d}"
        source_result = ROOT / relative_result
        result = json.loads(source_result.read_text(encoding="utf-8"))
        paths = (result.get("graph") or {}).get("paths") or []
        matches = [p for p in paths if p.get("path_signature") == signature]
        if not matches:
            raise RuntimeError(f"Path {signature} is absent from {source_result}")
        # Some legacy result files repeated the same ranked path verbatim.  The frozen
        # signature identifies the path; duplicate rows must not create extra items.
        selected = matches[0]
        if not is_tier_a(selected):
            raise RuntimeError(f"Selected path is not current Tier A: {signature}")

        source_corpus = source_result.parent / "corpus.pubtator"
        if not source_corpus.exists():
            raise FileNotFoundError(source_corpus)
        item_corpus_dir = corpus_root / qid
        item_exposure_dir = exposure_root / qid
        item_expanded_exposure_dir = expanded_exposure_root / qid
        item_corpus_dir.mkdir(exist_ok=True)
        item_exposure_dir.mkdir(exist_ok=True)
        item_expanded_exposure_dir.mkdir(exist_ok=True)
        shutil.copyfile(source_corpus, item_corpus_dir / "corpus.pubtator")

        frozen = {
            "status": "complete",
            "question_id": qid,
            "graph": {
                "node_count": (result.get("graph") or {}).get("node_count", 0),
                "edge_count": (result.get("graph") or {}).get("edge_count", 0),
                "path_count": 1,
                "paths": [selected],
                "pre_gate_candidate_count": 1,
                "pre_gate_candidates": [selected],
            },
            "evidence_exposure": {
                "profile": "H_evidence_gated_four_hop",
                "routed_profile": "H_evidence_gated_four_hop",
                "selection_frozen_before_answers": True,
                "source_result": relative_result,
            },
        }
        exposure_path = item_exposure_dir / "result.json"
        exposure_path.write_text(
            json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        selected_names = selected.get("names") or []
        start_name, end_name = selected_names[0].casefold(), selected_names[-1].casefold()
        expanded_by_signature = {}
        for candidate in paths:
            names = candidate.get("names") or []
            endpoint_match = (
                len(names) >= 2
                and names[0].casefold() == start_name
                and names[-1].casefold() == end_name
            )
            if endpoint_match and is_tier_a(candidate):
                expanded_by_signature[candidate["path_signature"]] = candidate
        expanded_paths = list(expanded_by_signature.values())
        expanded_frozen = json.loads(json.dumps(frozen))
        expanded_frozen["graph"]["paths"] = expanded_paths
        expanded_frozen["graph"]["path_count"] = len(expanded_paths)
        expanded_frozen["graph"]["pre_gate_candidates"] = expanded_paths
        expanded_frozen["graph"]["pre_gate_candidate_count"] = len(expanded_paths)
        expanded_frozen["evidence_exposure"]["expanded_reliable_pool"] = True
        expanded_exposure_path = item_expanded_exposure_dir / "result.json"
        expanded_exposure_path.write_text(
            json.dumps(expanded_frozen, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        names = selected["names"]
        pmids = sorted(
            {
                str(pmid)
                for edge_pmids in selected.get("edge_pmids", [])
                for pmid in (edge_pmids or [])
                if pmid
            }
        )
        question = make_question(selected)
        domain = result.get("domain") or "biomedicine"
        source_query = result.get("pubmed_query") or result.get("effective_pubmed_query") or ""
        question_rows.append(
            {
                "question_id": qid,
                "domain": domain,
                "question": question,
                "question_type": "mechanism",
                "expected_concepts": "; ".join(names),
                "gold_pmids": "",
                "minimum_answer_criteria": "Cite evidence for each hop and label the endpoint conclusion as inference when no direct edge is shown.",
                "curator_notes": "Path-enriched efficacy item; excluded from representative ITT claims.",
            }
        )
        query_rows.append(
            {
                "question_id": qid,
                "domain": domain,
                "question": question,
                "pubmed_query": source_query,
                "language": "English",
            }
        )
        cat = category(selected)
        audit_rows.append(
            {
                "question_id": qid,
                "source_question_id": result.get("question_id", ""),
                "category": cat,
                "hop_count": selected.get("hop_count", len(selected.get("relations") or [])),
                "path_signature": signature,
                "path": " -> ".join(names),
                "relations": " -> ".join(selected.get("relations") or []),
                "supporting_pmids": ";".join(pmids),
                "source_result": relative_result,
            }
        )
        manifest_items.append(
            {
                "question_id": qid,
                "path_signature": signature,
                "category": cat,
                "source_result_sha256": sha256(source_result),
                "corpus_sha256": sha256(item_corpus_dir / "corpus.pubtator"),
                "exposure_sha256": sha256(exposure_path),
                "expanded_exposure_sha256": sha256(expanded_exposure_path),
                "expanded_claim_safe_path_count": len(expanded_paths),
            }
        )

    write_csv(OUTPUT / "questions.csv", question_rows, list(question_rows[0]))
    write_csv(OUTPUT / "queries.csv", query_rows, list(query_rows[0]))
    write_csv(OUTPUT / "candidate_audit.csv", audit_rows, list(audit_rows[0]))
    counts: dict[str, int] = {}
    for row in audit_rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    manifest = {
        "benchmark_id": "path-positive-20-v1",
        "purpose": "conditional KG efficacy among current Tier-A path-positive items",
        "not_for": "representative overall-performance or path-coverage claims",
        "selection_reads_answers_or_judgments": False,
        "tier_a_rule": "quote present; quote-relation aligned; confidence >= 0.8 on every edge",
        "counts": counts,
        "items": manifest_items,
    }
    (OUTPUT / "selection_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(OUTPUT), "counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
