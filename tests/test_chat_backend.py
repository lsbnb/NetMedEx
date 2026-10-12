from __future__ import annotations

import sys
import types

from webapp.chat_backend import build_project_session


def test_no_backend_configured_keeps_default_paths(monkeypatch):
    monkeypatch.delenv("NETMEDEX_CHAT_BACKEND", raising=False)
    assert build_project_session(object(), object(), "topic") is None


def test_configured_backend_builds_the_session(monkeypatch):
    calls = []
    module = types.ModuleType("fake_project_chat")

    def factory(G, llm_client, topic):
        calls.append((G, llm_client, topic))
        return "session", "rag"

    module.web_session = factory
    monkeypatch.setitem(sys.modules, "fake_project_chat", module)
    monkeypatch.setenv("NETMEDEX_CHAT_BACKEND", "fake_project_chat:web_session")
    G, client = object(), object()
    assert build_project_session(G, client, None) == ("session", "rag")
    assert calls == [(G, client, "biomedical research")]
