"""User-defined entity dictionary for concepts PubTator3 does not annotate.

PubTator3 tags genes, chemicals, diseases, species, cell lines, variants (and,
in NetMedEx, GO/HPO/KEGG/Reactome terms), but not every research concept: for
example extracellular vesicles / exosomes or mesenchymal stem cells have no
entity type, so a graph about them has no node for them and semantic
extraction never relates them to anything. A dictionary adds such concepts as
ordinary annotations before the graph is built, so node creation and relation
extraction then treat them like any PubTator entity.

Dictionary: a TSV file, one concept per line, `#` comments allowed:

    id <TAB> type <TAB> display name <TAB> synonym|synonym|...

    DICT:EV   Chemical  extracellular vesicles  extracellular vesicle|exosome|exosomes|EVs|sEV
    DICT:MSC  CellLine  mesenchymal stem cells  mesenchymal stromal cells|MSC|MSCs|BMSCs

Matching is whole-word. A synonym written entirely in lower case matches in any
case; one containing an upper-case letter is treated as an abbreviation and
matched case-sensitively, so "EV"/"MSC" never match ordinary words. Where a
match overlaps an annotation PubTator already made, PubTator's annotation is
kept. Used by `netmedex network --entity_dict FILE`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


@dataclass
class DictEntity:
    id: str
    type: str
    name: str
    pattern: re.Pattern


def load_entity_dict(path: str | Path) -> list[DictEntity]:
    entities = []
    for line_no, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3:
            raise ValueError(f"{path}:{line_no}: expected 'id<TAB>type<TAB>name[<TAB>synonyms]'")
        concept_id, ntype, name = parts[:3]
        synonyms = {name, *(s.strip() for s in (parts[3] if len(parts) > 3 else "").split("|"))}
        synonyms = sorted((s for s in synonyms if s), key=len, reverse=True)
        alternatives = [
            re.escape(s) if any(c.isupper() for c in s) else f"(?i:{re.escape(s)})"
            for s in synonyms
        ]
        pattern = re.compile(rf"(?<![\w-])(?:{'|'.join(alternatives)})(?![\w-])")
        entities.append(DictEntity(concept_id, ntype, name, pattern))
    return entities


def annotate_article(article: PubTatorArticle, entities: list[DictEntity]) -> int:
    """Add dictionary matches to `article.annotations`; returns how many."""
    title = article.title or ""
    sections = [(0, title), (len(title) + 1, article.abstract or "")]
    taken = [(a.start, a.end) for a in article.annotations]
    added = 0
    for entity in entities:
        for offset, text in sections:
            for m in entity.pattern.finditer(text):
                start, end = offset + m.start(), offset + m.end()
                if any(start < e and s < end for s, e in taken):
                    continue
                article.annotations.append(PubTatorAnnotation(
                    pmid=article.pmid, start=start, end=end, name=m.group(0),
                    identifier_name=entity.name, type=entity.type, mesh=entity.id))
                taken.append((start, end))
                added += 1
    article.annotations.sort(key=lambda a: a.start)
    return added
