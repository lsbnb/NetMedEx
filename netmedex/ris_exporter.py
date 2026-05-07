from __future__ import annotations

import re

from rispy import dumps
from rispy.writer import RisWriter

from netmedex.pubtator_data import PubTatorArticle


class EndnoteRisWriter(RisWriter):
    def set_header(self, count: int) -> str:  # noqa: D102
        return ""


def _normalize_authors(article: PubTatorArticle) -> list[str]:
    """Extract and normalize authors from PubTatorArticle metadata."""
    if not article.metadata:
        return []

    authors_raw = article.metadata.get("authors", article.metadata.get("authors_list", ""))

    if isinstance(authors_raw, list):
        return [str(author).strip() for author in authors_raw if str(author).strip()]

    if isinstance(authors_raw, str):
        # BioC-JSON often provides a comma-separated or semicolon-separated string.
        # pubtator3 format: "Abalsamo L, Spadaro F, Bozzuto G, ..."
        if ";" in authors_raw:
            return [a.strip() for a in authors_raw.split(";") if a.strip()]
        if "," in authors_raw:
            # Heuristic: split by comma if there are multiple parts that look like authors (Last FI)
            parts = [a.strip() for a in authors_raw.split(",") if a.strip()]
            if len(parts) > 1:
                return parts
        return [authors_raw.strip()]

    return []


def _extract_year(article: PubTatorArticle) -> str | None:
    if article.date:
        match = re.search(r"(\d{4})", str(article.date))
        if match:
            return match.group(1)

    if article.metadata:
        year = article.metadata.get("year")
        if year:
            return str(year)

    return None


def _parse_pages(pages: str) -> tuple[str | None, str | None]:
    if not pages:
        return None, None

    cleaned = pages.strip()
    if not cleaned:
        return None, None

    parts = re.split(r"[-–—]", cleaned, maxsplit=1)
    start = parts[0].strip()
    end = parts[1].strip() if len(parts) > 1 else None
    return (start or None, end or None)


def convert_to_ris(articles: list[PubTatorArticle]) -> str:
    records = []
    for article in articles:
        record: dict[str, str | list[str]] = {"type_of_reference": "JOUR"}

        if article.title:
            record["title"] = article.title

        authors = _normalize_authors(article)
        if authors:
            record["authors"] = authors

        if article.journal:
            record["journal_name"] = article.journal

        year = _extract_year(article)
        if year:
            record["year"] = year
            record["publication_year"] = year

        if article.date:
            record["date"] = str(article.date)

        if article.volume:
            record["volume"] = str(article.volume)

        if article.issue:
            record["number"] = str(article.issue)

        start_page, end_page = _parse_pages(article.pages or "")
        if start_page:
            record["start_page"] = start_page
        if end_page:
            record["end_page"] = end_page

        if article.doi:
            record["doi"] = article.doi

        if article.abstract:
            record["abstract"] = article.abstract

        record["accession_number"] = str(article.pmid)
        record["urls"] = [f"https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/"]

        if article.metadata and "citation_count" in article.metadata:
            record["notes"] = [f"Cited by: {article.metadata['citation_count']} (source: OpenCitations)"]

        records.append(record)

    if not records:
        return ""

    return dumps(records, implementation=EndnoteRisWriter)
