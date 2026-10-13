"""Rule- and dictionary-based NER for microRNAs and non-coding RNAs (miRNAs, circRNAs, lncRNAs).

PubTator3's GNormPlus primarily indexes protein-coding genes from NCBI Gene. It frequently
omits microRNAs -- particularly mature strands (-5p/-3p, e.g. "miR-133a-5p"), newly reported
miRNAs, circular RNAs ("circHIPK3", "circ_0001234"), and ad-hoc lncRNA mentions ("lncRNA-ATB").
Worse, PubTator3's NER sometimes mistakenly tags the "-5p" suffix alone as a Chromosome
(Chromosome 5) while completely dropping the miRNA identity.

This module closes that gap:
1. Deterministically detects microRNAs (miR-xxx, miR-xxx-5p/3p, let-7, lin-4) following
   standard miRBase nomenclature, with or without species prefixes (hsa-, mmu-, rno-).
2. Detects circular RNAs (circ_*, circ-*, circRNA-*) and lncRNAs.
3. Normalizes them to canonical display names (e.g. "miR-133a-5p", "circHIPK3") and
   consistent ontology IDs (e.g. "mir-133a-5p", "circ:circhipk3").
4. Assigns entity type "Gene", mirroring PubTator's own classification for genetic elements,
   ensuring full interoperability with Cytoscape styling, graph metrics, semantic LLM prompts,
   and RAG retrieval.
5. Resolves overlaps with PubTator: supersedes sub-span noise (such as bogus "5p" Chromosome
   annotations), while preserving existing PubTator Gene annotations if an identical exact span
   was already mapped to an NCBI Gene ID.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from netmedex.pubtator_data import PubTatorAnnotation

# Pattern matching microRNA mentions:
# - Optional species prefix (hsa-, mmu-, rno-, etc.)
# - Core prefix: miR-, mir-, MiR-, miRNA-, microRNA-
# - Number / letter: 133a, 133a-1, 21, 223, 22, 146a
# - Optional cluster range: 17-92, 17~92
# - Optional arm / strand: -5p, -3p, *, -star
# - Standalone let-7 / lin-4 family (let-7, let-7a-5p, lin-4)
_MIRNA_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:"
        r"(?:(?:hsa|mmu|rno|dme|cel|has)[-_])?"
        r"(?:"
            r"(?:microRNA|miRNA|miR|mir)[-\s_]?"
            r"(?:"
                r"(?:let|lin)[-_]?[47][a-z0-9]?(?:[-_]\d+)?"
                r"|"
                r"\d+[a-z0-9]?(?:[-_]\d+)?"
                r"(?:[~-]\d+[a-z]?)?"
            r")"
            r"(?:[-_][35]p|\*|-star)?"
        r"|"
            r"(?:let|lin)[-_][47][a-z0-9]?(?:[-_]\d+)?"
            r"(?:[-_][35]p|\*|-star)?"
        r")"
    r")"
    r"(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)

# Pattern matching circular RNAs (circRNAs):
# An optional separator after "circ" made this match ordinary words --
# "circulating", "circular", "circulation" all parse as circ + suffix. A real
# mention either separates the identifier ("circ_0001234", "circRNA-ABC1") or
# runs a gene symbol straight on ("circHIPK3"), which always starts with an
# upper-case letter or a digit. The prefix stays case-insensitive so a mention
# at the start of a sentence still matches; the identifier does not.
_CIRCRNA_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:(?i:hsa|mmu|rno|has)[-_])?"
    r"(?i:circ(?:rna)?)"
    r"(?:[-_][A-Za-z0-9][A-Za-z0-9_-]*"
    r"|[A-Z0-9][A-Za-z0-9_-]*)"
    r"(?![A-Za-z0-9_-])",
)

# "circRNA"/"circRNAs" name the class, not one transcript.
_CIRCRNA_GENERIC = {"circ", "circrna", "circrnas", "circruna", "circrnas-"}

# Pattern matching common lncRNAs with lnc- / lncRNA- prefix:
_LNCRNA_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:(?:hsa|mmu|rno)[-_])?"
    r"(?:lnc|lncRNA)[-_](?:[A-Za-z0-9_-]+)"
    r"(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)


def canonicalize_mirna(mention: str) -> tuple[str, str]:
    """Standardize a surface microRNA mention.

    Returns:
        (canonical_display_name, ontology_id)
        e.g. ('MiR-133a-5p' -> ('miR-133a-5p', 'mir-133a-5p'))
             ('hsa-let-7a-5p' -> ('let-7a-5p', 'let-7a-5p'))
    """
    s = mention.strip()
    # Strip species prefix for canonicalization
    s = re.sub(r"^(?:hsa|mmu|rno|dme|cel|has)[-_]", "", s, flags=re.IGNORECASE)

    # Handle let-7 / lin-4
    m_let = re.match(r"^(?:miR|mir|MiR|MIR|miRNA|microRNA|microrna)?[-\s_]?((?:let|lin)[-_]?[47].*)$", s, flags=re.IGNORECASE)
    if m_let:
        rest = m_let.group(1).lower()
        rest = re.sub(r"^([a-z]+)[-_]?", r"\1-", rest)
        return rest, rest

    # Handle standard microRNA / miRNA / miR
    m_mir = re.match(
        r"^(?:microRNA|miRNA|miR|mir)[-\s_]?(.*)$",
        s,
        flags=re.IGNORECASE,
    )
    if m_mir:
        rest = m_mir.group(1).lower()
        canonical_name = f"miR-{rest}"
        mesh_id = f"mir-{rest}"
        return canonical_name, mesh_id

    # Fallback
    canonical_name = s
    mesh_id = s.lower()
    return canonical_name, mesh_id


def canonicalize_circrna(mention: str) -> tuple[str, str]:
    """Standardize a circular RNA mention.

    Returns:
        (canonical_display_name, ontology_id)
        e.g. ('circHIPK3' -> ('circHIPK3', 'circ:circhipk3'))
             ('circ_0001234' -> ('circ_0001234', 'circ:circ_0001234'))
    """
    s = mention.strip()
    s_clean = re.sub(r"^(?:hsa|mmu|rno|has)[-_]", "", s, flags=re.IGNORECASE)
    mesh_id = f"circ:{s_clean.lower()}"
    return s_clean, mesh_id


def is_generic_circrna(mention: str) -> bool:
    """True for a mention that names circular RNAs as a class, not one transcript."""
    s = re.sub(r"^(?:hsa|mmu|rno|has)[-_]", "", mention.strip(), flags=re.IGNORECASE)
    return s.lower() in _CIRCRNA_GENERIC


def canonicalize_lncrna(mention: str) -> tuple[str, str]:
    """Standardize a lncRNA mention.

    Returns:
        (canonical_display_name, ontology_id)
        e.g. ('lncRNA-ATB' -> ('lncRNA-ATB', 'lnc:lncrna-atb'))
    """
    s = mention.strip()
    s_clean = re.sub(r"^(?:hsa|mmu|rno)[-_]", "", s, flags=re.IGNORECASE)
    mesh_id = f"lnc:{s_clean.lower()}"
    return s_clean, mesh_id


def find_mirna_annotations(
    pmid: str,
    title: str,
    abstract: str | None,
    existing_annotations: Sequence[PubTatorAnnotation] | None = None,
) -> list[PubTatorAnnotation]:
    """Scan title + abstract for microRNA, circRNA, and lncRNA mentions.

    Returns synthetic PubTatorAnnotation objects (type "Gene") that can be fed
    straight into PubTatorNodeCollection.add_node() alongside the article's real
    PubTator annotations.

    Overlaps with existing annotations:
    - If PubTator already tagged the exact span as "Gene" (e.g. mapped to an NCBI Gene ID),
      the match is skipped to avoid creating duplicate nodes.
    - If PubTator only tagged a sub-span (e.g. only "5p" as Chromosome) or tagged a non-Gene,
      our complete RNA annotation is emitted.
    """
    text = f"{title} {abstract or ''}"
    if not text.strip():
        return []

    # Map existing exact Gene spans to skip duplicates
    existing_gene_spans = set()
    if existing_annotations:
        for a in existing_annotations:
            if a.type == "Gene" and str(a.mesh or "-") not in ("-", ""):
                existing_gene_spans.add((a.start, a.end))

    annotations: list[PubTatorAnnotation] = []
    matched_spans: list[tuple[int, int]] = []

    # 1. Match microRNAs
    for m in _MIRNA_RE.finditer(text):
        start, end = m.start(), m.end()
        raw_text = m.group(0)

        # Skip if exact span is already an NCBI Gene annotation
        if (start, end) in existing_gene_spans:
            continue

        # Prevent overlapping matches within this module
        if any(start < e and s < end for s, e in matched_spans):
            continue

        canonical_name, mesh_id = canonicalize_mirna(raw_text)
        annotations.append(
            PubTatorAnnotation(
                pmid=pmid,
                start=start,
                end=end,
                name=raw_text,
                identifier_name=canonical_name,
                type="Gene",
                mesh=mesh_id,
            )
        )
        matched_spans.append((start, end))

    # 2. Match circular RNAs (circRNAs)
    for m in _CIRCRNA_RE.finditer(text):
        start, end = m.start(), m.end()
        raw_text = m.group(0)

        if (start, end) in existing_gene_spans:
            continue
        if any(start < e and s < end for s, e in matched_spans):
            continue
        if is_generic_circrna(raw_text):
            continue

        canonical_name, mesh_id = canonicalize_circrna(raw_text)
        annotations.append(
            PubTatorAnnotation(
                pmid=pmid,
                start=start,
                end=end,
                name=raw_text,
                identifier_name=canonical_name,
                type="Gene",
                mesh=mesh_id,
            )
        )
        matched_spans.append((start, end))

    # 3. Match explicit lncRNAs
    for m in _LNCRNA_RE.finditer(text):
        start, end = m.start(), m.end()
        raw_text = m.group(0)

        if (start, end) in existing_gene_spans:
            continue
        if any(start < e and s < end for s, e in matched_spans):
            continue

        canonical_name, mesh_id = canonicalize_lncrna(raw_text)
        annotations.append(
            PubTatorAnnotation(
                pmid=pmid,
                start=start,
                end=end,
                name=raw_text,
                identifier_name=canonical_name,
                type="Gene",
                mesh=mesh_id,
            )
        )
        matched_spans.append((start, end))

    annotations.sort(key=lambda a: a.start)
    return annotations
