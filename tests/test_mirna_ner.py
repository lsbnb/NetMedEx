from netmedex.graph import PubTatorGraphBuilder
from netmedex.mirna_ner import canonicalize_mirna, find_mirna_annotations
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle


def test_canonicalize_mirna_variations():
    assert canonicalize_mirna("MiR-133a-5p") == ("miR-133a-5p", "mir-133a-5p")
    assert canonicalize_mirna("miR 133a-5p") == ("miR-133a-5p", "mir-133a-5p")
    assert canonicalize_mirna("hsa-miR-21-5p") == ("miR-21-5p", "mir-21-5p")
    assert canonicalize_mirna("microRNA-155") == ("miR-155", "mir-155")
    assert canonicalize_mirna("miRNA-223-3p") == ("miR-223-3p", "mir-223-3p")
    assert canonicalize_mirna("let-7a-5p") == ("let-7a-5p", "let-7a-5p")
    assert canonicalize_mirna("hsa-let-7") == ("let-7", "let-7")
    assert canonicalize_mirna("lin-4") == ("lin-4", "lin-4")


def test_finds_mir133a_5p_in_title_and_abstract():
    title = "MiR-133a-5p Facilitates Cuproptosis in Hepatocellular Carcinoma Through Targeting of ATP7B."
    abstract = "We explored the effects of miR-133a-5p and ATP7B on cuproptosis."
    annotations = find_mirna_annotations("40433054", title, abstract)
    names = [a.name for a in annotations]
    assert "MiR-133a-5p" in names
    assert "miR-133a-5p" in names
    assert all(a.type == "Gene" for a in annotations)
    assert all(a.mesh == "mir-133a-5p" for a in annotations)


def test_finds_circrna_and_lncrna():
    text = "circHIPK3 sponges miR-124 to regulate cancer cell growth, while lncRNA-ATB promotes invasion."
    annotations = find_mirna_annotations("1", text, None)
    names = {a.name: a.mesh for a in annotations}
    assert "circHIPK3" in names
    assert names["circHIPK3"] == "circ:circhipk3"
    assert "lncRNA-ATB" in names
    assert names["lncRNA-ATB"] == "lnc:lncrna-atb"
    assert "miR-124" in names
    assert names["miR-124"] == "mir-124"


def test_supersedes_bogus_5p_chromosome_annotation():
    # PubTator only tagged "5p" (offset 880-882) as Chromosome in abstract
    title = "MiR-133a-5p in HCC."
    abstract = "Targeting by miR-133a-5p was observed."
    existing = [
        PubTatorAnnotation(
            pmid="1", start=len(title) + 1 + 13, end=len(title) + 1 + 15,
            name="5p", identifier_name=None, type="Chromosome", mesh="5"
        )
    ]
    annotations = find_mirna_annotations("1", title, abstract, existing_annotations=existing)
    # The complete miR-133a-5p must be extracted despite bogus "5p" Chromosome annotation
    assert any(a.identifier_name == "miR-133a-5p" and a.name == "miR-133a-5p" for a in annotations)


def test_mirna_graph_builder_integration():
    article = PubTatorArticle(
        pmid="40433054",
        date=None,
        journal=None,
        doi=None,
        title="MiR-133a-5p Facilitates Cuproptosis in Hepatocellular Carcinoma Through Targeting of ATP7B.",
        abstract="We explored the effects of miR-133a-5p and ATP7B.",
        annotations=[
            PubTatorAnnotation(
                pmid="40433054", start=71, end=76, name="ATP7B", identifier_name="ATP7B",
                type="Gene", mesh="540"
            )
        ],
        relations=[],
    )
    builder = PubTatorGraphBuilder(node_type="all")
    builder.add_article(article)
    G = builder.build()

    assert "mir-133a-5p_Gene" in G
    assert "540_Gene" in G
    assert G.has_edge("mir-133a-5p_Gene", "540_Gene")


def test_circrna_pattern_does_not_match_ordinary_words():
    """Regression: an optional separator after "circ" made the pattern match
    "circulating", "circular" and "circulation" -- on a 36k-article corpus those
    were among the most frequent "circRNAs" found."""
    text = ("Circulating exosomes showed a circular profile; circulation and "
            "circumference were unchanged, and circuits were intact.")
    found = find_mirna_annotations("1", text, "", [])
    assert [a.name for a in found] == []


def test_circrna_pattern_still_matches_real_identifiers():
    text = "circHIPK3, circ_0001234, hsa_circ_0000190, circRNA-ABC1 and circZNF609 were measured."
    names = {a.identifier_name for a in find_mirna_annotations("1", text, "", [])}
    assert names == {"circHIPK3", "circ_0001234", "circ_0000190", "circRNA-ABC1", "circZNF609"}


def test_bare_class_mentions_are_not_entities():
    found = find_mirna_annotations("1", "circRNAs and circRNA biogenesis in cancer", "", [])
    assert [a.name for a in found] == []


def test_class_level_phrases_are_not_transcripts():
    """Regression: "circRNA-" / "lncRNA-" followed by any word matched, so
    network and method phrases became entities -- "circRNA-miRNA-mRNA" alone
    carried 82 relations on a 36k-article corpus."""
    text = ("A circRNA-miRNA-mRNA network and a lncRNA-miRNA axis were built; "
            "circRNA-based and lncRNA-mediated regulation, circRNA-protein binding "
            "and lncRNA-autophagy links were discussed.")
    assert find_mirna_annotations("1", text, "", []) == []


def test_real_noncoding_transcripts_still_match():
    text = "lncRNA-HOTAIR, lnc-MALAT1, lncRNA-ATB, circRNA-ABC1 and circ_0001234 were measured."
    names = {a.identifier_name for a in find_mirna_annotations("1", text, "", [])}
    assert {"circRNA-ABC1", "circ_0001234"} <= names
    assert len(names) == 5
