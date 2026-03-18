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


async def _fetch_citation_counts_async(pmid_list: list[str]) -> dict[str, int]:
    """Fetch citation counts for a list of PMIDs asynchronously."""
    if not pmid_list:
        return {}

    pmid_list = list(set(pmid_list))  # Unique PMIDs
    results = {}

    async with aiohttp.ClientSession() as session:
        jobs = [partial(fetch_citation_count, session, pmid) for pmid in pmid_list]
        counts = await aiometer.run_all(
            jobs, max_at_once=MAX_AT_ONCE, max_per_second=MAX_PER_SECOND
        )
        for pmid, count in zip(pmid_list, counts):
            results[pmid] = count

    return results


def fetch_citation_counts(pmid_list: list[str]) -> dict[str, int]:
    """Synchronous wrapper to fetch citation counts for a list of PMIDs."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_fetch_citation_counts_async(pmid_list))

    # In an existing async context, execute in a separate thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _fetch_citation_counts_async(pmid_list))
        return future.result()
