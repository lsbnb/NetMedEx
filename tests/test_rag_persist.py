from __future__ import annotations

from netmedex.rag import AbstractDocument, AbstractRAG


def _docs(n):
    return [AbstractDocument(pmid=str(i), title=f"title {i}", abstract=f"liver exosome study {i}",
                             entities=[], edges=[]) for i in range(n)]


def test_persisted_index_is_reloaded_not_rebuilt(tmp_path):
    first = AbstractRAG(None, persist_directory=str(tmp_path))
    assert first.index_abstracts(_docs(6), reuse_persisted=True) == 6

    again = AbstractRAG(None, persist_directory=str(tmp_path))

    assert again.index_abstracts(_docs(6), reuse_persisted=True) == 6
    assert again.collection_name == first.collection_name
    assert again.search("exosome", top_k=3)                 # dense + BM25 work after reload

    other = AbstractRAG(None, persist_directory=str(tmp_path))
    other.index_abstracts(_docs(3), reuse_persisted=True)  # different PMIDs: own collection
    assert other.collection_name != first.collection_name


def test_without_reuse_flag_behaviour_is_unchanged(tmp_path):
    rag = AbstractRAG(None, persist_directory=str(tmp_path))
    rag.index_abstracts(_docs(4))
    assert rag.collection_name == "abstracts"
