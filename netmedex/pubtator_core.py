# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
import json
import logging
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from queue import Queue
from typing import Literal

import requests
from requests import Response, Session
from tqdm.auto import tqdm

from netmedex.biocjson_parser import biocjson_to_pubtator
from netmedex.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest

# API GET limit: 100
PMID_REQUEST_SIZE = 100
# Fall back to "search" if "cite" failed
FALLBACK_SEARCH = True

# users post no more than three requests per second
# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
SLEEP = 0.5

# Full text annotation is only availabe in `biocxml` and `biocjson` formats
# RESPONSE_FORMAT = ["pubtator", "biocxml", "biocjson"][2]
logger = logging.getLogger(__name__)


class PubTatorAPI:
    def __init__(
        self,
        query: str | None,
        pmid_list: Sequence[str] | None,
        savepath: str | None,
        search_type: Literal["query", "pmids"],
        sort: Literal["score", "date"],
        max_articles: int,
        use_mesh: bool,
        full_text: bool,
        debug: bool,
        queue: Queue | None = None,
    ):
        self.query = query
        self.pmid_list = pmid_list
        self.savepath = savepath
        self.search_type = search_type
        self.sort = sort
        self.max_articles = max_articles
        self.use_mesh = use_mesh
        self.full_text = full_text
        self.debug = debug
        self.queue = queue
        self.api_method = "cite" if sort == "date" else "search"
        self.return_progress = isinstance(queue, Queue)

    def run(self):
        if self.search_type == "query":
            if self.query is None or self.query.strip() == "":
                raise EmptyInput
            self.pmid_list = self.get_query_results()
        elif self.search_type == "pmids":
            if not self.pmid_list:
                raise EmptyInput

        if not self.pmid_list:
            raise NoArticles

        search_results = self.batch_publication_search()

        if self.use_mesh or self.full_text:
            retain_ori_text = False if self.use_mesh else True
            search_results = [
                biocjson_to_pubtator(
                    articles, retain_ori_text=retain_ori_text, role_type="identifier"
                )
                for articles in search_results
            ]

        self._write_results(search_results)

    def get_query_results(self):
        logger.info(f"Query: {self.query}")
        if self.api_method == "search":
            article_list = self._get_by_search()
        elif self.api_method == "cite":
            article_list = self._get_by_cite()

        return article_list

    def _get_by_search(self):
        res = send_search_query(self.query, type="search")

        article_list = []
        if not request_successful(res):
            return article_list

        res_json = res.json()
        total_articles = int(res_json["count"])
        page_size = int(res_json["page_size"])
        article_list.extend(get_article_ids(res_json))

        n_articles_to_request = get_n_articles(self.max_articles, total_articles)

        # Get search results in different pages until the max_articles is reached
        logger.info("Obtaining article PMIDs...")
        current_page = 1
        with Session() as session:
            with tqdm(total=n_articles_to_request, file=sys.stdout) as pbar:
                while current_page * page_size < n_articles_to_request:
                    current_page += 1
                    res = send_search_query_with_page(self.query, current_page, self.sort, session)
                    if request_successful(res):
                        article_list.extend(get_article_ids(res.json()))
                    pbar.update(page_size)
                    if self.return_progress:
                        self.queue.put(progress_message("search-search", pbar.n, pbar.total))
                pbar.n = pbar.total

        return article_list[:n_articles_to_request]

    def _get_by_cite(self):
        logger.info("Obtaining article PMIDs...")
        res = send_search_query(self.query, type="cite")
        if not request_successful(res):
            if FALLBACK_SEARCH:
                logger.warning("Fetching articles by 'cite' method failed. Switch to 'search'.")
                return self._get_by_search()
            else:
                unsuccessful_query(res.status_code)

        pmid_list = parse_cite_response(res.text)
        n_articles_to_request = get_n_articles(self.max_articles, len(pmid_list))
        if self.return_progress:
            self.queue.put(
                progress_message("search-cite", n_articles_to_request, n_articles_to_request)
            )

        return pmid_list[:n_articles_to_request]

    def batch_publication_search(self):
        results = []
        format = "biocjson" if self.use_mesh or self.full_text else "pubtator"
        with Session() as session:
            with tqdm(total=len(self.pmid_list), file=sys.stdout) as pbar:
                for start in range(0, len(self.pmid_list), PMID_REQUEST_SIZE):
                    end = start + PMID_REQUEST_SIZE
                    end = end if end < len(self.pmid_list) else None
                    res = send_publication_query(
                        pmid_string=",".join(self.pmid_list[start:end]),
                        article_id_type="pmids",
                        format=format,
                        full_text=self.full_text,
                        session=session,
                    )
                    if request_successful(res):
                        results.extend(self._append_json_or_text(res))
                    if end is not None:
                        pbar.update(PMID_REQUEST_SIZE)
                    else:
                        pbar.n = len(self.pmid_list)

                    if self.return_progress:
                        self.queue.put(progress_message("get", pbar.n, pbar.total))

        if self.return_progress:
            self.queue.put(None)

        if self.debug:
            now = datetime.now().strftime("%y%m%d%H%M%S")
            with open(f"./pubtator3_response_{now}.txt", "w") as f:
                f.writelines([json.dumps(o) + "\n" for o in results])
            with open(f"./pubtator3_pmid_{now}.txt", "w") as f:
                f.writelines([f"{id}\n" for id in self.pmid_list])
        return results

    def _append_json_or_text(self, res: Response):
        if self.full_text or self.use_mesh:
            if len(res.text.split("\n")) > 2:
                content = [json.loads(text) for text in res.text.split("\n")[:-1]]
            else:
                content = [res.json()]
        else:
            content = [res.text]

        return content

    def _write_results(self, results):
        if self.savepath is None:
            return

        header = []

        if self.use_mesh:
            header.append("##USE-MESH-VOCABULARY")
        if len(header) > 0:
            header.append("\n")

        with open(self.savepath, "w") as f:
            f.writelines(header)
            f.writelines(results)
            logger.info(f"Save to {self.savepath}")


def send_search_query(
    query: str,
    type: Literal["search", "cite"],
    session: Session | None = None,
):
    if type == "search":
        url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    elif type == "cite":
        url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv"
    res = handle_session_get(url, params={"text": query}, session=session)
    time.sleep(SLEEP)
    return res


def send_search_query_with_page(
    query: str,
    page: int,
    sort: Literal["score", "date"],
    session: Session | None = None,
):
    url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    if sort == "score":
        params = {"text": query, "sort": "score desc", "page": page}
    elif sort == "date":
        params = {"text": query, "sort": "date desc", "page": page}
    res = handle_session_get(url, params, session)
    time.sleep(SLEEP)
    return res


def send_publication_query(
    pmid_string: str,
    article_id_type: Literal["pmids", "pmcids"],
    format: Literal["biocjson", "pubtator"],
    full_text: bool,
    session: Session | None = None,
):
    url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{format}"
    params = {article_id_type: pmid_string}
    if full_text:
        params["full"] = "true"
    res = handle_session_get(url, params, session)
    time.sleep(SLEEP)
    return res


def get_n_articles(max_articles: int, total_articles: int):
    logger.info(f"Find {total_articles} articles")
    n_articles_to_request = max_articles if total_articles > max_articles else total_articles
    logger.info(f"Requesting {n_articles_to_request} articles...")
    return n_articles_to_request


def get_article_ids(res_json):
    return [str(article.get("pmid")) for article in res_json["results"]]


def parse_cite_response(res_text: str):
    pmid_list = []
    for line in res_text.split("\n"):
        if line.startswith("#") or line == "":
            continue
        # [pmid, title, journal]
        pmid = line.split("\t")[0]
        pmid_list.append(pmid)
    return pmid_list


def request_successful(res: Response):
    if res.status_code != 200:
        logger.info("Unsuccessful request")
        logger.debug(f"Response status code: {res.status_code}")
        return False
    return True


def unsuccessful_query(status_code: int):
    if status_code == 502:
        msg = "Possibly too many articles. Please try more specific queries."
    else:
        msg = "Please retry later."

    raise UnsuccessfulRequest(msg)


def handle_session_get(url: str, params, session: Session | None = None):
    try:
        res = session.get(url, params=params)
    except Exception:
        res = requests.get(url, params=params)

    return res


def progress_message(status, progress, total):
    return f"{status}/{progress}/{total}"
