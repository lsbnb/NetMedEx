"""Optional merging of nodes that name the same concept under different ids.

Enabled with ``PubTatorGraphBuilder(merge_duplicates=True)`` /
``netmedex network --merge_duplicates``; off by default, so graphs keep one
node per PubTator identifier unless asked otherwise.

PubTator3 gives one concept several identifiers in common cases:
- species orthologs: one NCBI Gene id per species (human IL6 3569, mouse Il6
  16193, rat Il6 24498 ...), so a mixed human/animal corpus splits one gene's
  evidence over several thin edges;
- the same term in different vocabularies: a GO process, a KEGG/Reactome
  pathway, an HPO phenotype and a MeSH disease named alike ("ferroptosis",
  "apoptosis", "hepatocellular carcinoma");
- ad-hoc nodes (no identifier) that duplicate a standard one, often mis-typed;
- one gene under two display names ("il-6" vs "interleukin 6").

Rules: same name and type -> merge; Disease / Phenotype / BiologicalProcess /
Pathway with the same name -> merge; ad-hoc nodes join the standard node of the
same name; genes whose names are *each other's* aliases -> merge pairwise
(one-way aliases are noisy: PubTator maps combined mentions such as "Smad2/3/4"
to several genes). Gene vs chemical stays apart (insulin the gene is not
insulin the drug). The kept node is the best-connected one; merged ids are
recorded in node["merged_ids"] and every name and alias stays an alias, so
search by any of them still finds the node.
"""
from __future__ import annotations

import re
from collections import defaultdict

import networkx as nx

CONCEPT_TYPES = {"Disease", "Phenotype", "BiologicalProcess", "Pathway", "CellularComponent"}
_PER_PMID_FIELDS = ("relations", "confidences", "evidences", "mechanism_events")
_MIRNA_NUMBER = re.compile(r"(?:mir|microrna|mirna)[-\s]?(\d+[a-z]?)")


def _name(G, n) -> str:
    return str(G.nodes[n].get("name", "")).strip().lower()


def _is_adhoc(G, n) -> bool:
    return str(G.nodes[n].get("mesh") or "-") in ("-", "")


def _keep_rank(G, protected: set[str]):
    return lambda n: (n in protected, not _is_adhoc(G, n), G.degree(n),
                      len(G.nodes[n].get("pmids") or ()), str(n))


def merge_into(G: nx.Graph, keep: str, drop: str) -> None:
    """Fold node `drop` into `keep`: PMIDs, aliases, species context and every
    edge (per-PMID relation / confidence / evidence records are unioned)."""
    kd, dd = G.nodes[keep], G.nodes[drop]
    kd["pmids"] = set(kd.get("pmids") or ()) | set(dd.get("pmids") or ())
    aliases = set(kd.get("aliases") or ()) | set(dd.get("aliases") or ())
    aliases.add(dd.get("name"))
    kd["aliases"] = {a for a in aliases if a}
    species = dict(dd.get("study_species_by_pmid") or {})
    species.update(kd.get("study_species_by_pmid") or {})
    kd["study_species_by_pmid"] = species
    kd["merged_ids"] = sorted(set(kd.get("merged_ids") or ()) | {drop}
                              | set(dd.get("merged_ids") or ()))
    for _, nb, ed in list(G.edges(drop, data=True)):
        if nb == keep:
            continue
        ed = dict(ed)
        if ed.get("source_id") == drop:
            ed["source_id"] = keep
        if not G.has_edge(keep, nb):
            G.add_edge(keep, nb, **ed)
            continue
        target = G.edges[keep, nb]
        for field in _PER_PMID_FIELDS:
            incoming = ed.get(field) or {}
            if not incoming:
                continue
            merged = dict(target.get(field) or {})
            for pmid, value in incoming.items():
                if pmid not in merged:
                    merged[pmid] = value
                elif isinstance(value, set):
                    merged[pmid] = set(merged[pmid]) | value
                elif isinstance(value, dict):
                    merged[pmid] = {**value, **merged[pmid]}
            target[field] = merged
    G.remove_node(drop)


def _name_groups(G, protected) -> list[list[str]]:
    rank = _keep_rank(G, protected)
    by_name = defaultdict(list)
    for n in G.nodes:
        if _name(G, n):
            by_name[_name(G, n)].append(n)
    groups = []
    for nodes in by_name.values():
        if len(nodes) < 2:
            continue
        standard = [n for n in nodes if not _is_adhoc(G, n)]
        adhoc = [n for n in nodes if _is_adhoc(G, n)]
        buckets = defaultdict(list)
        for n in standard or adhoc:
            t = G.nodes[n].get("type")
            buckets["concept" if t in CONCEPT_TYPES else t].append(n)
        if standard:
            main = max(buckets, key=lambda b: max(rank(n) for n in buckets[b]))
            for n in adhoc:
                t = G.nodes[n].get("type")
                key = "concept" if t in CONCEPT_TYPES and "concept" in buckets else t
                buckets[key if key in buckets else main].append(n)
        groups += [sorted(m, key=rank, reverse=True) for m in buckets.values() if len(m) > 1]
    return groups


def _plausibly_same_gene(x: str, y: str) -> bool:
    mx, my = _MIRNA_NUMBER.search(x), _MIRNA_NUMBER.search(y)
    if mx or my:  # miR-223 vs miR-22-3p are different miRNAs
        return bool(mx and my and mx.group(1) == my.group(1))
    short, long = sorted((x, y), key=len)  # "ppar" (family) vs "pparalpha" (member)
    return not (long.startswith(short) and long[len(short):].strip("-_ ").isalpha())


def _gene_alias_pairs(G, protected) -> list[list[str]]:
    rank = _keep_rank(G, protected)
    genes = [n for n, d in G.nodes(data=True) if d.get("type") == "Gene"]
    aliases = {n: {str(a).lower() for a in (G.nodes[n].get("aliases") or ())} for n in genes}
    owners = defaultdict(set)
    for n in genes:
        for a in aliases[n]:
            if len(a) >= 3:
                owners[a].add(n)
    pairs = set()
    for b in genes:
        nb = _name(G, b)
        if len(nb) < 3:
            continue
        for a in owners.get(nb, ()):
            na = _name(G, a)
            if a != b and na != nb and na in aliases[b] and _plausibly_same_gene(na, nb):
                pairs.add(tuple(sorted((a, b), key=str)))
    used, groups = set(), []
    for a, b in sorted(pairs, key=lambda p: (-max(G.degree(p[0]), G.degree(p[1])), p)):
        if a not in used and b not in used:
            used.update((a, b))
            groups.append(sorted((a, b), key=rank, reverse=True))
    return groups


def merge_duplicate_nodes(G: nx.Graph, protected: set[str] | None = None) -> dict[str, int]:
    """Merge same-concept nodes in place; returns counts for logging.
    `protected` nodes are always kept when they take part in a merge."""
    protected = set(protected or ())
    stats = {"name_groups": 0, "gene_alias_pairs": 0, "nodes_removed": 0}
    for key, groups in (("name_groups", _name_groups), ("gene_alias_pairs", _gene_alias_pairs)):
        found = groups(G, protected)
        for keep, *drops in found:
            for n in drops:
                merge_into(G, keep, n)
        stats[key] = len(found)
        stats["nodes_removed"] += sum(len(g) - 1 for g in found)
    return stats
