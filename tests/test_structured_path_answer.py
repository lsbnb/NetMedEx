import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.run_formal_50 import (
    generate_answer,
    render_canonical_graph_insights,
    render_natural_graph_insights,
    select_answer_paths,
    select_oracle_answer_paths,
)
from netmedex.claim_verifier import verify_answer_graph_claims


def make_path(signature: str = "deadbeef12345678", score: float = 0.9) -> dict:
    return {
        "path_signature": signature,
        "gate_tier": "A",
        "claim_safe": True,
        "incremental_value_class": "graph_incremental_candidate",
        "names": ["A", "B", "C", "D", "A"],
        "relations": ["causes", "promotes", "inhibits", "leads_to"],
        "edge_pmids": [["111111"], ["222222"], ["333333"], ["444444"]],
        "edge_evidence_quotes": [
            ["A causes B"], ["B promotes C"], ["C inhibits D"], ["D leads to A"]
        ],
        "score": score,
        "candidate_rank": 1,
    }


def test_four_hop_cycle_canonical_claim_is_fully_supported():
    path = make_path()
    answer = render_canonical_graph_insights([path], "English")
    verification = verify_answer_graph_claims(answer, [path])
    assert verification["supported_claim_count"] == 1
    assert verification["unsupported_claim_count"] == 0


def test_answer_selector_is_claim_safe_limited_and_deduplicated():
    first = make_path("aaaaaaaa11111111", 0.9)
    duplicate = make_path("bbbbbbbb22222222", 0.8)
    unsafe = make_path("cccccccc33333333", 1.0)
    unsafe["claim_safe"] = False
    selected = select_answer_paths([unsafe, duplicate, first], limit=2)
    assert [path["path_signature"] for path in selected] == ["aaaaaaaa11111111"]


def test_confirmatory_paths_are_not_added_to_answer_context():
    confirmed = make_path()
    confirmed["incremental_value_class"] = "graph_confirmed"
    assert select_answer_paths([confirmed]) == []


def test_empty_path_set_adds_no_graph_section():
    assert render_canonical_graph_insights([], "English") == ""


def test_natural_renderer_keeps_hop_pmids_without_path_jargon():
    rendered = render_natural_graph_insights([make_path()], "English")
    assert "Additional evidence synthesis" in rendered
    assert "PMID: 111111" in rendered
    assert "PATH deadbeef" not in rendered
    assert "→" not in rendered


def test_answer_generation_retries_when_provider_reports_length_finish():
    class TruncatingOnceLLM:
        def __init__(self):
            self.calls = []
            self.last_completion_finish_reason = ""

        def chat_completion_text(self, **kwargs):
            self.calls.append(kwargs["max_tokens"])
            if len(self.calls) == 1:
                self.last_completion_finish_reason = "length"
                return "truncated"
            self.last_completion_finish_reason = "stop"
            return "complete answer"

    llm = TruncatingOnceLLM()
    answer = generate_answer(
        llm,
        system="traditional_rag",
        question="Question?",
        language="English",
        text_context="Evidence [PMID: 1]",
        max_tokens=1200,
    )
    assert answer == "complete answer"
    assert llm.calls == [1200, 2400]


def test_oracle_rejects_nonlocal_model():
    class RemoteLLM:
        provider = "openai"

    try:
        select_oracle_answer_paths(RemoteLLM(), [make_path()], "question")
    except ValueError as exc:
        assert "provider=local" in str(exc)
    else:
        raise AssertionError("remote oracle should fail closed")


def test_local_oracle_selects_only_supplied_safe_id():
    path = make_path()

    class LocalLLM:
        provider = "local"

        def chat_completion_text(self, **_kwargs):
            return '{"selected_ids":["deadbeef12345678","invented"]}'

    selected, audit = select_oracle_answer_paths(LocalLLM(), [path], "question")
    assert selected == [path]
    assert audit["selected"] == ["deadbeef12345678"]


def test_local_oracle_excludes_requested_bridge_misaligned_path():
    aligned = make_path("aaaaaaaa11111111")
    aligned["query_endpoint_coverage"] = 1.0
    aligned["requested_bridge_coverage"] = 1.0
    misaligned = make_path("bbbbbbbb22222222")
    misaligned["query_endpoint_coverage"] = 1.0
    misaligned["requested_bridge_coverage"] = 0.5

    class LocalLLM:
        provider = "local"

        def chat_completion_text(self, **_kwargs):
            return '{"selected_ids":["bbbbbbbb22222222","aaaaaaaa11111111"]}'

    selected, audit = select_oracle_answer_paths(
        LocalLLM(), [misaligned, aligned], "question"
    )
    assert selected == [aligned]
    assert audit["eligible"] == 1
    assert audit["selected"] == ["aaaaaaaa11111111"]


def test_local_oracle_fails_instead_of_using_rule_fallback():
    class EmptyLocalLLM:
        provider = "local"

        def chat_completion_text(self, **_kwargs):
            return ""

    try:
        select_oracle_answer_paths(EmptyLocalLLM(), [make_path()], "question")
    except RuntimeError as exc:
        assert "no valid safe path" in str(exc)
    else:
        raise AssertionError("empty local oracle should fail closed")
