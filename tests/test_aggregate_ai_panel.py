import csv

from evaluation.aggregate_ai_panel import aggregate


def _write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_aggregate_answer_panel_maps_blinded_ids_and_counts_preferences(tmp_path):
    key = tmp_path / "key.csv"
    _write(
        key,
        [
            {"answer_id": "Q001-A", "question_id": "Q001", "system": "traditional_rag"},
            {"answer_id": "Q001-B", "question_id": "Q001", "system": "netmedex_hybrid_rag"},
        ],
    )
    rating_files = []
    for index, preference in enumerate(("Q001-B", "Q001-B", "tie"), 1):
        path = tmp_path / f"judge{index}.csv"
        rows = []
        for answer_id, score in (("Q001-A", 3), ("Q001-B", 5)):
            rows.append(
                {
                    "question_id": "Q001",
                    "answer_id": answer_id,
                    "rater_id": f"judge-{index}",
                    "correctness": score,
                    "completeness": score,
                    "relevance": score,
                    "grounding": score,
                    "mechanistic_coherence": score,
                    "research_value": score,
                    "preferred_answer_id": preference,
                    "notes": "",
                }
            )
        _write(path, rows)
        rating_files.append((f"judge-{index}", path))

    long_rows, consensus, summary = aggregate("answer", rating_files, key)
    assert len(long_rows) == 6
    assert len(consensus) == 2
    assert summary["pairwise_preferences"]["question_level_consensus"] == {
        "netmedex_hybrid_rag": 1
    }
    assert summary["paired_score_comparison"]["n_questions"] == 1
