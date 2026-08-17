from webapp.llm import LLMClient


def test_local_provider_prefers_local_endpoint_over_openai_base(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://192.168.81.7:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "gpt-oss:120b")
    monkeypatch.setattr(LLMClient, "initialize_client", lambda self, *args, **kwargs: None)

    client = LLMClient()

    assert client.provider == "local"
    assert client.base_url == "http://192.168.81.7:11434/v1"
    assert client.model == "gpt-oss:120b"
