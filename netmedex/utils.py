from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from uuid import uuid4


def generate_uuid():
    return str(uuid4())


def generate_stable_id(input_str: str):
    import hashlib

    # Used only to derive a stable non-cryptographic ID for graph nodes/edges, not for any
    # security purpose -- usedforsecurity=False silences the (correct) bandit false positive.
    return hashlib.sha1(input_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def config_logger(is_debug: bool, filename: str | None = None):
    handlers = [logging.StreamHandler(stream=sys.stdout)]

    if filename is not None:
        now = datetime.now().strftime("%y%m%d%H%M%S")
        logfile = f"{filename}_{now}.log"
        handlers.append(logging.FileHandler(logfile, mode="w", encoding="utf-8"))

    if is_debug:
        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.DEBUG,
            handlers=handlers,
        )
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO, handlers=handlers)


def is_notebook():
    try:
        shell = get_ipython().__class__.__name__  # type: ignore
        return shell == "ZMQInteractiveShell"
    except NameError:
        return False


def detect_query_language(text: str) -> str:
    """
    Detect the primary language of a query string using Unicode character ranges.
    Returns a human-readable language name suitable for use in LLM prompts.
    """
    if not text:
        return "English"
    # Japanese: Hiragana (U+3040-U+309F) or Katakana (U+30A0-U+30FF)
    if any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" for c in text):
        return "Japanese"
    # Korean: Hangul (U+AC00-U+D7AF)
    if any("\uac00" <= c <= "\ud7af" for c in text):
        return "Korean"
    # CJK Unified Ideographs — Chinese
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "Traditional Chinese"
    return "English"


def calculate_citation_weight(
    citation_count: int | None, pub_date: str | None, current_year: int | None = None
) -> float:
    """Calculate time-normalized citation weights for articles.

    Formula: weight = log10( (citations / age) + 1.1 ) + 1.0
    Age = CurrentYear - PubYear + 1
    This gives a boost to highly cited and recent papers.
    """
    import math
    import re

    if current_year is None:
        current_year = datetime.now().year

    citations = citation_count if citation_count is not None else 0
    pub_year = current_year
    if pub_date:
        match = re.search(r"(\d{4})", str(pub_date))
        if match:
            pub_year = int(match.group(1))

    age = max(1, current_year - pub_year + 1)
    normalized_score = citations / age
    # Log scaling to keep weights in a reasonable range (mostly 1.0 to 3.0)
    weight = math.log10(normalized_score + 1.1) + 1.0
    return round(weight, 3)


def get_network_profile_params() -> dict[str, Any]:
    """
    Resolve network profile parameters dynamically.
    Environment Variable: NETMEDEX_NETWORK_PROFILE
    Profiles:
      - 'standard' (default): Multiplier 1.0x (normal network speed, fast & responsive)
      - 'slow': Multiplier 2.0x (unstable network / local LLM, increased retries)
      - 'extreme': Multiplier 3.0x (high latency / severe packet loss, maximum retries)
    Or explicit override via NETMEDEX_TIMEOUT_MULTIPLIER.
    """
    import os

    profile = os.getenv("NETMEDEX_NETWORK_PROFILE", "standard").strip().lower()
    profile_multipliers = {
        "standard": 1.0,
        "fast": 1.0,
        "slow": 2.0,
        "extreme": 3.0,
    }
    multiplier = profile_multipliers.get(profile, 1.0)

    # Custom multiplier override if specified
    custom_multiplier = os.getenv("NETMEDEX_TIMEOUT_MULTIPLIER")
    if custom_multiplier:
        try:
            multiplier = max(0.5, float(custom_multiplier))
        except ValueError:
            pass

    max_retries = 4 if multiplier <= 1.0 else (6 if multiplier <= 2.0 else 8)

    return {
        "profile": profile,
        "multiplier": multiplier,
        "max_retries": max_retries,
        "pubtator_total_timeout": 180.0 * multiplier,
        "pubtator_connect_timeout": 30.0 * multiplier,
        "pubtator_read_timeout": 120.0 * multiplier,
        "llm_timeout": 180.0 * multiplier,
        "article_timeout": int(600 * multiplier),
        "citation_timeout": 30.0 * multiplier,
    }


MIRNA_QUERY_TRIGGERS = {"mirna", "microrna", "mirnas", "micrornas", "微小rna", "微rna", "小分子rna"}
SNP_QUERY_TRIGGERS = {
    "snp",
    "snps",
    "snv",
    "snvs",
    "polymorphism",
    "polymorphisms",
    "single nucleotide polymorphism",
    "單核苷酸多態性",
    "變異位點",
    "基因突變",
    "突變位點",
}


def is_snp_node(name: str | None, aliases=None, node_type: str | None = None) -> bool:
    """Check if a node represents a Single Nucleotide Polymorphism (SNP) or genomic mutation."""
    if node_type in ("SNP", "DNAMutation", "ProteinMutation"):
        return True
    all_strings = [str(name or "")]
    if aliases:
        if isinstance(aliases, (set, list)):
            all_strings.extend(str(a) for a in aliases if a)
        elif isinstance(aliases, str):
            all_strings.append(aliases)

    for s in all_strings:
        norm = s.strip().lower()
        if not norm:
            continue
        if norm.startswith("rs") and len(norm) > 2 and norm[2:].isdigit():
            return True
    return False



def is_mirna_node(name: str | None, aliases=None, node_type: str | None = None) -> bool:
    """Check if a node name, alias set, or type represents a microRNA (miRNA) entity."""
    if node_type in ("miRNA", "microRNA", "RNA"):
        return True
    all_strings = [str(name or "")]
    if aliases:
        if isinstance(aliases, (set, list)):
            all_strings.extend(str(a) for a in aliases if a)
        elif isinstance(aliases, str):
            all_strings.append(aliases)

    import re

    for s in all_strings:
        norm = s.strip().lower()
        if not norm:
            continue
        clean = re.sub(r"^(?:hsa|mmu|rno|ptr|ggo|pon|mcc)-", "", norm)
        if clean.startswith(("mir", "microrna", "let-", "mirna")):
            return True
        if re.search(r"\b(?:mir|microrna|let)-\d", norm):
            return True
        if re.search(r"\bmir\d", clean):
            return True
    return False


LNCRNA_QUERY_TRIGGERS = {
    "lncrna",
    "lncrnas",
    "long non-coding rna",
    "long noncoding rna",
    "long non coding rna",
    "非編碼rna",
    "長鏈非編碼rna",
    "長非編碼rna",
}

# lncRNA names have no single reliable naming convention the way miRNA does
# (MALAT1, GAS5, H19, PVT1 look identical to ordinary protein-coding gene
# symbols), so this list of well-known named lncRNAs supplements the handful
# of somewhat reliable naming patterns below (LINC*/SNHG* prefixes, -AS<n>
# antisense suffix). Necessarily incomplete -- an obscure lncRNA matching
# neither the list nor a pattern will not be recognized.
_KNOWN_LNCRNA_NAMES = {
    "malat1",
    "neat1",
    "hotair",
    "xist",
    "h19",
    "meg3",
    "gas5",
    "tug1",
    "pvt1",
    "miat",
    "uca1",
    "kcnq1ot1",
    "dancr",
    "ccat1",
    "ccat2",
    "anril",
    "cdkn2b-as1",
    "hottip",
    "dleu2",
    "ftx",
    "norad",
    "linc-ror",
    "airn",
    "tsix",
}


def is_lncrna_node(name: str | None, aliases=None, node_type: str | None = None) -> bool:
    """Check if a node name, alias set, or type represents a long non-coding RNA (lncRNA).

    PubTator3 tags lncRNAs with the same generic "Gene" type as protein-coding
    genes, so this relies mainly on name matching: a curated list of well-known
    lncRNAs (see _KNOWN_LNCRNA_NAMES) plus the LINC*/SNHG* prefixes and the
    -AS<n> antisense-RNA suffix, which are reasonably specific to this RNA
    family. Necessarily incomplete for names outside these patterns.
    """
    if node_type in ("lncRNA", "ncRNA"):
        return True
    all_strings = [str(name or "")]
    if aliases:
        if isinstance(aliases, (set, list)):
            all_strings.extend(str(a) for a in aliases if a)
        elif isinstance(aliases, str):
            all_strings.append(aliases)

    import re

    for s in all_strings:
        norm = s.strip().lower()
        if not norm:
            continue
        if norm in _KNOWN_LNCRNA_NAMES:
            return True
        if norm.startswith(("linc", "snhg")):
            return True
        if re.search(r"-as\d+$", norm):
            return True
    return False

