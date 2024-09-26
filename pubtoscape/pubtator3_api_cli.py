# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Literal, Optional, Union

import requests
from tqdm.auto import tqdm

from pubtoscape.biocjson_parser import convert_to_pubtator
from pubtoscape.exceptions import EmptyInput, NoArticles, UnsuccessfulRequest
from pubtoscape.utils import config_logger

# API GET limit: 100
PMID_REQUEST_SIZE = 100
QUERY_METHOD = ["search", "cite"][1]
# Full text annotation is only availabe in `biocxml` and `biocjson` formats
# RESPONSE_FORMAT = ["pubtator", "biocxml", "biocjson"][2]
debug = False
logger = logging.getLogger(__name__)


def main():
    global debug

    args = parse_args(sys.argv[1:])
    debug = args.debug
    log_file = "pubtator3" if debug else None

    config_logger(debug, log_file)

    if sum(arg is not None for arg in [args.pmids, args.pmid_file, args.query]) != 1:
        logger.info("Please specify only one of the following: --query, --pmids, --pmid_file")
        sys.exit()

    if args.query is not None:
        search_type = "query"
    elif args.pmids is not None:
        search_type = "pmids"
        pmids = load_pmids(args.pmids, load_from="string")
        logger.info(f"Find {len(pmids)} PMIDs")
    elif args.pmid_file is not None:
        search_type = "pmids"
        logger.info(f"Load PMIDs from: {args.pmid_file}")
        pmids = load_pmids(args.pmid_file, load_from="file")
        logger.info(f"Find {len(pmids)} PMIDs")

    suffix = args.query if search_type == "query" else f"{pmids[0]}_total_{len(pmids)}"
    query = args.query if search_type == "query" else pmids
    savepath = create_savepath(args.output, type=search_type, suffix=suffix)

    try:
        run_query_pipeline(query=query,
                           savepath=savepath,
                           type=search_type,
                           max_articles=args.max_articles,
                           full_text=args.full_text,
                           use_mesh=args.use_mesh)
    except (NoArticles, EmptyInput, UnsuccessfulRequest) as e:
        logger.error(str(e))


def load_pmids(input_data, load_from: Literal["string", "file"]):
    if load_from == "string":
        pmids = input_data.split(",")
    elif load_from == "file":
        pmids = []
        with open(input_data) as f:
            for line in f.readlines():
                pmids.extend(line.strip().split(","))

    pmids = drop_if_not_num(pmids)

    return pmids


def run_query_pipeline(query: Union[str, list],
                       savepath: Union[str, Path],
                       type: Literal["query", "pmids"],
                       max_articles: int = 1000,
                       full_text: bool = False,
                       use_mesh: bool = False,
                       queue: Optional[Queue] = None):

    if type == "query":
        if query is None or query.strip() == "":
            raise EmptyInput
        pmid_list = get_search_results(query, max_articles)
    elif type == "pmids":
        if not query:
            raise EmptyInput
        pmid_list = query

    if not pmid_list:
        raise NoArticles

    output = batch_publication_query(pmid_list,
                                     type="pmids",
                                     full_text=full_text,
                                     use_mesh=use_mesh,
                                     queue=queue)

    if use_mesh or full_text:
        retain_ori_text = False if use_mesh else True
        output = [
            convert_to_pubtator(articles,
                                retain_ori_text=retain_ori_text,
                                role_type="identifier") for articles in output
        ]

    write_output(output, savepath=savepath, use_mesh=use_mesh)


def get_search_results(query, max_articles):
    logger.info(f"Query: {query}")
    if QUERY_METHOD == "search":
        article_list = get_by_search(query, max_articles)
    elif QUERY_METHOD == "cite":
        article_list = get_by_cite(query, max_articles)

    return article_list


def get_by_search(query, max_articles):
    res = send_search_query(query, type="search")

    article_list = []
    if not request_successful(res):
        return article_list

    res_json = res.json()
    total_articles = int(res_json["count"])
    page_size = int(res_json["page_size"])
    article_list.extend(get_article_ids(res_json))

    n_articles_to_request = get_n_articles(max_articles, total_articles)

    # Get search results in different pages until the max_articles is reached
    logger.info("Obtaining article PMIDs...")
    current_page = 1
    with requests.Session() as session:
        with tqdm(total=n_articles_to_request, file=sys.stdout) as pbar:
            while current_page * page_size < n_articles_to_request:
                pbar.update(page_size)
                current_page += 1
                res = send_search_query_with_page(query, current_page, session)
                if request_successful(res):
                    article_list.extend(get_article_ids(res.json()))
            pbar.n = pbar.total

    return article_list[:n_articles_to_request]


def send_search_query(query, type: Literal["search", "cite"] = QUERY_METHOD):
    if type == "search":
        url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    elif type == "cite":
        url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv"
    res = requests.get(url, params={"text": query})
    time.sleep(0.5)
    return res


def send_search_query_with_page(query, page, session=None):
    url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    params = {"text": query, "sort": "score desc", "page": page}
    res = handle_session_get(url, params, session)
    time.sleep(0.5)
    return res


def get_n_articles(max_articles, total_articles):
    logger.info(f"Find {total_articles} articles")
    n_articles_to_request = max_articles if total_articles > max_articles else total_articles
    logger.info(f"Requesting {n_articles_to_request} articles...")
    return n_articles_to_request


def get_by_cite(query, max_articles):
    logger.info("Obtaining article PMIDs...")
    res = send_search_query(query, type="cite")
    if not request_successful(res):
        unsuccessful_query(res.status_code)

    pmid_list = parse_cite_response(res.text)
    n_articles_to_request = get_n_articles(max_articles, len(pmid_list))

    return pmid_list[:n_articles_to_request]


def unsuccessful_query(status_code):
    if status_code == 502:
        msg = "Possibly too many articles. Please try more specific queries."
    else:
        msg = "Please retry later."

    logger.warning(msg)
    raise UnsuccessfulRequest(msg)


def parse_cite_response(res_text):
    pmid_list = []
    for line in res_text.split("\n"):
        if line.startswith("#") or line == "":
            continue
        # [pmid, title, journal]
        pmid = line.split("\t")[0]
        pmid_list.append(pmid)
    return pmid_list


def handle_session_get(url, params, session):
    try:
        res = session.get(url, params=params)
    except Exception:
        res = requests.get(url, params=params)

    return res


def request_successful(res):
    if res.status_code != 200:
        logger.info("Unsuccessful request")
        logger.debug(f"Response status code: {res.status_code}")
        return False
    return True


def get_article_ids(res_json):
    return [str(article.get("pmid")) for article in res_json["results"]]


def batch_publication_query(id_list, type,
                            full_text=False,
                            use_mesh=False,
                            queue=None):
    return_progress = isinstance(queue, Queue)
    output = []
    format = "biocjson" if use_mesh or full_text else "pubtator"
    with requests.Session() as session:
        with tqdm(total=len(id_list), file=sys.stdout) as pbar:
            for start in range(0, len(id_list), PMID_REQUEST_SIZE):
                end = start + PMID_REQUEST_SIZE
                end = end if end < len(id_list) else None
                res = send_publication_query(
                    ",".join(id_list[start:end]),
                    type=type, format=format, full_text=full_text,
                    session=session)
                if request_successful(res):
                    output.extend(append_json_or_text(res, full_text, use_mesh))
                if end is not None:
                    pbar.update(PMID_REQUEST_SIZE)
                else:
                    pbar.n = len(id_list)

                if return_progress:
                    queue.put(f"{pbar.n}/{len(id_list)}")

    if return_progress:
        queue.put(None)

    global debug
    if debug:
        now = datetime.now().strftime("%y%m%d%H%M%S")
        with open(f"./pubtator3_api_{now}.txt", "w") as f:
            f.writelines([json.dumps(o) + "\n" for o in output])

    return output


def send_publication_query(article_id, type: Literal["pmids", "pmcids"], format,
                           full_text=False, session=None):
    url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{format}"
    params = {type: article_id}
    if full_text:
        params["full"] = "true"
    res = handle_session_get(url, params, session)
    time.sleep(0.5)
    return res


def append_json_or_text(res, full_text, use_mesh):
    if full_text or use_mesh:
        if len(res.text.split("\n")) > 2:
            content = [json.loads(text) for text in res.text.split("\n")[:-1]]
        else:
            content = [res.json()]
    else:
        content = [res.text]

    return content


def write_output(output, savepath: Path, use_mesh=False):
    header = []

    if use_mesh:
        header.append("##USE-MESH-VOCABULARY")
    if len(output) > 0:
        header.append("\n")

    with open(savepath, "w") as f:
        f.writelines(header)
        f.writelines(output)
        logger.info(f"Save to {str(savepath)}")


def drop_if_not_num(id_list):
    checked_list = []
    for id in id_list:
        id = id.strip()
        try:
            _ = int(id)
            checked_list.append(id)
        except ValueError:
            pass

    return checked_list


def create_savepath(output_path, type, suffix):
    if output_path is None:
        if type == "query":
            savepath = Path(f"./query_{suffix}.pubtator")
        elif type == "pmids":
            savepath = Path(f"./pmids_{suffix}.pubtator")
    else:
        savepath = Path(output_path)
        savepath.parent.mkdir(parents=True, exist_ok=True)

    return savepath


def parse_args(args):
    parser = setup_argparsers()
    return parser.parse_args(args)


def setup_argparsers():
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--query", default=None,
                        help="Query string")
    parser.add_argument("-o", "--output", default=None,
                        help="Output path")
    parser.add_argument("-p", "--pmids", default=None, type=str,
                        help="PMIDs for the articles (comma-separated)")
    parser.add_argument("-f", "--pmid_file", default=None,
                        help="Filepath to load PMIDs")
    parser.add_argument("--max_articles", type=int, default=1000,
                        help="Maximal articles to request from the searching result (default: 1000)")
    parser.add_argument("--full_text", action="store_true",
                        help="Collect full-text annotations if available")
    parser.add_argument("--use_mesh", action="store_true",
                        help="Use MeSH vocabulary instead of the most commonly used original text in articles")
    parser.add_argument("--debug", action="store_true",
                        help="Print debug information")

    return parser


if __name__ == "__main__":
    main()
