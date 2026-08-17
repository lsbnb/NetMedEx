import pytest

from evaluation.review_controlled_bridge_evidence import compact_abstract, validate


def expected():
    return {("Q1", "M1"): {"source": {"S1"}, "target": {"T1"}}}


def test_abstract_compaction_preserves_both_ends():
    text = "BACKGROUND " + ("x" * 100) + " CONCLUSION"
    compact = compact_abstract(text, 60)
    assert compact.startswith("BACKGROUND")
    assert compact.endswith("CONCLUSION")
    assert len(compact) == 60


def test_evidence_review_requires_all_signed_checks():
    rows = validate(
        {"reviews": [{
            "question_id": "Q1", "mediator": "M1",
            "source_relation_supported": 1, "target_relation_supported": 1,
            "signed_composition_valid": 0, "endpoint_semantically_isolated": 1,
            "source_supporting_pmids": ["S1"], "target_supporting_pmids": ["T1"],
            "contradiction_pmids": [], "reason": "Polarity cannot be composed."
        }]},
        expected(),
    )
    assert rows[0]["passes_evidence_gate"] == 0


def test_evidence_review_rejects_unsupplied_citation():
    with pytest.raises(ValueError, match="unsupplied PMID"):
        validate(
            {"reviews": [{
                "question_id": "Q1", "mediator": "M1",
                "source_relation_supported": 1, "target_relation_supported": 1,
                "signed_composition_valid": 1, "endpoint_semantically_isolated": 1,
                "source_supporting_pmids": ["OTHER"], "target_supporting_pmids": ["T1"],
                "contradiction_pmids": [], "reason": ""
            }]},
            expected(),
        )
