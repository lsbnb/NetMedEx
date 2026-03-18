from __future__ import annotations

from typing import Any

import requests


class NetMedExAPIClient:
    """Framework-agnostic client for NetMedEx FastAPI bridge."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session_id: str | None = None

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_session(
        self,
        config: dict[str, Any],
        *,
        genes: list[str] | None = None,
        disease: str = "osteoporosis",
        query: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"config": config, "disease": disease}
        if genes is not None:
            payload["genes"] = genes
        if query is not None:
            payload["query"] = query

        result = self._request("POST", "/sessions", json=payload)
        self.session_id = result.get("session_id")
        return result

    def ask(self, question: str, *, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("Session ID is required. Call create_session() first.")
        return self._request("POST", f"/sessions/{sid}/ask", json={"question": question})

    def close(self, *, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("Session ID is required.")
        result = self._request("DELETE", f"/sessions/{sid}")
        if sid == self.session_id:
            self.session_id = None
        return result

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = requests.request(
            method=method,
            url=f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        return response.json()


if __name__ == "__main__":
    client = NetMedExAPIClient(base_url="http://127.0.0.1:8000")
    print(client.health())

    create_resp = client.create_session(
        config={
            "provider": "google",
            "model": "gemini-2.0-flash",
            "edge_method": "semantic",
            "max_articles": 120,
        },
        genes=["SOST", "LRP5", "TNFRSF11B", "RUNX2", "ALPL"],
        disease="osteoporosis",
    )
    print("Session:", create_resp["session_id"])

    answer = client.ask("Summarize strongest evidence and potential mechanisms.")
    print(answer.get("message", ""))

    client.close()
