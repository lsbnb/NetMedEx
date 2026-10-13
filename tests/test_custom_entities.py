from __future__ import annotations

from netmedex.custom_entities import annotate_article, load_entity_dict
from netmedex.pubtator_data import PubTatorAnnotation, PubTatorArticle

DICT = """# id	type	name	synonyms
DICT:EV	Chemical	extracellular vesicles	extracellular vesicle|exosome|exosomes|EVs|sEV

DICT:MSC	CellLine	mesenchymal stem cells	mesenchymal stromal cells|MSC|MSCs
"""


def _article(title, abstract, annotations=()):
    return PubTatorArticle(pmid="1", date=None, journal=None, doi=None, title=title,
                           abstract=abstract, annotations=list(annotations), relations=[])


def _entities(tmp_path):
    path = tmp_path / "dict.tsv"
    path.write_text(DICT, encoding="utf-8")
    return load_entity_dict(path)


def test_dictionary_skips_comments_and_blank_lines(tmp_path):
    entities = _entities(tmp_path)
    assert [(e.id, e.type, e.name) for e in entities] == [
        ("DICT:EV", "Chemical", "extracellular vesicles"),
        ("DICT:MSC", "CellLine", "mesenchymal stem cells"),
    ]


def test_lowercase_synonyms_match_any_case_abbreviations_only_exact(tmp_path):
    article = _article("Exosomes from MSCs", "msc and evs are lower case here; EVs are not")
    added = annotate_article(article, _entities(tmp_path))
    found = [(a.name, a.mesh) for a in article.annotations]
    assert ("Exosomes", "DICT:EV") in found and ("MSCs", "DICT:MSC") in found
    assert ("EVs", "DICT:EV") in found
    assert ("msc", "DICT:MSC") not in found and ("evs", "DICT:EV") not in found
    assert added == len(found)


def test_offsets_cover_title_and_abstract(tmp_path):
    article = _article("MSC", "exosome")
    annotate_article(article, _entities(tmp_path))
    text = article.title + " " + article.abstract
    assert [text[a.start:a.end] for a in article.annotations] == ["MSC", "exosome"]


def test_whole_words_only_and_longest_synonym_wins(tmp_path):
    article = _article("MSC-Exos and extracellular vesicles", "")
    annotate_article(article, _entities(tmp_path))
    assert [a.name for a in article.annotations] == ["extracellular vesicles"]


def test_existing_pubtator_annotation_is_kept(tmp_path):
    existing = PubTatorAnnotation(pmid="1", start=0, end=8, name="exosomes",
                                  identifier_name=None, type="Chemical", mesh="MESH:X")
    article = _article("exosomes", "", [existing])
    assert annotate_article(article, _entities(tmp_path)) == 0
    assert article.annotations == [existing]


def test_network_cli_turns_dictionary_concepts_into_graph_nodes(tmp_path):
    import pickle
    from pathlib import Path

    from netmedex.cli import parse_args

    dictionary = tmp_path / "dict.tsv"
    dictionary.write_text("DICT:MT\tBiologicalProcess\tmesenchymal traits\tmesenchymal traits\n")
    source = Path(__file__).parent / "test_data" / "22429397_abstract_240916.pubtator"
    out = tmp_path / "graph.pickle"
    args = parse_args(["network", "-i", str(source), "-o", str(out), "-f", "pickle",
                       "--cut_weight", "0", "--entity_dict", str(dictionary)])
    args.entry_func(args)
    with open(out, "rb") as f:
        G = pickle.load(f)
    assert "DICT:MT_BiologicalProcess" in G
    assert G.degree("DICT:MT_BiologicalProcess") > 0  # co-mentioned with the article's entities
