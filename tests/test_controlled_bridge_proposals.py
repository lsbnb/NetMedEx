import pytest

from evaluation.propose_controlled_bridge_specs import normalize_pubmed_query_fields, validate


def test_normalize_pubmed_query_fields_repairs_only_unfielded_and_clause():
    assert normalize_pubmed_query_fields(
        "curcumin AND caspase-3[Title/Abstract]"
    ) == "curcumin[Title/Abstract] AND caspase-3[Title/Abstract]"


def valid_payload():
    return {
        "questions": [
            {
                "question_id": "Q1",
                "source_patterns": [r"\bsource\b"],
                "target_patterns": [r"\btarget\b"],
                "target_side_forbidden_source_patterns": [r"\bsource\b"],
                "mediators": [
                    {
                        "name": "STAT1",
                        "patterns": [r"\bstat1\b"],
                        "source_query": "source[Title/Abstract] AND STAT1[Title/Abstract]",
                        "target_query": "target[Title/Abstract] AND STAT1[Title/Abstract]",
                        "rationale": "A test bridge.",
                    }
                ],
            }
        ]
    }


def test_bridge_proposal_validation_accepts_complete_schema():
    result = validate(valid_payload(), {"Q1"})
    assert result["questions"][0]["mediators"][0]["name"] == "STAT1"


def test_bridge_proposal_validation_rejects_invalid_regex():
    payload = valid_payload()
    payload["questions"][0]["mediators"][0]["patterns"] = ["["]
    with pytest.raises(Exception):
        validate(payload, {"Q1"})


def test_latent_bridge_proposal_requires_signed_and_falsifiable_fields():
    payload = valid_payload()
    mediator = payload["questions"][0]["mediators"][0]
    mediator.update(
        relation_1="source increases STAT1",
        relation_2="STAT1 suppresses target",
        why_text_rag_may_miss="The evidence is split across unrelated literatures.",
        falsifiable_hypothesis="STAT1 knockout abolishes the source effect on target.",
    )
    result = validate(payload, {"Q1"}, require_latent_fields=True)
    assert result["questions"][0]["mediators"][0]["relation_1"]

    del mediator["falsifiable_hypothesis"]
    with pytest.raises(ValueError, match="falsifiable_hypothesis missing"):
        validate(payload, {"Q1"}, require_latent_fields=True)


def test_bridge_proposal_repairs_one_unfielded_query_side():
    payload = valid_payload()
    payload["questions"][0]["mediators"][0]["source_query"] = (
        "source AND STAT1[Title/Abstract]"
    )
    result = validate(payload, {"Q1"})
    assert result["questions"][0]["mediators"][0]["source_query"] == (
        "source[Title/Abstract] AND STAT1[Title/Abstract]"
    )


def test_bridge_proposal_still_rejects_query_without_two_fielded_concepts():
    payload = valid_payload()
    payload["questions"][0]["mediators"][0]["source_query"] = "STAT1"
    with pytest.raises(ValueError, match="must field both endpoint and mediator"):
        validate(payload, {"Q1"})
