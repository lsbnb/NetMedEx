from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import aiohttp
import aiometer

logger = logging.getLogger(__name__)

# OpenCitations Index API base URL
OPENCITATIONS_BASE_URL = "https://api.opencitations.net/index/v2"
# Rate limit: 180 requests per minute (3 per second)
MAX_PER_SECOND = 3
MAX_AT_ONCE = 3


async def fetch_citation_count(session: aiohttp.ClientSession, pmid: str) -> int:
    """Fetch citation count for a single PMID from OpenCitations."""
    url = f"{OPENCITATIONS_BASE_URL}/citation-count/pmid:{pmid}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                # OpenCitations returns a list of dictionaries
                # Example: [{"count": "42"}]
                if data and isinstance(data, list) and len(data) > 0:
                    count_str = data[0].get("count", "0")
                    return int(count_str)
            elif response.status == 404:
                return 0
            else:
                logger.warning(
                    f"Failed to fetch citation count for PMID {pmid}: {response.status}"
                )
                return 0
    except Exception as e:
        logger.error(f"Error fetching citation count for PMID {pmid}: {e}")
        return 0
    return 0


async def _fetch_citation_counts_async(
    pmid_list: list[str],
    progress_callback=None,
) -> dict[str, int]:
    """Fetch citation counts for a list of PMIDs asynchronously.

    Progress callback is fired immediately after each individual PMID is resolved,
    not after all PMIDs have been processed.
    """
    if not pmid_list:
        return {}

    pmid_list = list(set(pmid_list))  # Unique PMIDs
    total = len(pmid_list)
    results: dict[str, int] = {}
    # Mutable counter accessible from each per-PMID callable closure.
    counter = [0]

    async with aiohttp.ClientSession() as session:

        async def _fetch_one(pmid: str) -> tuple[str, int]:
            """Fetch a single PMID, update counter, and fire the progress callback."""
            count = await fetch_citation_count(session, pmid)
            counter[0] += 1
            if progress_callback:
                try:
                    progress_callback(counter[0], total)
                except Exception:
                    logger.exception("Error in citation progress_callback")
            return pmid, count

        # aiometer.run_all requires callables, not coroutines.
        jobs = [partial(_fetch_one, pmid) for pmid in pmid_list]
        pairs = await aiometer.run_all(
            jobs, max_at_once=MAX_AT_ONCE, max_per_second=MAX_PER_SECOND
        )
        for pmid, count in pairs:
            results[pmid] = count

    return results


def _run_async_in_new_loop(
    pmid_list: list[str],
    progress_callback=None,
) -> dict[str, int]:
    """Run the async fetch in a fresh event loop.

    Safe to call from any thread, including executor workers spawned inside a
    Dash background callback that already owns a running event loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _fetch_citation_counts_async(pmid_list, progress_callback)
        )
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def fetch_citation_counts(
    pmid_list: list[str],
    progress_callback=None,
) -> dict[str, int]:
    """Synchronous wrapper to fetch citation counts for a list of PMIDs."""
    try:
        asyncio.get_running_loop()
        # A running loop exists (e.g. inside a Dash background callback).
        # Calling asyncio.run() here would raise RuntimeError or deadlock.
        # Dispatch to a dedicated thread with its own fresh loop instead.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_in_new_loop, pmid_list, progress_callback)
            return future.result()
    except RuntimeError:
        # No running loop — safe to call asyncio.run() directly.
        return asyncio.run(_fetch_citation_counts_async(pmid_list, progress_callback))
