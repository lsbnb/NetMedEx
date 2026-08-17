import pytest
from unittest.mock import MagicMock, patch

from evaluation.rate_ai_panel import (
    DEFAULT_MODELS,
    build_prompt,
    init_client,
    parse_json_object,
    validate_payload,
)


def test_parse_json_object_tolerates_fences_and_trailing_text():
    parsed = parse_json_object('```json\n{"ratings": []}\n``` trailing')
    assert parsed == {"ratings": []}


def test_parse_json_object_wraps_bare_ratings_array():
    parsed = parse_json_object('[{"edge_id":"E1"}] trailing')
    assert parsed == {"ratings": [{"edge_id": "E1"}]}


def test_validate_edge_panel_payload():
    result = validate_payload(
        "edge",
        {
            "ratings": [
                {
                    "edge_id": "Q001-E01",
                    "entity_valid": 1,
                    "relation_exists": 1,
                    "relation_type_correct": 0,
                    "direction_correct": 0,
                    "evidence_support": 1,
                    "confidence": 3,
                    "notes": "Reverse direction.",
                }
            ]
        },
        {"Q001-E01"},
    )
    assert result["ratings"][0]["direction_correct"] == 0


def test_validate_answer_requires_blinded_pairwise_choice():
    payload = {
        "ratings": [
            {
                "answer_id": answer_id,
                "correctness": 4,
                "completeness": 4,
                "relevance": 5,
                "grounding": 4,
                "mechanistic_coherence": 4,
                "research_value": 4,
                "notes": "Supported.",
            }
            for answer_id in ("Q001-A", "Q001-B")
        ],
        "preferred_item_id": "Q001-A",
        "pairwise_reason": "More complete.",
    }
    assert validate_payload("answer", payload, {"Q001-A", "Q001-B"})[
        "preferred_item_id"
    ] == "Q001-A"

    payload["preferred_item_id"] = "netmedex_hybrid_rag"
    with pytest.raises(ValueError):
        validate_payload("answer", payload, {"Q001-A", "Q001-B"})


def test_validate_hidden_claim_payload_and_share_comparison_once():
    payload = {
        "ratings": [
            {
                "hidden_claim_id": "Q001-HC01",
                "hybrid_only": 1,
                "path_traceable": 1,
                "evidence_support": 1,
                "relation_direction_correct": 1,
                "multi_document_or_hop": 1,
                "non_obviousness": 4,
                "research_utility": 5,
                "unsupported_novelty": 0,
                "notes": "Traceable and useful.",
            }
        ]
    }
    result = validate_payload("hidden_claim", payload, {"Q001-HC01"})
    assert result["ratings"][0]["evidence_support"] == 1

    records = [
        {
            "hidden_claim_id": "Q001-HC01",
            "candidate_claim": "A may affect C through B.",
            "path_evidence": "A-B-C",
            "comparison_answer": "Comparator text unique marker.",
        },
        {
            "hidden_claim_id": "Q001-HC02",
            "candidate_claim": "D may affect F through E.",
            "path_evidence": "D-E-F",
            "comparison_answer": "Comparator text unique marker.",
        },
    ]
    prompt = build_prompt("hidden_claim", "Question", records)
    assert prompt.count("Comparator text unique marker.") == 1


def test_local_panel_client_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://192.168.1.10:11434")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "test-local-key")
    with patch("evaluation.rate_ai_panel.LLMClient") as client_class:
        client = MagicMock()
        client_class.return_value = client
        assert init_client("local", "medgemma:27b") is client
        client.initialize_client.assert_called_once_with(
            provider="local",
            api_key="test-local-key",
            base_url="http://192.168.1.10:11434/v1",
            model="medgemma:27b",
        )


def test_gemini_panel_is_blocked_by_administrative_flag(monkeypatch):
    monkeypatch.setenv("DISABLE_GEMINI_API", "true")
    with pytest.raises(RuntimeError, match="Gemini judge is disabled"):
        init_client("google", "gemini-2.0-flash")


def test_primary_local_panel_model_is_gpt_oss_120b():
    assert DEFAULT_MODELS["local"] == "gpt-oss:120b"
