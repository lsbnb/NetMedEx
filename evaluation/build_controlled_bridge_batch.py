#!/usr/bin/env python3
"""Build an endpoint-isolated corpus with a shared, withheld bridge entity."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from evaluation.run_formal_50 import pubmed_esearch
from netmedex.pubtator import PubTatorAPI
from netmedex.pubtator_data import PubTatorArticle, PubTatorCollection


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def article_text(article: PubTatorArticle) -> str:
    return f"{article.title}\n{article.abstract or ''}"


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def has_annotation_identifier(article: PubTatorArticle, identifiers: list[str]) -> bool:
    wanted = {str(identifier).casefold() for identifier in identifiers}
    return any(
        str(annotation.mesh).casefold() in wanted for annotation in article.annotations
    )


def matching_annotation_identifiers(
    article: PubTatorArticle, patterns: list[str]
) -> set[str]:
    identifiers = set()
    for annotation in article.annotations:
        if not matches_any(str(annotation.name), patterns):
            continue
        identifier = str(annotation.mesh).strip()
        if identifier not in {"", "-"}:
            identifiers.add(identifier)
    return identifiers


def eligible_for_side(
    article: PubTatorArticle,
    *,
    side: str,
    source_patterns: list[str],
    target_patterns: list[str],
    mediator_patterns: list[str],
    source_identifiers: list[str] | None = None,
    target_identifiers: list[str] | None = None,
    mediator_identifiers: list[str] | None = None,
    source_side_forbidden_target_patterns: list[str] | None = None,
    source_side_forbidden_target_identifiers: list[str] | None = None,
    target_side_forbidden_source_patterns: list[str] | None = None,
    target_side_forbidden_source_identifiers: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Apply the preregisterable endpoint-isolation rule to one article."""
    text = article_text(article)
    source_present = matches_any(text, source_patterns) or has_annotation_identifier(
        article, source_identifiers or []
    )
    target_present = matches_any(text, target_patterns) or has_annotation_identifier(
        article, target_identifiers or []
    )
    mediator_present = matches_any(text, mediator_patterns)
    if mediator_identifiers:
        # A canonical identifier on both sides is what lets the graph join two
        # otherwise isolated documents. Lexical presence alone is insufficient
        # because upstream NER can mistype HBx as Species or split orthologs.
        mediator_present = mediator_present and has_annotation_identifier(
            article, mediator_identifiers
        )
    reasons = []
    if not mediator_present:
        reasons.append("mediator_absent")
    if side == "source":
        if not source_present:
            reasons.append("source_absent")
        broad_target_leak = matches_any(
            text, source_side_forbidden_target_patterns or target_patterns
        ) or has_annotation_identifier(
            article,
            source_side_forbidden_target_identifiers or target_identifiers or [],
        )
        if target_present or broad_target_leak:
            reasons.append("target_leak")
    elif side == "target":
        if not target_present:
            reasons.append("target_absent")
        broad_source_leak = matches_any(
            text, target_side_forbidden_source_patterns or source_patterns
        ) or has_annotation_identifier(
            article,
            target_side_forbidden_source_identifiers or source_identifiers or [],
        )
        if broad_source_leak:
            reasons.append("source_leak")
    else:
        raise ValueError(f"Unknown side: {side}")
    return not reasons, reasons


def eligible_endpoint_distractor(
    article: PubTatorArticle,
    *,
    side: str,
    source_patterns: list[str],
    target_patterns: list[str],
    mediator_patterns: list[str],
    source_identifiers: list[str] | None = None,
    target_identifiers: list[str] | None = None,
    source_side_forbidden_target_patterns: list[str] | None = None,
    source_side_forbidden_target_identifiers: list[str] | None = None,
    target_side_forbidden_source_patterns: list[str] | None = None,
    target_side_forbidden_source_identifiers: list[str] | None = None,
) -> tuple[bool, list[str]]:
    text = article_text(article)
    source_present = matches_any(text, source_patterns) or has_annotation_identifier(
        article, source_identifiers or []
    )
    target_present = matches_any(text, target_patterns) or has_annotation_identifier(
        article, target_identifiers or []
    )
    reasons = []
    if matches_any(text, mediator_patterns):
        reasons.append("mediator_leak")
    if side == "source":
        if not source_present:
            reasons.append("source_absent")
        broad_target = matches_any(
            text, source_side_forbidden_target_patterns or target_patterns
        ) or has_annotation_identifier(
            article,
            source_side_forbidden_target_identifiers or target_identifiers or [],
        )
        if target_present or broad_target:
            reasons.append("target_leak")
    elif side == "target":
        if not target_present:
            reasons.append("target_absent")
        broad_source = matches_any(
            text, target_side_forbidden_source_patterns or source_patterns
        ) or has_annotation_identifier(
            article,
            target_side_forbidden_source_identifiers or source_identifiers or [],
        )
        if broad_source:
            reasons.append("source_leak")
    else:
        raise ValueError(f"Unknown side: {side}")
    return not reasons, reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-batch",
        type=Path,
        default=Path("evaluation/formal/bridge_withheld_dev_v1"),
    )
    parser.add_argument("--query-spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument(
        "--skip-ineligible",
        action="store_true",
        help="Persist negative audits and continue instead of aborting the batch.",
    )
    args = parser.parse_args()

    spec = json.loads(args.query_spec.read_text(encoding="utf-8"))
    query_by_id = {
        row["question_id"]: dict(row)
        for row in read_csv(args.source_batch / "queries.csv")
    }
    metadata_by_id = {
        row["question_id"]: dict(row)
        for row in read_csv(args.source_batch / "questions_metadata.csv")
    }
    selected_ids = args.question_id or list(spec["questions"])
    missing = sorted(
        (set(selected_ids) - set(query_by_id))
        | (set(selected_ids) - set(spec["questions"]))
    )
    if missing:
        raise ValueError(f"Unknown question IDs: {missing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    query_rows = [query_by_id[qid] for qid in selected_ids]
    metadata_rows = [metadata_by_id[qid] for qid in selected_ids]
    write_csv(args.output_dir / "queries.csv", query_rows)
    write_csv(args.output_dir / "questions_metadata.csv", metadata_rows)
    artifacts = [args.output_dir / "queries.csv", args.output_dir / "questions_metadata.csv"]
    question_records = []

    for question_id in selected_ids:
        question_spec = spec["questions"][question_id]
        max_candidates = int(question_spec.get("max_candidates_per_query", 30))
        max_per_side = int(question_spec.get("max_articles_per_side", 3))
        source_patterns = list(question_spec["source_patterns"])
        target_patterns = list(question_spec["target_patterns"])
        source_identifiers = list(question_spec.get("source_identifiers", []))
        target_identifiers = list(question_spec.get("target_identifiers", []))
        selected_articles: list[PubTatorArticle] = []
        selected_pmids: set[str] = set()
        mediator_audit = []

        for mediator in question_spec["mediators"]:
            query_pmids = {
                "source": pubmed_esearch(mediator["source_query"], max_candidates),
                "target": pubmed_esearch(mediator["target_query"], max_candidates),
            }
            requested = []
            for side in ("source", "target"):
                for pmid in query_pmids[side]:
                    if pmid not in requested:
                        requested.append(pmid)
            collection = PubTatorAPI(
                query=None,
                pmid_list=requested,
                sort="score",
                request_format="biocjson",
                max_articles=len(requested),
                full_text=False,
                queue=None,
            ).run()
            article_by_pmid = {str(article.pmid): article for article in collection.articles}
            accepted_by_side: dict[str, list[str]] = {"source": [], "target": []}
            rejected_by_side: dict[str, dict[str, list[str]]] = {
                "source": {},
                "target": {},
            }
            for side in ("source", "target"):
                for pmid in query_pmids[side]:
                    article = article_by_pmid.get(str(pmid))
                    if article is None:
                        rejected_by_side[side][str(pmid)] = ["fetch_missing"]
                        continue
                    eligible, reasons = eligible_for_side(
                        article,
                        side=side,
                        source_patterns=source_patterns,
                        target_patterns=target_patterns,
                        mediator_patterns=list(mediator["patterns"]),
                        source_identifiers=source_identifiers,
                        target_identifiers=target_identifiers,
                        mediator_identifiers=list(mediator.get("identifiers", [])),
                        source_side_forbidden_target_patterns=list(
                            question_spec.get(
                                "source_side_forbidden_target_patterns", []
                            )
                        ),
                        source_side_forbidden_target_identifiers=list(
                            question_spec.get(
                                "source_side_forbidden_target_identifiers", []
                            )
                        ),
                        target_side_forbidden_source_patterns=list(
                            question_spec.get(
                                "target_side_forbidden_source_patterns", []
                            )
                        ),
                        target_side_forbidden_source_identifiers=list(
                            question_spec.get(
                                "target_side_forbidden_source_identifiers", []
                            )
                        ),
                    )
                    if not eligible:
                        rejected_by_side[side][str(pmid)] = reasons
                        continue
                    if str(pmid) in selected_pmids:
                        rejected_by_side[side][str(pmid)] = ["duplicate"]
                        continue
                    accepted_by_side[side].append(str(pmid))
                    selected_pmids.add(str(pmid))
                    selected_articles.append(article)
                    if len(accepted_by_side[side]) >= max_per_side:
                        break
            mediator_patterns = list(mediator["patterns"])
            annotation_ids_by_side = {
                side: sorted(
                    set().union(
                        *(
                            matching_annotation_identifiers(
                                article_by_pmid[pmid], mediator_patterns
                            )
                            for pmid in accepted_by_side[side]
                        )
                    )
                    if accepted_by_side[side]
                    else set()
                )
                for side in ("source", "target")
            }
            shared_mediator_identifiers = sorted(
                set(annotation_ids_by_side["source"])
                & set(annotation_ids_by_side["target"])
            )
            mediator_audit.append(
                {
                    "name": mediator["name"],
                    "queries": {
                        "source": mediator["source_query"],
                        "target": mediator["target_query"],
                    },
                    "candidate_pmids": query_pmids,
                    "accepted_pmids": accepted_by_side,
                    "annotation_identifiers": annotation_ids_by_side,
                    "shared_mediator_identifiers": shared_mediator_identifiers,
                    "rejected_pmids": rejected_by_side,
                    "bridge_eligible": bool(
                        accepted_by_side["source"] and accepted_by_side["target"]
                        and shared_mediator_identifiers
                    ),
                }
            )

        distractor_audit = None
        distractor_queries = {
            side: str(question_spec.get(f"{side}_distractor_query", "")).strip()
            for side in ("source", "target")
        }
        if all(distractor_queries.values()):
            max_distractors = int(question_spec.get("max_distractors_per_side", 10))
            all_mediator_patterns = [
                pattern
                for mediator in question_spec["mediators"]
                for pattern in mediator["patterns"]
            ]
            candidate_pmids = {
                side: pubmed_esearch(query, max(max_candidates, max_distractors * 3))
                for side, query in distractor_queries.items()
            }
            requested = []
            for side in ("source", "target"):
                for pmid in candidate_pmids[side]:
                    if pmid not in requested:
                        requested.append(pmid)
            collection = PubTatorAPI(
                query=None,
                pmid_list=requested,
                sort="score",
                request_format="biocjson",
                max_articles=len(requested),
                full_text=False,
                queue=None,
            ).run()
            article_by_pmid = {str(article.pmid): article for article in collection.articles}
            accepted_distractors = {"source": [], "target": []}
            rejected_distractors = {"source": {}, "target": {}}
            for side in ("source", "target"):
                for pmid in candidate_pmids[side]:
                    article = article_by_pmid.get(str(pmid))
                    if article is None:
                        rejected_distractors[side][str(pmid)] = ["fetch_missing"]
                        continue
                    eligible, reasons = eligible_endpoint_distractor(
                        article,
                        side=side,
                        source_patterns=source_patterns,
                        target_patterns=target_patterns,
                        mediator_patterns=all_mediator_patterns,
                        source_identifiers=source_identifiers,
                        target_identifiers=target_identifiers,
                        source_side_forbidden_target_patterns=list(
                            question_spec.get(
                                "source_side_forbidden_target_patterns", []
                            )
                        ),
                        source_side_forbidden_target_identifiers=list(
                            question_spec.get(
                                "source_side_forbidden_target_identifiers", []
                            )
                        ),
                        target_side_forbidden_source_patterns=list(
                            question_spec.get(
                                "target_side_forbidden_source_patterns", []
                            )
                        ),
                        target_side_forbidden_source_identifiers=list(
                            question_spec.get(
                                "target_side_forbidden_source_identifiers", []
                            )
                        ),
                    )
                    if not eligible:
                        rejected_distractors[side][str(pmid)] = reasons
                        continue
                    if str(pmid) in selected_pmids:
                        rejected_distractors[side][str(pmid)] = ["duplicate"]
                        continue
                    accepted_distractors[side].append(str(pmid))
                    selected_pmids.add(str(pmid))
                    selected_articles.append(article)
                    if len(accepted_distractors[side]) >= max_distractors:
                        break
            distractor_audit = {
                "queries": distractor_queries,
                "candidate_pmids": candidate_pmids,
                "accepted_pmids": accepted_distractors,
                "rejected_pmids": rejected_distractors,
            }

        eligible_mediators = [
            row["name"] for row in mediator_audit if row["bridge_eligible"]
        ]
        question_dir = args.output_dir / "questions" / question_id
        question_dir.mkdir(parents=True, exist_ok=True)
        corpus_path = question_dir / "corpus.pubtator"
        corpus = PubTatorCollection(headers=[], articles=selected_articles)
        corpus_path.write_text(
            corpus.to_pubtator_str(annotation_use_identifier_name=True),
            encoding="utf-8",
        )
        manifest = {
            "question_id": question_id,
            "status": "eligible" if eligible_mediators else "ineligible",
            "corpus_strategy": "controlled_endpoint_isolated_shared_bridge",
            "same_corpus_for_text_and_hybrid": True,
            "mediators_withheld_from_system_query": True,
            "source_patterns": source_patterns,
            "target_patterns": target_patterns,
            "source_identifiers": source_identifiers,
            "target_identifiers": target_identifiers,
            "source_side_forbidden_target_patterns": question_spec.get(
                "source_side_forbidden_target_patterns", []
            ),
            "source_side_forbidden_target_identifiers": question_spec.get(
                "source_side_forbidden_target_identifiers", []
            ),
            "target_side_forbidden_source_patterns": question_spec.get(
                "target_side_forbidden_source_patterns", []
            ),
            "target_side_forbidden_source_identifiers": question_spec.get(
                "target_side_forbidden_source_identifiers", []
            ),
            "eligible_mediators": eligible_mediators,
            "mediator_audit": mediator_audit,
            "distractor_audit": distractor_audit,
            "fetched_pmids": [str(article.pmid) for article in selected_articles],
        }
        manifest_path = question_dir / "corpus_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.extend([corpus_path, manifest_path])
        question_records.append(
            {
                "question_id": question_id,
                "document_count": len(selected_articles),
                "eligible_mediators": eligible_mediators,
                "graph_build_eligible": bool(eligible_mediators),
                "corpus_sha256": sha256(corpus_path),
            }
        )
        if not eligible_mediators and not args.skip_ineligible:
            raise RuntimeError(
                f"{question_id}: no endpoint-isolated mediator has both sides"
            )

    freeze = {
        "name": spec["name"],
        "status": "frozen_before_semantic_graph_generation",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "independent_holdout": False,
        "same_corpus_for_text_and_hybrid": True,
        "mediators_used_only_for_corpus_construction": True,
        "endpoint_co_mention_forbidden_per_article": True,
        "query_spec": str(args.query_spec),
        "query_spec_sha256": sha256(args.query_spec),
        "questions": question_records,
        "checksums": {
            str(path.relative_to(args.output_dir)): sha256(path) for path in artifacts
        },
    }
    (args.output_dir / "freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(question_records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
