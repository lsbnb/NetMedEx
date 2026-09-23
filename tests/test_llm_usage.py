from types import SimpleNamespace
from unittest.mock import MagicMock

from webapp.llm import LLMClient


def test_translate_to_english_ok_status_on_success():
    """A successful translation call must leave last_translation_status == "ok" so
    chat.py's English Intermediary does not mistake it for a silent fallback."""
    llm = LLMClient()
    llm.provider = "openai"
    llm.api_key = "test-key"
    llm.client = MagicMock()
    llm.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="translated text"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    assert llm.translate_to_english("原始文字") == "translated text"
    assert llm.last_translation_status == "ok"


def test_translate_to_english_unavailable_status_with_no_client():
    """With no client configured, the original text is returned unchanged (existing
    behavior) but last_translation_status must now flag "unavailable" so callers can
    tell this apart from a genuine "already English" no-op."""
    llm = LLMClient()
    llm.client = None
    llm.anthropic_client = None

    original = "請找出與骨質疏鬆相關的機制"
    assert llm.translate_to_english(original) == original
    assert llm.last_translation_status == "unavailable"


def test_translate_to_english_error_status_when_call_raises():
    """An exception during the underlying LLM call must fall back to the original
    text (existing behavior) while flagging last_translation_status == "error"."""
    llm = LLMClient()
    llm.provider = "openai"
    llm.client = MagicMock()
    llm.client.chat.completions.create.side_effect = RuntimeError("boom")

    original = "請找出與骨質疏鬆相關的機制"
    assert llm.translate_to_english(original) == original
    assert llm.last_translation_status == "error"


def test_openai_compatible_completion_records_token_usage():
    llm = LLMClient()
    llm.provider = "openai"
    llm.api_key = "test-key"
    llm.model = "gpt-4o"
    llm.client = MagicMock()
    llm.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3, total_tokens=15),
    )

    assert llm.chat_completion_text([{"role": "user", "content": "test"}]) == "ok"
    assert llm.last_completion_usage == {
        "input_tokens": 12,
        "output_tokens": 3,
        "total_tokens": 15,
    }
    assert llm.completion_usage_totals == llm.last_completion_usage

    llm.chat_completion_text([{"role": "user", "content": "again"}])
    assert llm.completion_usage_totals == {
        "input_tokens": 24,
        "output_tokens": 6,
        "total_tokens": 30,
    }
