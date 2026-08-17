from evaluation.add_controlled_bridge_distractors import build_distractor_spec


def test_build_distractor_spec_keeps_only_canonical_bridge_mediators():
    base = {
        "questions": {
            "Q1": {
                "source_patterns": ["source"],
                "target_patterns": ["target"],
                "mediators": [{"name": "keep"}, {"name": "drop"}],
            }
        }
    }
    preflight = {
        "questions": [
            {
                "question_id": "Q1",
                "mediators": [
                    {"mediator": "keep", "bridge_eligible": True},
                    {"mediator": "drop", "bridge_eligible": False},
                ],
            }
        ]
    }
    queries = {
        "Q1": {
            "source_distractor_query": "source query",
            "target_distractor_query": "target query",
        }
    }

    result = build_distractor_spec(base, preflight, queries, 8)

    question = result["questions"]["Q1"]
    assert question["mediators"] == [{"name": "keep"}]
    assert question["max_distractors_per_side"] == 8
