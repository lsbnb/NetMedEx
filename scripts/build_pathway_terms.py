#!/usr/bin/env python3
"""Build the compact KEGG + Reactome pathway-name dictionary bundled at
netmedex/data/pathway_terms.json.

Mirrors scripts/build_phenotype_terms.py's approach but for named signaling/metabolic pathways
(e.g. "PI3K-Akt signaling pathway", "Wnt signaling pathway") rather than GO biological processes --
a distinct entity category: a pathway is a named, ID-bearing concept a paper invokes directly
("activates the PI3K/AKT pathway"), which is different from the biological-process outcome the
pathway leads to (see netmedex/phenotype_ner.py).

Usage:
    python3 scripts/build_pathway_terms.py --reactome ReactomePathways.txt --kegg kegg_pathways.txt

Download sources:
    Reactome: https://reactome.org/download/current/ReactomePathways.txt
    KEGG:     https://rest.kegg.jp/list/pathway
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Papers inconsistently write compound pathway names with a hyphen or a slash (e.g.
# "PI3K-Akt signaling pathway" vs "PI3K/Akt signaling pathway"). Generating the alternate-
# punctuation variant as an extra dictionary key (pointing at the same ID) catches both.
_HYPHEN_SLASH_RE = re.compile(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])")
_SLASH_RE = re.compile(r"(?<=[A-Za-z0-9])/(?=[A-Za-z0-9])")

# Reactome's ~27 root-level pathway categories (e.g. "Disease", "Metabolism", "Signal
# Transduction") are real pathway IDs but far too generic as text-match keys -- "disease" or
# "metabolism" appears constantly in ordinary biomedical prose with no connection to Reactome's
# specific top-level grouping. Indexing them turns every such word into a false-positive pathway
# match, so they're excluded by name (case-insensitive) rather than relying on a length/specificity
# heuristic, since some (e.g. "Hemostasis") are short but not actually ambiguous.
_REACTOME_ROOT_CATEGORIES = {
    "autophagy", "cell cycle", "cellular responses to stimuli", "chromatin organization",
    "circadian clock", "developmental biology", "digestion and absorption", "disease",
    "dna repair", "dna replication", "extracellular matrix organization",
    "gene expression (transcription)", "hemostasis", "immune system", "metabolism",
    "metabolism of proteins", "metabolism of rna", "muscle contraction", "neuronal system",
    "organelle biogenesis and maintenance", "programmed cell death", "protein localization",
    "reproduction", "sensory perception", "signal transduction", "transport of small molecules",
    "vesicle-mediated transport",
}

# Literature often uses compact pathway-family labels that are absent from the
# official display names. These aliases remain ontology-backed: each maps to one
# existing KEGG reference pathway rather than creating a free-text node.
_CURATED_ALIASES = {
    "pi3k/akt pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "pi3k-akt pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "pi3k/akt signaling": ("map04151", "PI3K-Akt signaling pathway"),
    "pi3k/akt/mtor": ("map04151", "PI3K-Akt signaling pathway"),
    "pi3k/akt/mtor pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "pi3k/akt/mtor signaling pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "pten/pi3k/akt/hif-1alpha pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "pten/pi3k/akt/hif1alpha pathway": ("map04151", "PI3K-Akt signaling pathway"),
    "jak/stat pathway": ("map04630", "JAK-STAT signaling pathway"),
    "jak-stat pathway": ("map04630", "JAK-STAT signaling pathway"),
    "mapk pathway": ("map04010", "MAPK signaling pathway"),
    "wnt pathway": ("map04310", "Wnt signaling pathway"),
}


def _punctuation_variants(term: str) -> list[str]:
    variants = []
    if _HYPHEN_SLASH_RE.search(term):
        variants.append(_HYPHEN_SLASH_RE.sub("/", term))
    if _SLASH_RE.search(term):
        variants.append(_SLASH_RE.sub("-", term))
    return variants


def parse_reactome(path: Path, species: str = "Homo sapiens"):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            stable_id, name, line_species = parts
            if line_species != species:
                continue
            yield stable_id, name


def parse_kegg(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            map_id, name = parts
            # KEGG pathway names are sometimes suffixed "- Homo sapiens (human)"; strip it.
            name = re.sub(r"\s*-\s*Homo sapiens \(human\)\s*$", "", name)
            yield map_id, name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reactome", type=Path, default=Path("ReactomePathways.txt"))
    parser.add_argument("--kegg", type=Path, default=Path("kegg_pathways.txt"))
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "netmedex" / "data" / "pathway_terms.json",
    )
    args = parser.parse_args()

    index: dict[str, list[str]] = {}
    stats = {"reactome": 0, "kegg": 0}

    if args.reactome.exists():
        for stable_id, name in parse_reactome(args.reactome):
            key = name.strip().lower()
            if len(key) < 4 or key in _REACTOME_ROOT_CATEGORIES:
                continue
            if key not in index:
                index[key] = [stable_id, name, "Pathway"]
                stats["reactome"] += 1
    else:
        print(f"WARNING: {args.reactome} not found, skipping Reactome pathways")

    if args.kegg.exists():
        for map_id, name in parse_kegg(args.kegg):
            key = name.strip().lower()
            if len(key) < 4:
                continue
            if key not in index:
                index[key] = [map_id, name, "Pathway"]
                stats["kegg"] += 1
    else:
        print(f"WARNING: {args.kegg} not found, skipping KEGG pathways")

    punctuation_added = 0
    for key in list(index.keys()):
        for variant in _punctuation_variants(key):
            if variant not in index:
                index[variant] = index[key]
                punctuation_added += 1

    curated_added = 0
    for alias, (ontology_id, canonical_name) in _CURATED_ALIASES.items():
        if alias not in index:
            index[alias] = [ontology_id, canonical_name, "Pathway"]
            curated_added += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))

    print(f"Reactome (Homo sapiens) pathways indexed: {stats['reactome']}")
    print(f"KEGG reference pathways indexed: {stats['kegg']}")
    print(f"Hyphen/slash punctuation variants added: {punctuation_added}")
    print(f"Curated literature aliases added: {curated_added}")
    print(f"Total dictionary entries: {len(index)}")
    print(f"Written to {args.output} ({args.output.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
