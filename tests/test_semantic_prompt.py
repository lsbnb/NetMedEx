from __future__ import annotations

from types import SimpleNamespace

from netmedex.semantic_re import SemanticRelationshipExtractor


def _sample_entities():
    return [
        {"id": "MESH:D012559_Disease", "name": "Retinal Diseases", "type": "Disease", "mesh": "D012559"},
        {"id": "MESH:D007333_Chemical", "name": "Lutein", "type": "Chemical", "mesh": "D007333"},
    ]


def test_google_prompt_uses_same_chatgpt_style_structure_as_openai():
    llm_client = SimpleNamespace(provider="google", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    prompt = extractor._build_llm_prompt(
        title="Example title",
        abstract="Example abstract text about retinal diseases and lutein.",
        entity_list=_sample_entities(),
    )

    assert "**Task**" in prompt
    assert "**Instructions**" in prompt
    assert "Return ONLY a JSON array" in prompt
    assert "Do NOT perform NER" in prompt


def test_openai_prompt_keeps_existing_structure():
    llm_client = SimpleNamespace(provider="openai", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    prompt = extractor._build_llm_prompt(
        title="Example title",
        abstract="Example abstract text about retinal diseases and lutein.",
        entity_list=_sample_entities(),
    )

    assert "**Task**" in prompt
    assert "Return ONLY a JSON array" in prompt
    assert "Do NOT perform NER" in prompt


def test_relaxed_parser_recovers_from_malformed_json_like_output():
    llm_client = SimpleNamespace(provider="google", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    malformed = """
[
  {"entity1_id":"MESH:D1_Disease","entity2_id":"MESH:D2_Chemical","relation_type":"associated_with","confidence":0.78,"evidence":"shows association}
]
"""
    rels = extractor._parse_llm_response_relaxed(malformed, "12345")
    assert len(rels) == 1
    assert rels[0]["entity1_id"] == "MESH:D1_Disease"
    assert rels[0]["entity2_id"] == "MESH:D2_Chemical"
    assert rels[0]["relation_type"] == "associated_with"


def test_google_effective_threshold_is_capped_for_gemini():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=None)
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)
    assert extractor._effective_confidence_threshold(0.5) == 0.25


def test_confidence_percent_is_normalized_and_kept_in_semantic_edge():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="12345",
        title="Example",
        abstract="Lutein is associated with retinal disease outcomes.",
    )
    nodes = {
        "MESH:D012559_Disease": SimpleNamespace(
            name="Retinal Diseases",
            type="Disease",
            mesh="D012559",
        ),
        "MESH:D007333_Chemical": SimpleNamespace(
            name="Lutein",
            type="Chemical",
            mesh="D007333",
        ),
    }

    extractor._call_llm = lambda prompt, max_tokens=1500, response_format=None: (
        '[{"entity1_id":"MESH:D012559_Disease","entity2_id":"MESH:D007333_Chemical",'
        '"relation_type":"associated_with","confidence":"78%","evidence":"associated"}]'
    )
    edges = extractor.analyze_article_relationships(article, nodes)

    assert len(edges) == 1
    assert edges[0].confidence == 0.78


def test_google_compact_retry_recovers_when_first_pass_empty():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="99999",
        title="Example",
        abstract="Chemical A inhibits Disease B progression.",
    )
    nodes = {
        "MESH:D_B_Disease": SimpleNamespace(name="Disease B", type="Disease", mesh="D_B"),
        "MESH:C_A_Chemical": SimpleNamespace(name="Chemical A", type="Chemical", mesh="C_A"),
    }

    calls = {"n": 0}

    def fake_call(prompt, max_tokens=1500, response_format=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "[]"
        return (
            '[{"entity1_id":"MESH:C_A_Chemical","entity2_id":"MESH:D_B_Disease",'
            '"relation_type":"inhibits","confidence":0.62}]'
        )

    extractor._call_llm = fake_call
    edges = extractor.analyze_article_relationships(article, nodes)

    assert calls["n"] == 2
    assert len(edges) == 1
    assert edges[0].relation_type == "inhibits"


def test_name_based_entity_fallback_is_not_allowed():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o-mini", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)

    article = SimpleNamespace(
        pmid="77777",
        title="Example",
        abstract="Lutein is associated with retinal disease outcomes.",
    )
    nodes = {
        "MESH:D012559_Disease": SimpleNamespace(
            name="Retinal Diseases",
            type="Disease",
            mesh="D012559",
        ),
        "MESH:D007333_Chemical": SimpleNamespace(
            name="Lutein",
            type="Chemical",
            mesh="D007333",
        ),
    }

    # LLM returns names instead of canonical IDs; this should be rejected.
    extractor._call_llm = lambda prompt, max_tokens=1500, response_format=None: (
        '[{"entity1_id":"Retinal Diseases","entity2_id":"Lutein",'
        '"relation_type":"associated_with","confidence":0.92}]'
    )
    edges = extractor.analyze_article_relationships(article, nodes)
    assert len(edges) == 0


def test_relation_type_is_normalized_to_canonical_form():
    llm_client = SimpleNamespace(provider="openai", model="gpt-4o-mini", client=object())
    extractor = SemanticRelationshipExtractor(llm_client, confidence_threshold=0.5)
    rels = extractor._parse_llm_response(
        '[{"entity1_id":"A","entity2_id":"B","relation_type":"inhibition","confidence":0.8}]',
        "pmid-x",
    )
    assert len(rels) == 1
    assert rels[0]["relation_type"] == "inhibits"


def test_google_coverage_prompt_is_valid():
    llm_client = SimpleNamespace(provider="google", model="gemini-pro-latest", client=None)
    extractor = SemanticRelationshipExtractor(llm_client)
    # This should not raise NameError: name 'pair_count' is not defined
    prompt = extractor._build_coverage_prompt(
        title="Example title",
        abstract="Example abstract text.",
        entity_list=_sample_entities(),
    )

    assert "unordered pairs" in prompt
    assert "one of:" in prompt
    assert "associated_with" in prompt
