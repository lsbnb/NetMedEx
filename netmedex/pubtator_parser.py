from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path

from netmedex.pubtator_data import (
    PubTatorAnnotation,
    PubTatorArticle,
    PubTatorCollection,
    PubTatorLine,
    PubTatorRelation,
)

# Custom metadata header
HEADER_SYMBOL = "##"


class PubTatorIO:
    """Parse a PubTator file.

    Extra headers added by NetMedEx is also parsed.
    """

    @staticmethod
    def parse(filepath: str | Path) -> PubTatorCollection:
        articles: list[PubTatorArticle] = []
        with open(filepath) as stream:
            result = PubTatorIO._parse_header(stream)
            if (non_header_line := result.non_header_line) is not None:
                for article in PubTatorIterator(stream, non_header_line):
                    if article is None:
                        break
                    articles.append(article)

        return PubTatorCollection(result.headers, articles)

    @staticmethod
    def _parse_header(stream: TextIOBase) -> "PubTatorHeaderResult":
        headers = []
        for line in stream:
            if not line.startswith(HEADER_SYMBOL):
                return PubTatorHeaderResult(headers=headers, non_header_line=line)
            headers.append(line.replace(HEADER_SYMBOL, "", 1).strip())
        else:
            return PubTatorHeaderResult(headers=headers, non_header_line=None)


class PubTatorIterator:
    """Iterate a Pubtator file or string line by line (excluded header)"""

    def __init__(self, handle: str | Path | TextIOBase, first_line: str | None = None):
        if isinstance(handle, str):
            # Treat it as a string
            self.stream = iter(handle.splitlines())
        elif isinstance(handle, Path):
            self.stream = open(handle)
        elif isinstance(handle, TextIOBase):
            self.stream = handle

        if first_line is None:
            try:
                first_line = next(self.stream)
            except StopIteration:
                first_line = None
        self._line = first_line

    def __next__(self):
        line = self._line
        pmid = None
        title = None
        abstract = None
        annotations: list[PubTatorAnnotation] = []
        relations: list[PubTatorRelation] = []

        if line is None:
            raise StopIteration

        while (title := self._get_title(line)) is None:
            line = next(self.stream)

        pmid = line.split("|", 1)[0]
        has_tried_getting_abstract = False

        for line in self.stream:
            # See if the next line is the next article
            if self._get_title(line) is not None:
                break

            # Sometimes an article won't have a abstract, so use `has_tried_getting_abstract`
            if not has_tried_getting_abstract:
                if (abstract := self._get_abstract(line)) is not None:
                    has_tried_getting_abstract = True
                    continue

            line_instance = PubTatorLine.parse(line)
            if isinstance(line_instance, PubTatorAnnotation):
                has_tried_getting_abstract = True
                annotations.append(line_instance)
            elif isinstance(line_instance, PubTatorRelation):
                has_tried_getting_abstract = True
                relations.append(line_instance)

        # The first line of the next article
        self._line = line

        return PubTatorArticle(
            pmid=pmid,
            date=None,
            journal=None,
            title=title,
            abstract=abstract,
            annotations=annotations,
            relations=relations,
            identifiers=None,
            metadata=None,
        )

    @staticmethod
    def _get_title(line: str) -> str | None:
        # Title looks like: 962740|t|Dermal ulceration of mullet
        result = line.split("|", 2)
        if len(result) < 3 or result[1] != "t":
            return None
        else:
            return result[2].rstrip("\n")

    @staticmethod
    def _get_abstract(line: str) -> str | None:
        # Abstract looks like: 962740|a|Phycomycotic granulomas are described
        result = line.split("|", 2)
        if len(result) < 3 or result[1] != "a":
            return None
        else:
            return result[2].rstrip("\n")

    def __iter__(self):
        return self


@dataclass
class PubTatorHeaderResult:
    headers: list[str]
    non_header_line: str | None
