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


def test_switching_provider_without_explicit_model_resets_to_new_providers_default(monkeypatch):
    """Regression test found live via the FastAPI bridge: LLMClient() auto-inits as
    "local" (LOCAL_LLM_MODEL=gpt-oss:120b), then a session requests provider="openai"
    without a model. initialize_client() already resets base_url when the provider
    changes -- it must do the same for model, or every call silently sends the old
    provider's model tag (e.g. an Ollama tag) to the new provider's API and 404s."""
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://192.168.81.7:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "gpt-oss:120b")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    client = LLMClient()
    assert client.model == "gpt-oss:120b"  # sanity: local auto-init picked it up

    client.initialize_client(api_key="sk-test-key", base_url=None, model=None, provider="openai")

    assert client.provider == "openai"
    assert client.model == "gpt-4o-mini"


def test_switching_provider_with_explicit_model_is_still_respected(monkeypatch):
    """The fix above must not override a model the caller explicitly asked for."""
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://192.168.81.7:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "gpt-oss:120b")

    client = LLMClient()
    client.initialize_client(api_key="sk-test", base_url=None, model="gpt-4o", provider="openai")

    assert client.model == "gpt-4o"
