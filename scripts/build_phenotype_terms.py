#!/usr/bin/env python3
"""Build the compact GO-biological_process + HPO term dictionary bundled at
netmedex/data/phenotype_terms.json.

Run this once (or whenever go-basic.obo / hp.obo are refreshed) to regenerate the bundled index.
Not run at request time -- NetMedEx ships the compact JSON output, not the raw ~40MB OBO files.

Usage:
    python3 scripts/build_phenotype_terms.py --go go-basic.obo --hp hp.obo

Download sources:
    GO:  http://purl.obolibrary.org/obo/go/go-basic.obo
    HPO: http://purl.obolibrary.org/obo/hp.obo
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

STANZA_RE = re.compile(r"^\[(\w+)\]\s*$")
SYNONYM_RE = re.compile(r'^synonym:\s*"([^"]+)"\s+(EXACT|NARROW|BROAD|RELATED)\b')

# GO/HPO terms are written in American spelling. Each pattern here matches the AMERICAN root
# within an indexed term and substitutes the corresponding BRITISH root, producing an extra
# dictionary key that points at the same ID as the original American-spelled entry. Measured
# against a real 15-abstract sample, "hyperglycaemia" failing to match the indexed American
# "hyperglycemia" was one of only two concrete, repeatable, cheaply-fixable causes found for an
# otherwise-indexed term not matching. Deliberately targets specific known word-roots rather than a
# blind "e"->"ae" substitution, which would corrupt unrelated words that merely contain an "e".
_BRITISH_SPELLING_PATTERNS = [
    (re.compile(r"emia\b"), "aemia"),  # hyperglycemia -> hyperglycaemia, leukemia, ischemia
    (re.compile(r"\bhem(?=[aeiou])"), "haem"),  # hemoglobin, hemorrhage, hematology
    (re.compile(r"\bfet(?=[au])"), "foet"),  # fetal, fetus
    (re.compile(r"\bpediat"), "paediat"),  # pediatric
    (re.compile(r"\bedema\b"), "oedema"),
    (re.compile(r"\bceliac\b"), "coeliac"),
    (re.compile(r"\besophag"), "oesophag"),
    (re.compile(r"\bdiarrhea\b"), "diarrhoea"),
]

# A small, manually-reviewed whitelist of extremely common terms that are real, mappable GO/HPO
# concepts but were excluded by the EXACT/NARROW-only synonym filter because their only listed
# synonym relationship is BROAD or RELATED (looser than what the general rule accepts), or because
# they're common shorthand for a "response to X" GO term rather than a synonym at all. Kept as an
# explicit, reviewed list rather than broadening the general BROAD/RELATED inclusion rule, which
# would reintroduce the imprecise-mapping risk that rule was designed to avoid (see
# parse_obo_terms's docstring, e.g. "cell proliferation" as a RELATED synonym of the more specific
# "cell population proliferation").
_CURATED_EXTRA_TERMS = {
    "inflammation": ("GO:0006954", "inflammatory response", "BiologicalProcess"),
    "cell proliferation": ("GO:0008283", "cell population proliferation", "BiologicalProcess"),
    "oxidative stress": ("GO:0006979", "response to oxidative stress", "BiologicalProcess"),
    # Common experimental wording for the GO osteoblast-differentiation
    # process.  This is deliberately explicit rather than a broad semantic
    # expansion of every "-genic" adjective.
    "osteogenic differentiation": (
        "GO:0001649", "osteoblast differentiation", "BiologicalProcess"
    ),
}


def _british_spelling_variants(term: str) -> list[str]:
    variants = set()
    for pattern, replacement in _BRITISH_SPELLING_PATTERNS:
        if pattern.search(term):
            variants.add(pattern.sub(replacement, term))
    return list(variants)


def _iter_term_stanzas(path: Path):
    """Yield the raw line-list of every [Term] stanza in an OBO file."""
    in_term = False
    current: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            stanza_match = STANZA_RE.match(line)
            if stanza_match:
                if in_term and current:
                    yield current
                in_term = stanza_match.group(1) == "Term"
                current = []
                continue
            if in_term:
                current.append(line)
        if in_term and current:
            yield current


def parse_obo_terms(path: Path, namespace_filter: str | None):
    """Yield (id, name, synonyms, namespace) for each non-obsolete [Term] stanza.

    Only EXACT and NARROW synonyms are kept. NARROW synonyms are included because common,
    everyday terms (e.g. "apoptosis") are frequently curated as a NARROW synonym of a more
    precisely-scoped GO term (e.g. "apoptotic process") rather than an EXACT one -- excluding
    NARROW would miss many of the most common terms actually used in abstracts. BROAD/RELATED
    synonyms are excluded as too loose (e.g. "cell proliferation" is only a RELATED synonym of
    "cell population proliferation", a looser association not safe to treat as substitutable).
    """
    for stanza in _iter_term_stanzas(path):
        term_id = name = namespace = None
        is_obsolete = False
        synonyms: list[str] = []
        for line in stanza:
            if line.startswith("id:"):
                term_id = line.split(":", 1)[1].strip()
            elif line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("namespace:"):
                namespace = line.split(":", 1)[1].strip()
            elif line.startswith("is_obsolete:"):
                is_obsolete = line.split(":", 1)[1].strip() == "true"
            elif line.startswith("synonym:"):
                syn_match = SYNONYM_RE.match(line)
                if syn_match and syn_match.group(2) in ("EXACT", "NARROW"):
                    synonyms.append(syn_match.group(1))

        if not term_id or not name or is_obsolete:
            continue
        if namespace_filter is not None and namespace != namespace_filter:
            continue
        yield term_id, name, synonyms, namespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", type=Path, default=Path("go-basic.obo"))
    parser.add_argument("--hp", type=Path, default=Path("hp.obo"))
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "netmedex" / "data" / "phenotype_terms.json",
    )
    args = parser.parse_args()

    # term_string (lowercase) -> [ontology_id, canonical_name, entity_type]
    index: dict[str, list[str]] = {}
    stats = {"go_terms": 0, "hp_terms": 0, "go_names": 0, "hp_names": 0}

    if args.go.exists():
        for term_id, name, synonyms, _ns in parse_obo_terms(args.go, "biological_process"):
            stats["go_terms"] += 1
            for label in [name, *synonyms]:
                key = label.strip().lower()
                if len(key) < 4:  # skip too-short labels (e.g. "PSI") -- high false-positive risk
                    continue
                if key not in index:
                    index[key] = [term_id, name, "BiologicalProcess"]
                    stats["go_names"] += 1
    else:
        print(f"WARNING: {args.go} not found, skipping GO biological_process terms")

    if args.hp.exists():
        for term_id, name, synonyms, _ns in parse_obo_terms(args.hp, None):
            stats["hp_terms"] += 1
            for label in [name, *synonyms]:
                key = label.strip().lower()
                if len(key) < 4:
                    continue
                if key not in index:
                    index[key] = [term_id, name, "Phenotype"]
                    stats["hp_names"] += 1
    else:
        print(f"WARNING: {args.hp} not found, skipping HPO phenotype terms")

    # British spelling variants: generated from the already-indexed American keys, added only if
    # not already present (never overwrites a real GO/HPO-sourced entry).
    british_added = 0
    for key in list(index.keys()):
        for variant in _british_spelling_variants(key):
            if variant not in index:
                index[variant] = index[key]
                british_added += 1

    # Curated whitelist: reviewed high-value terms excluded by the EXACT/NARROW-only synonym
    # filter. Only fills gaps -- never overrides a real GO/HPO-sourced entry for the same key.
    curated_added = 0
    for key, value in _CURATED_EXTRA_TERMS.items():
        if key not in index:
            index[key] = list(value)
            curated_added += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))

    print(f"GO biological_process terms parsed: {stats['go_terms']} (unique labels indexed: {stats['go_names']})")
    print(f"HPO terms parsed: {stats['hp_terms']} (unique labels indexed: {stats['hp_names']})")
    print(f"British spelling variants added: {british_added}")
    print(f"Curated whitelist terms added: {curated_added}")
    print(f"Total dictionary entries: {len(index)}")
    print(f"Written to {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
