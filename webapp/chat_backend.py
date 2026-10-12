"""Optional project-specific chat backend.

NetMedEx's web chat indexes the abstracts of the current graph (or selection)
in memory every time a chat session starts or is rebuilt -- right for graphs
of a few thousand articles. A project serving a much larger prebuilt graph
(see NETMEDEX_PRELOAD_GRAPH) can supply its own session factory instead, e.g.
one that reloads persistent indexes:

    NETMEDEX_CHAT_BACKEND=kg_chat:web_session   # module importable on PYTHONPATH

The factory is called as ``factory(G, llm_client, topic=...)`` and returns
``(session, rag_system)``. Unset, every chat path behaves exactly as before.
"""
from __future__ import annotations

import importlib
import logging
import os

logger = logging.getLogger(__name__)


def build_project_session(G, llm_client, topic: str | None):
    spec = os.getenv("NETMEDEX_CHAT_BACKEND")
    if not spec:
        return None
    module_name, _, func_name = spec.partition(":")
    factory = getattr(importlib.import_module(module_name), func_name)
    session, rag_system = factory(G, llm_client, topic=topic or "biomedical research")
    logger.info("Chat session built by project backend %s", spec)
    return session, rag_system
