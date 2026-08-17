from evaluation.screen_controlled_bridge_preflight import evaluate_mediator


def audit(source, target, *, eligible=True):
    return {
        "name": "STAT1",
        "bridge_eligible": eligible,
        "accepted_pmids": {"source": source, "target": target},
    }


def ranking(*pmids):
    return [{"pmid": pmid, "score": 1.0} for pmid in pmids]


def test_preflight_accepts_exactly_one_withheld_bridge_side():
    result = evaluate_mediator(
        audit(["S1", "S2"], ["T1", "T2"]),
        ranking("S1", "S2", "D1"),
        top_k=3,
    )
    assert result["graph_build_eligible"] is True
    assert result["target_outside_text_top_k"] == ["T1", "T2"]


def test_preflight_rejects_bridge_fully_visible_to_text():
    result = evaluate_mediator(
        audit(["S1"], ["T1"]), ranking("S1", "T1"), top_k=2
    )
    assert result["graph_build_eligible"] is False
    assert "complete_bridge_visible_in_text_top_k" in result["reasons"]


def test_preflight_rejects_document_overlap():
    result = evaluate_mediator(
        audit(["P1"], ["P1"]), ranking("P1"), top_k=1
    )
    assert result["graph_build_eligible"] is False
    assert "source_target_document_overlap" in result["reasons"]


def test_preflight_rejects_when_neither_side_is_retrieved():
    result = evaluate_mediator(
        audit(["S1"], ["T1"]), ranking("D1", "D2"), top_k=2
    )
    assert result["graph_build_eligible"] is False
    assert "neither_bridge_side_visible_in_text_top_k" in result["reasons"]


def test_preflight_requires_all_signed_hop_evidence_checks_when_audit_supplied():
    result = evaluate_mediator(
        audit(["S1"], ["T1"]),
        ranking("S1"),
        top_k=1,
        evidence_audit={
            "source_relation_supported": False,
            "target_relation_supported": True,
            "signed_composition_valid": True,
            "endpoint_semantically_isolated": True,
        },
    )
    assert result["retrieval_eligible"] is True
    assert result["evidence_eligible"] is False
    assert result["graph_build_eligible"] is False
    assert "signed_hop_evidence_gate_failed" in result["reasons"]


def test_preflight_accepts_retrieval_and_signed_evidence_together():
    result = evaluate_mediator(
        audit(["S1"], ["T1"]),
        ranking("S1"),
        top_k=1,
        evidence_audit={
            "source_relation_supported": True,
            "target_relation_supported": True,
            "signed_composition_valid": True,
            "endpoint_semantically_isolated": True,
        },
    )
    assert result["retrieval_eligible"] is True
    assert result["evidence_eligible"] is True
    assert result["graph_build_eligible"] is True
