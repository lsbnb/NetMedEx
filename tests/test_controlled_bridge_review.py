import pytest

from evaluation.review_controlled_bridge_specs import validate


def row(**updates):
    value = {
        "question_id": "Q1",
        "mediator": "STAT1",
        "accept": 1,
        "polarity_coherent": 1,
        "canonical_entity_likely": 1,
        "endpoint_isolation_feasible": 1,
        "non_obviousness": 4,
        "research_utility": 4,
        "reason": "Suitable.",
    }
    value.update(updates)
    return value


def test_review_validation_applies_strict_consensus_gate():
    result = validate({"reviews": [row()]}, {("Q1", "STAT1")})
    assert result[0]["passes_consensus_gate"] == 1


def test_review_validation_rejects_high_value_but_bad_polarity():
    result = validate(
        {"reviews": [row(polarity_coherent=0, non_obviousness=5)]},
        {("Q1", "STAT1")},
    )
    assert result[0]["passes_consensus_gate"] == 0


def test_review_validation_requires_every_candidate():
    with pytest.raises(ValueError, match="Missing reviews"):
        validate({"reviews": [row()]}, {("Q1", "STAT1"), ("Q2", "AMPK")})


def test_hidden_review_gate_requires_answer_incrementality_and_nontextbook_status():
    hidden = row(
        signed_composition_valid=1,
        answer_incremental_likely=1,
        textbook_mediator=0,
    )
    assert validate(
        {"reviews": [hidden]}, {("Q1", "STAT1")}, strict_hidden=True
    )[0]["passes_consensus_gate"] == 1

    hidden["textbook_mediator"] = 1
    assert validate(
        {"reviews": [hidden]}, {("Q1", "STAT1")}, strict_hidden=True
    )[0]["passes_consensus_gate"] == 0
