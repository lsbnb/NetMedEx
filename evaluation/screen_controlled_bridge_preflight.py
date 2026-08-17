#!/usr/bin/env python3
"""Screen controlled bridge corpora before paid semantic graph construction."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evaluation.build_controlled_bridge_batch import (
    article_text,
    has_annotation_identifier,
    matches_any,
)
from netmedex.pubtator_parser import PubTatorIO


def evaluate_mediator(
    mediator_audit: dict,
    traditional_ranking: list[dict],
    *,
    top_k: int,
    evidence_audit: dict | None = None,
) -> dict:
    source_pmids = {str(pmid) for pmid in mediator_audit["accepted_pmids"]["source"]}
    target_pmids = {str(pmid) for pmid in mediator_audit["accepted_pmids"]["target"]}
    top_pmids = {
        str(item["pmid"])
        for item in traditional_ranking[:top_k]
    }
    source_in_top = sorted(source_pmids & top_pmids)
    target_in_top = sorted(target_pmids & top_pmids)
    source_outside = sorted(source_pmids - top_pmids)
    target_outside = sorted(target_pmids - top_pmids)
    both_sides_exposed = bool(source_in_top and target_in_top)
    one_side_exposed = bool(source_in_top) != bool(target_in_top)
    retrieval_eligible = bool(
        mediator_audit.get("bridge_eligible")
        and not (source_pmids & target_pmids)
        and one_side_exposed
        and (source_outside or target_outside)
    )
    evidence_eligible = True
    if evidence_audit is not None:
        evidence_eligible = bool(
            evidence_audit.get("source_relation_supported")
            and evidence_audit.get("target_relation_supported")
            and evidence_audit.get("signed_composition_valid")
            and evidence_audit.get("endpoint_semantically_isolated")
        )
    graph_build_eligible = retrieval_eligible and evidence_eligible
    reasons = []
    if not mediator_audit.get("bridge_eligible"):
        reasons.append("missing_endpoint_isolated_side")
    if source_pmids & target_pmids:
        reasons.append("source_target_document_overlap")
    if both_sides_exposed:
        reasons.append("complete_bridge_visible_in_text_top_k")
    if not source_in_top and not target_in_top:
        reasons.append("neither_bridge_side_visible_in_text_top_k")
    if retrieval_eligible:
        reasons.append("exactly_one_bridge_side_withheld_from_text_top_k")
    if evidence_audit is not None and not evidence_eligible:
        reasons.append("signed_hop_evidence_gate_failed")
    return {
        "mediator": mediator_audit["name"],
        "bridge_eligible": bool(mediator_audit.get("bridge_eligible")),
        "source_pmids": sorted(source_pmids),
        "target_pmids": sorted(target_pmids),
        "source_in_text_top_k": source_in_top,
        "target_in_text_top_k": target_in_top,
        "source_outside_text_top_k": source_outside,
        "target_outside_text_top_k": target_outside,
        "both_sides_exposed": both_sides_exposed,
        "retrieval_eligible": retrieval_eligible,
        "evidence_audit": evidence_audit,
        "evidence_eligible": evidence_eligible,
        "graph_build_eligible": graph_build_eligible,
        "reasons": reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-batch", type=Path, required=True)
    parser.add_argument("--text-run", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--evidence-audit",
        type=Path,
        help=(
            "Optional signed-hop audit JSON. When supplied, every mediator must "
            "pass both relations, signed composition, and semantic endpoint isolation."
        ),
    )
    args = parser.parse_args()

    evidence_audits = {}
    if args.evidence_audit:
        evidence_audits = json.loads(
            args.evidence_audit.read_text(encoding="utf-8")
        ).get("questions", {})

    question_rows = []
    mediator_rows = []
    for question_dir in sorted((args.corpus_batch / "questions").iterdir()):
        if not question_dir.is_dir():
            continue
        question_id = question_dir.name
        manifest_path = question_dir / "corpus_manifest.json"
        result_path = args.text_run / "questions" / question_id / "result.json"
        corpus_path = question_dir / "corpus.pubtator"
        if not (manifest_path.exists() and result_path.exists() and corpus_path.exists()):
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        collection = PubTatorIO.parse(corpus_path)
        source_patterns = list(manifest.get("source_patterns", []))
        target_patterns = list(manifest.get("target_patterns", []))
        source_identifiers = list(manifest.get("source_identifiers", []))
        target_identifiers = list(manifest.get("target_identifiers", []))
        endpoint_leaks = []
        for article in collection.articles:
            text = article_text(article)
            source_present = matches_any(text, source_patterns) or has_annotation_identifier(
                article, source_identifiers
            )
            target_present = matches_any(text, target_patterns) or has_annotation_identifier(
                article, target_identifiers
            )
            if source_present and target_present:
                endpoint_leaks.append(str(article.pmid))

        ranking = result.get("rankings", {}).get("traditional_rag", [])
        candidate_rows = [
            evaluate_mediator(
                row,
                ranking,
                top_k=args.top_k,
                evidence_audit=(
                    evidence_audits.get(question_id, {}).get(row["name"], {})
                    if args.evidence_audit
                    else None
                ),
            )
            for row in manifest.get("mediator_audit", [])
        ]
        for row in candidate_rows:
            mediator_rows.append(
                {
                    "question_id": question_id,
                    "mediator": row["mediator"],
                    "bridge_eligible": int(row["bridge_eligible"]),
                    "retrieval_eligible": int(row["retrieval_eligible"]),
                    "evidence_eligible": int(row["evidence_eligible"]),
                    "both_sides_exposed": int(row["both_sides_exposed"]),
                    "graph_build_eligible": int(
                        row["graph_build_eligible"] and not endpoint_leaks
                    ),
                    "source_in_text_top_k": ";".join(row["source_in_text_top_k"]),
                    "target_in_text_top_k": ";".join(row["target_in_text_top_k"]),
                    "source_outside_text_top_k": ";".join(
                        row["source_outside_text_top_k"]
                    ),
                    "target_outside_text_top_k": ";".join(
                        row["target_outside_text_top_k"]
                    ),
                    "reasons": ";".join(row["reasons"]),
                }
            )
        eligible = [
            row["mediator"]
            for row in candidate_rows
            if row["graph_build_eligible"] and not endpoint_leaks
        ]
        question_rows.append(
            {
                "question_id": question_id,
                "document_count": len(collection.articles),
                "endpoint_leaks": endpoint_leaks,
                "eligible_mediators": eligible,
                "graph_build_eligible": bool(eligible),
                "mediators": candidate_rows,
            }
        )

    summary = {
        "top_k": args.top_k,
        "question_count": len(question_rows),
        "graph_build_eligible_question_count": sum(
            row["graph_build_eligible"] for row in question_rows
        ),
        "questions": question_rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = list(mediator_rows[0]) if mediator_rows else ["question_id", "mediator"]
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mediator_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
