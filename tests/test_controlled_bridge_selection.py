from evaluation.select_controlled_bridge_specs import (
    select_questions,
    select_questions_evidence_first,
)


def test_evidence_first_selection_preserves_all_proposed_mediators():
    proposal = {
        "questions": [{
            "question_id": "Q1", "source_patterns": ["source"],
            "target_patterns": ["target"],
            "target_side_forbidden_source_patterns": ["source alias"],
            "mediators": [{"name": "M1"}, {"name": "M2"}],
        }]
    }
    questions, audit = select_questions_evidence_first(proposal)
    assert [row["name"] for row in questions["Q1"]["mediators"]] == ["M1", "M2"]
    assert {row["reasons"][0] for row in audit} == {"pending_pmid_level_evidence_audit"}


def test_select_questions_applies_review_thresholds_and_exclusions():
    proposal = {
        "questions": [
            {
                "question_id": "Q1",
                "source_patterns": ["source"],
                "target_patterns": ["target"],
                "target_side_forbidden_source_patterns": ["source"],
                "mediators": [
                    {"name": "keep", "patterns": ["keep"]},
                    {"name": "low", "patterns": ["low"]},
                    {"name": "old", "patterns": ["old"]},
                ],
            }
        ]
    }
    review = {
        "reviews": [
            {
                "question_id": "Q1",
                "mediator": name,
                "polarity_coherent": 1,
                "canonical_entity_likely": 1,
                "endpoint_isolation_feasible": 1,
                "non_obviousness": non_obviousness,
                "research_utility": 4,
            }
            for name, non_obviousness in (("keep", 3), ("low", 2), ("old", 4))
        ]
    }

    questions, audit = select_questions(
        proposal, review, excluded_pairs={("Q1", "old")}
    )

    assert [row["name"] for row in questions["Q1"]["mediators"]] == ["keep"]
    by_mediator = {row["mediator"]: row for row in audit}
    assert by_mediator["keep"]["selected"] is True
    assert by_mediator["low"]["reasons"] == ["non_obviousness_below_threshold"]
    assert "previously_tested" in by_mediator["old"]["reasons"]
