from __future__ import annotations

from netmedex.claim_verifier import relation_supported_by_text
from netmedex.relation_types import is_directional_relation, normalize_relation_type
from netmedex.semantic_re import SemanticRelationshipExtractor


def test_cargo_relation_is_a_canonical_directional_type():
    for raw in ("carries", "contains", "delivers", "transfers", "shuttles", "Carry"):
        assert normalize_relation_type(raw) == "carries"
    assert is_directional_relation("carries")
    assert "carries" in SemanticRelationshipExtractor._allowed_relation_types()


def test_cargo_quotes_support_the_carries_relation():
    assert relation_supported_by_text(
        "MSC-derived exosomes delivered miR-17 to Kupffer cells", "carries")
    assert relation_supported_by_text("exosomal miR-21 promoted sorafenib resistance", "carries")
    assert not relation_supported_by_text("sorafenib inhibited tumor growth", "carries")
