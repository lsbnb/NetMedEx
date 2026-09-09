from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from netmedex.chat_bridge import BridgeConfig, NetMedExChatBridge

logger = logging.getLogger(__name__)


class SessionConfigModel(BaseModel):
    provider: str = Field(default="openai", pattern="^(openai|google|local|anthropic|groq|nvidia|openrouter)$")
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
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
    genes: Optional[list[str]] = None
    disease: str = "osteoporosis"
    query: Optional[str] = None


class AskRequest(BaseModel):
    question: str


class _SessionStore:
    def __init__(
        self,
        max_sessions: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._bridges: dict[str, NetMedExChatBridge] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._last_accessed: dict[str, float] = {}

        self.max_sessions = (
            max_sessions
            if max_sessions is not None
            else int(os.getenv("NETMEDEX_MAX_SESSIONS", "50"))
        )
        self.ttl_seconds = (
            ttl_seconds
            if ttl_seconds is not None
            else int(os.getenv("NETMEDEX_SESSION_TTL", "7200"))
        )

    def _cleanup_expired_locked(self, now: float) -> None:
        if self.ttl_seconds <= 0:
            return
        expired_ids = [
            sid for sid, last in self._last_accessed.items() if now - last > self.ttl_seconds
        ]
        for sid in expired_ids:
            self._bridges.pop(sid, None)
            self._meta.pop(sid, None)
            self._last_accessed.pop(sid, None)
            logger.info("Evicted expired session %s (TTL=%ds)", sid, self.ttl_seconds)

    def _evict_lru_locked(self) -> None:
        if self.max_sessions <= 0 or len(self._bridges) < self.max_sessions:
            return
        oldest_sid = min(self._last_accessed, key=self._last_accessed.get)
        self._bridges.pop(oldest_sid, None)
        self._meta.pop(oldest_sid, None)
        self._last_accessed.pop(oldest_sid, None)
        logger.info("Evicted LRU session %s (max_sessions=%d)", oldest_sid, self.max_sessions)

    def create(self, bridge: NetMedExChatBridge, meta: dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        now_dt = datetime.now(timezone.utc).isoformat()
        now_ts = time.time()
        with self._lock:
            self._cleanup_expired_locked(now_ts)
            self._evict_lru_locked()
            self._bridges[session_id] = bridge
            self._meta[session_id] = {"created_at": now_dt, **meta}
            self._last_accessed[session_id] = now_ts
        return session_id

    def get(self, session_id: str) -> NetMedExChatBridge:
        now_ts = time.time()
        with self._lock:
            self._cleanup_expired_locked(now_ts)
            bridge = self._bridges.get(session_id)
            if bridge is None:
                raise KeyError(session_id)
            self._last_accessed[session_id] = now_ts
        return bridge

    def delete(self, session_id: str) -> bool:
        with self._lock:
            existed = session_id in self._bridges
            self._bridges.pop(session_id, None)
            self._meta.pop(session_id, None)
            self._last_accessed.pop(session_id, None)
            return existed

    def list_meta(self) -> dict[str, dict[str, Any]]:
        now_ts = time.time()
        with self._lock:
            self._cleanup_expired_locked(now_ts)
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
                context = bridge.build_context_from_genes(
                    genes=request.genes or [], disease=request.disease
                )

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
