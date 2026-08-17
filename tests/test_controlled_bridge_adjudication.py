import pytest

from evaluation.adjudicate_controlled_bridge_reviews import validate


def test_adjudication_validation_accepts_binary_decision():
    result = validate(
        {"adjudications": [{"question_id": "Q1", "mediator": "PLS3", "final_accept": 1, "reason": "Test."}]},
        {("Q1", "PLS3")},
    )
    assert result[0]["final_accept"] == 1


def test_adjudication_validation_requires_exact_items():
    with pytest.raises(ValueError, match="Missing adjudications"):
        validate({"adjudications": []}, {("Q1", "PLS3")})
