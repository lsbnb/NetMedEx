from __future__ import annotations

import re

from netmedex.pubtator_data import PubTatorArticle


def convert_to_ris(articles: list[PubTatorArticle]) -> str:
    """
    Convert a list of PubTatorArticle objects to a RIS format string.
    RIS (Research Information Systems) is a standardized tag format for
    bibliographic data, compatible with EndNote, Zotero, etc.
    """
    ris_lines = []
    for article in articles:
        ris_lines.append("TY  - JOUR")
        ris_lines.append(f"TI  - {article.title}")

        # Authors extraction
        authors_raw = ""
        if article.metadata:
            authors_raw = article.metadata.get("authors", article.metadata.get("authors_list", ""))

        if authors_raw:
            if isinstance(authors_raw, str):
                # Standard format: "Author1, Author2" or "Author1; Author2"
                delimiter = ";" if ";" in authors_raw else ","
                for author in authors_raw.split(delimiter):
                    author_clean = author.strip()
                    if author_clean:
                        ris_lines.append(f"AU  - {author_clean}")
            elif isinstance(authors_raw, list):
                for author in authors_raw:
                    ris_lines.append(f"AU  - {author}")

        if article.journal:
            # Clean journal string (sometimes contains date/doi in some PubTator outputs)
            journal_clean = article.journal.split(".")[0].strip()
            ris_lines.append(f"JO  - {journal_clean}")

        # Year extraction
        year = ""
        if article.date:
            match = re.search(r"(\d{4})", str(article.date))
            if match:
                year = match.group(1)

        if not year and article.metadata:
            year = article.metadata.get("year", "")

        if year:
            ris_lines.append(f"PY  - {year}")

        if article.doi:
            ris_lines.append(f"DO  - {article.doi}")

        # Citation count (internal metadata)
        if article.metadata and "citation_count" in article.metadata:
            count = article.metadata["citation_count"]
            ris_lines.append(f"N1  - Cited by: {count} (source: OpenCitations)")

        ris_lines.append(f"AN  - {article.pmid}")
        ris_lines.append(f"UR  - https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/")
        ris_lines.append("ER  - ")
        ris_lines.append("")  # Separator

    return "\n".join(ris_lines)
