from types import SimpleNamespace
from unittest.mock import MagicMock

from webapp.llm import LLMClient


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
