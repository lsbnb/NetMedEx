from __future__ import annotations

import asyncio

from netmedex import citation_fetcher


def test_fetch_citation_counts_async_uses_callables_for_aiometer(monkeypatch):
    class DummySessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(citation_fetcher.aiohttp, "ClientSession", DummySessionContext)

    async def fake_fetch_citation_count(session, pmid):
        return int(pmid) + 10

    monkeypatch.setattr(citation_fetcher, "fetch_citation_count", fake_fetch_citation_count)

    state = {"all_callable": False}

    async def fake_run_all(jobs, max_at_once, max_per_second):
        state["all_callable"] = all(callable(job) for job in jobs)
        return [await job() for job in jobs]

    monkeypatch.setattr(citation_fetcher.aiometer, "run_all", fake_run_all)

    result = asyncio.run(citation_fetcher._fetch_citation_counts_async(["1", "2", "2"]))

    assert state["all_callable"] is True
    assert result == {"1": 11, "2": 12}
