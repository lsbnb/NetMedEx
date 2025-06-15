# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from queue import Queue
from typing import Any, Literal

import aiohttp
import aiometer
from aiohttp import ClientResponse, ClientSession
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from tqdm.auto import tqdm

from netmedex.biocjson_parser import biocjson_to_pubtator
from netmedex.exceptions import EmptyInput, NoArticles, RetryableError, UnsuccessfulRequest
from netmedex.pubtator_data import PubTatorArticle, PubTatorCollection
from netmedex.pubtator_parser import PubTatorIterator
from netmedex.types import T
from netmedex.utils import config_logger

# API GET limit: 100
PMID_REQUEST_SIZE = 100
# Fall back to "search" if "cite" failed
FALLBACK_SEARCH = True

PUBTATOR_SEARCH_URL = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
PUBTATOR_CITE_URL = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv"

# Users post no more than three requests per second
# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
MAX_CONCURRENT_REQUESTS = 3
REQUEST_INTERVAL = 0.8

PUBTATOR_RETRY_ERRORS = {
    # Error code: custom error message
    408: "Please retry later",  # Request Timeout
    429: "Too many requests. Please run this program later.",  # Too Many Requests
    500: "Please retry later",  # Internal Server Error
    502: "Possibly too many articles. Please try more specific queries.",  # Bad Gateway
    503: "Please retry later",  # Service Unavailable
    504: "Please retry later",  # Gateway Timeout
}

# Full text annotation is only availabe in `biocxml` and `biocjson` formats
# RESPONSE_FORMAT = ["pubtator", "biocxml", "biocjson"][2]
logger = logging.getLogger(__name__)
config_logger(is_debug=False)


class PubTatorAPI:
    """Retrieve PubMed articles with entity annotations via PubTator3 API.

    Input either a free-text PubMed query (e.g. '"COVID-19" AND "PON1"') or a
    list of PubMed IDs (PMIDs).

    After creating a `PubTatorAPI` instance, **remember to call
    `run` for synchronous execution** or **`arun` for asynchronous execution**
    to actually fetch the requested articles.

    Args:
        query (str | None):
            A free-text search query for PubMed articles. Mutually exclusive with `pmid_list`.
        pmid_list (Sequence[str | int] | None):
            A list of PubMed IDs to directly fetch annotations. Mutually exclusive with `query`.
        sort (Literal["score", "date"]):
            Sorting method for search results; "score" for relevance, "date" for most recent. Defaults to "score".
        request_format (Literal["biocjson", "pubtator"]):
            Format of the response. "biocjson" responses contain extra info for each article. Defaults to "biocjson".
        max_articles (int):
            Maximum number of articles to retrieve. Defaults to 1000.
        full_text (bool):
            Whether to request full-text annotations (available only in `biocjson`). Defaults to False.
        return_pmid_only (bool):
            Whether to return only the list of PMIDs without fetching full annotations. Defaults to False.
        queue (Queue | None):
            Optional queue for progress messaging (e.g., for UI or frontend logging).
    """

    def __init__(
        self,
        query: str | None = None,
        pmid_list: Sequence[str | int] | None = None,
        sort: Literal["score", "date"] = "score",
        request_format: Literal["biocjson", "pubtator"] = "biocjson",
        max_articles: int = 1000,
        full_text: bool = False,
        return_pmid_only: bool = False,
        queue: Queue | None = None,
    ):
        self.query = query
        self.pmid_list = pmid_list
        self.max_articles = max_articles
        self.full_text = full_text
        self.return_pmid_only = return_pmid_only
        self.queue = queue if isinstance(queue, Queue) else None
        self.sort: Literal["score", "date"] = sort
        self.response_format: Literal["biocjson", "pubtator"] = request_format
        # self.api_method: Literal["search", "cite"] = "cite" if sort == "date" else "search"

        # TODO: `cite` often fails when the number of articles exceeds ~7000
        # Always use `search`
        self.api_method: Literal["search", "cite"] = "search"

    def run(self):
        return asyncio.run(self._run())

    async def arun(self):
        return await asyncio.create_task(self._run())

    async def _run(self):
        if self.query is not None and self.pmid_list is not None:
            raise ValueError("Only one of `query` and `pmid_list` may be provided.")

        pmid_list = None
        # Searchy by free-text
        if self.query is not None:
            self.query = self.query.strip()
            if not self.query:
                raise EmptyInput
            pmid_list = await self.get_query_results(self.query)
        # Search by PMID list
        elif self.pmid_list is not None:
            if not self.pmid_list:
                raise EmptyInput
            pmid_list = [str(pmid) for pmid in self.pmid_list]

        if not pmid_list:
            raise NoArticles

        if self.return_pmid_only:
            return PubTatorCollection(headers=[], articles=[], metadata={"pmid_list": pmid_list})

        responses = await self.batch_publication_search(pmid_list)

        articles: list[PubTatorArticle] = []
        if self.response_format == "biocjson":
            for res_json in responses:
                articles.extend(
                    biocjson_to_pubtator(
                        res_json=res_json,
                        full_text=self.full_text,
                    )
                )
        elif self.response_format == "pubtator":
            for result in responses:
                articles.extend(
                    [article for article in PubTatorIterator(result) if article is not None]
                )

        return PubTatorCollection(headers=[], articles=articles, metadata={"pmid_list": pmid_list})

    async def get_query_results(self, query: str):
        logger.info(f"Query: {query}")
        article_list: list[str] = []
        async with ClientSession() as session:
            if self.api_method == "search":
                article_list = await self._handle_query_search(query, session=session)
            elif self.api_method == "cite":
                article_list = await self._handle_query_cite(query, session=session)

        return article_list

    async def _handle_query_search(self, query: str, session: ClientSession):
        res_json = await send_search_query(query, session=session)

        collected_article_ids: list[str] = []
        total_articles = int(res_json["count"])
        page_size = int(res_json["page_size"])
        collected_article_ids.extend(get_article_ids(res_json))

        n_articles_to_request = get_n_articles(self.max_articles, total_articles)
        if n_articles_to_request <= page_size:
            return collected_article_ids[:n_articles_to_request]

        num_page = n_articles_to_request // page_size
        if n_articles_to_request % page_size > 0:
            num_page += 1
        pages = range(2, num_page + 1)

        # Get search results in different pages until the max_articles is reached
        if self.return_pmid_only:
            logger.info("Step 1/1: Requesting article PMIDs...")
        else:
            logger.info("Step 1/2: Requesting article PMIDs...")

        async def each_request(page, pbar):
            article_ids = get_article_ids(
                await send_search_query_with_page(query, page, self.sort, session)
            )

            # Display progress
            update = page_size
            if pbar.n + page_size > pbar.total:
                update = pbar.total - pbar.n
            pbar.update(update)

            if self.queue is not None:
                # For frontend display
                self.queue.put(progress_message("search-search", pbar.n, pbar.total))

            return article_ids

        with tqdm(total=n_articles_to_request, file=sys.stdout) as pbar:
            article_id_lists = await batch_request([partial(each_request, p, pbar) for p in pages])
            if len(article_id_lists) != len(pages):
                logger.error(
                    f"Missing output: expected {len(article_id_lists)} batch outputs but only have {len(pages)}."
                )
            pbar.n = pbar.total
            if self.queue is not None:
                self.queue.put(progress_message("search-search", pbar.n, pbar.total))

        for article_ids in article_id_lists:
            collected_article_ids.extend(article_ids)

        return collected_article_ids[:n_articles_to_request]

    async def _handle_query_cite(self, query: str, session: ClientSession):
        if self.return_pmid_only:
            logger.info("Step 1/1: Requesting article PMIDs...")
        else:
            logger.info("Step 1/2: Requesting article PMIDs...")
        try:
            res_text = await send_cite_query(query, session=session)
        except (UnsuccessfulRequest, TypeError) as e:
            # TypeError happens if no response is returned
            if FALLBACK_SEARCH:
                logger.warning("Fetching articles by 'cite' method failed. Switch to 'search'.")
                return await self._handle_query_search(query, session=session)
            else:
                raise e

        pmid_list = parse_cite_response(res_text)
        n_articles_to_request = get_n_articles(self.max_articles, len(pmid_list))

        with tqdm(total=n_articles_to_request, file=sys.stdout) as pbar:
            pbar.n = pbar.total

        if self.queue is not None:
            self.queue.put(
                progress_message("search-cite", n_articles_to_request, n_articles_to_request)
            )

        return pmid_list[:n_articles_to_request]

    async def batch_publication_search(self, pmid_list: Sequence[str]):
        logger.info("Step 2/2: Requesting article annotations...")

        async with ClientSession() as session:

            async def each_request(batch, pbar):
                pmid_start = batch * PMID_REQUEST_SIZE
                pmid_end = pmid_start + PMID_REQUEST_SIZE
                if pmid_end >= len(pmid_list):
                    pmid_end = None

                res_txt_or_json = await send_publication_request(
                    pmid_string=",".join(pmid_list[pmid_start:pmid_end]),
                    article_id_type="pmids",
                    format=self.response_format,
                    full_text=self.full_text,
                    session=session,
                )

                # Display progress
                update = PMID_REQUEST_SIZE
                if pbar.n + PMID_REQUEST_SIZE > pbar.total:
                    update = pbar.total - pbar.n
                pbar.update(update)

                if self.queue is not None:
                    # For frontend display
                    self.queue.put(progress_message("get", pbar.n, pbar.total))

                return res_txt_or_json

            num_articles = len(pmid_list)
            with tqdm(total=num_articles, file=sys.stdout) as pbar:
                num_batch = num_articles // PMID_REQUEST_SIZE
                if num_articles % PMID_REQUEST_SIZE > 0:
                    num_batch += 1
                batches = range(0, num_batch)

                res_list = await batch_request(
                    [partial(each_request, batch, pbar) for batch in batches],
                )

                if len(res_list) != len(batches):
                    logger.error(
                        f"Missing output: expected {len(res_list)} batch outputs but only have {len(batches)}."
                    )
                pbar.n = pbar.total
                if self.queue is not None:
                    self.queue.put(progress_message("get", pbar.n, pbar.total))

        # End frontend progress display
        if self.queue is not None:
            self.queue.put(None)

        return res_list


async def send_search_query(
    query: str,
    session: ClientSession,
):
    return await request_pubtator3(
        PUBTATOR_SEARCH_URL,
        params={"text": query},
        session=session,
        is_json=True,
    )


async def send_cite_query(
    query: str,
    session: ClientSession,
):
    return await request_pubtator3(
        PUBTATOR_CITE_URL,
        params={"text": query},
        session=session,
        is_json=False,
    )


async def send_search_query_with_page(
    query: str,
    page: int,
    sort: Literal["score", "date"],
    session: ClientSession,
):
    url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    if sort == "score":
        params = {"text": query, "sort": "score desc", "page": page}
    elif sort == "date":
        params = {"text": query, "sort": "date desc", "page": page}
    return await request_pubtator3(url, params, session, is_json=True)


async def send_publication_request(
    pmid_string: str,
    article_id_type: Literal["pmids", "pmcids"],
    format: Literal["biocjson", "pubtator"],
    full_text: bool,
    session: ClientSession,
):
    url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{format}"
    params = {article_id_type: pmid_string}
    if full_text:
        params["full"] = "true"

    if format == "biocjson":
        is_json = True
    elif format == "pubtator":
        is_json = False

    return await request_pubtator3(url, params, session, is_json=is_json)


def get_n_articles(max_articles: int, total_articles: int):
    logger.info(f"Find {total_articles} articles")
    n_articles_to_request = max_articles if total_articles > max_articles else total_articles
    logger.info(f"Requesting {n_articles_to_request} articles...")
    return n_articles_to_request


def get_article_ids(res_json: Any):
    return [str(article.get("pmid")) for article in res_json["results"]]


def parse_cite_response(res_text: str):
    pmid_list: list[str] = []
    for line in res_text.split("\n"):
        if line.startswith("#") or line == "":
            continue
        # [pmid, title, journal]
        pmid = line.split("\t")[0]
        pmid_list.append(pmid)
    return pmid_list


def check_if_need_retry(res: ClientResponse):
    if res.status == 200:
        return

    if (error_msg := PUBTATOR_RETRY_ERRORS.get(res.status, None)) is not None:
        logger.warning(f"Request error occurred in input: {res.url} Retrying.")
        raise RetryableError(error_msg)
    else:
        logger.warning(f"Request error occurred in input: {res.url} Retrying.")
        raise UnsuccessfulRequest()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=5, max=10),
    reraise=True,
    retry=retry_if_exception(
        lambda e: isinstance(e, RetryableError | aiohttp.ServerDisconnectedError)
    ),
)
async def request_pubtator3(
    url: str,
    params: Any,
    session: ClientSession,
    is_json: bool = True,
) -> Any:
    async with session.get(url, params=params) as res:
        check_if_need_retry(res)
        try:
            if is_json:
                result = await res.json()
            else:
                result = await res.text()
        except Exception:
            msg = f"Failed to parse response: {res.url}"
            logger.warning(f"{msg} Retrying.")
            raise RetryableError(msg)

    return result


def progress_message(status, progress, total):
    return f"{status}/{progress}/{total}"


async def batch_request(
    jobs: Sequence[Callable[[], Awaitable[T]]],
) -> list[T]:
    return await aiometer.run_all(
        jobs,
        max_at_once=MAX_CONCURRENT_REQUESTS,
        max_per_second=1 / REQUEST_INTERVAL,
    )
