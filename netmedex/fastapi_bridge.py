from __future__ import annotations

import threading
import uuid
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from netmedex.chat_bridge import BridgeConfig, NetMedExChatBridge


class SessionConfigModel(BaseModel):
    provider: str = Field(default="openai", pattern="^(openai|google|local)$")
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    max_articles: int = 200
    sort: str = Field(default="score", pattern="^(score|date)$")
    full_text: bool = False
    edge_method: str = Field(default="semantic", pattern="^(co-occurrence|semantic|relation)$")
    semantic_threshold: float = 0.5
    top_k: int = 5
    max_history: int = 10
    session_language: str = "English"


class CreateSessionRequest(BaseModel):
    config: SessionConfigModel
    genes: list[str] | None = None
    disease: str = "osteoporosis"
    query: str | None = None


class AskRequest(BaseModel):
    question: str


class _SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bridges: dict[str, NetMedExChatBridge] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def create(self, bridge: NetMedExChatBridge, meta: dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._bridges[session_id] = bridge
            self._meta[session_id] = {"created_at": now, **meta}
        return session_id

    def get(self, session_id: str) -> NetMedExChatBridge:
        with self._lock:
            bridge = self._bridges.get(session_id)
        if bridge is None:
            raise KeyError(session_id)
        return bridge

    def delete(self, session_id: str) -> bool:
        with self._lock:
            existed = session_id in self._bridges
            self._bridges.pop(session_id, None)
            self._meta.pop(session_id, None)
            return existed

    def list_meta(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._meta)


store = _SessionStore()


def create_app() -> FastAPI:
    app = FastAPI(title="NetMedEx FastAPI Bridge", version="0.1.0")
    cors_origins_env = os.getenv("NETMEDEX_CORS_ORIGINS", "").strip()
    cors_origins = (
        [o.strip() for o in cors_origins_env.split(",") if o.strip()]
        if cors_origins_env
        else ["http://localhost:8050", "http://127.0.0.1:8050"]
    )
    allow_credentials = os.getenv("NETMEDEX_CORS_ALLOW_CREDENTIALS", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if "*" in cors_origins:
        allow_credentials = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sessions")
    def list_sessions() -> dict[str, Any]:
        meta = store.list_meta()
        return {"count": len(meta), "sessions": meta}

    @app.post("/sessions")
    def create_session(request: CreateSessionRequest) -> dict[str, Any]:
        if not request.query and not request.genes:
            raise HTTPException(status_code=400, detail="Provide either query or genes.")
        if request.query and request.genes:
            raise HTTPException(status_code=400, detail="Provide only one of query or genes.")
        try:
            config = BridgeConfig(**request.config.model_dump())
            bridge = NetMedExChatBridge(config=config)
            if request.query:
                context = bridge.build_context_from_query(request.query)
            else:
                context = bridge.build_context_from_genes(genes=request.genes or [], disease=request.disease)

            session_id = store.create(
                bridge=bridge,
                meta={
                    "provider": config.provider,
                    "edge_method": config.edge_method,
                    "last_query": bridge.last_query,
                    "pmid_count": context.get("pmid_count", 0),
                },
            )
            return {"session_id": session_id, "context": context}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create session: {e}")

    @app.post("/sessions/{session_id}/ask")
    def ask(session_id: str, request: AskRequest) -> dict[str, Any]:
        try:
            bridge = store.get(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            return bridge.ask(request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

    @app.delete("/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, Any]:
        if not store.delete(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        return {"deleted": True, "session_id": session_id}

    return app


app = create_app()
