from __future__ import annotations

import logging
import os

import uvicorn

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    host = os.getenv("NETMEDEX_API_HOST", "0.0.0.0")
    port = int(os.getenv("NETMEDEX_API_PORT", "8000"))

    if host not in ("127.0.0.1", "localhost") and not os.getenv("NETMEDEX_API_KEY", "").strip():
        logger.warning(
            "Binding to %s:%d with no NETMEDEX_API_KEY set -- any other host that can reach "
            "this address can create sessions, read session metadata, and use your configured "
            "LLM provider. Set NETMEDEX_API_KEY to require an API key, or set "
            "NETMEDEX_API_HOST=127.0.0.1 to restrict this to the local machine only.",
            host,
            port,
        )

    uvicorn.run("netmedex.fastapi_bridge:app", host=host, port=port, reload=False)
