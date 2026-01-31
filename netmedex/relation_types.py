from __future__ import annotations

"""
Relationship Type Classification for Semantic Edges

This module provides utilities to classify biomedical relationship types
as either directional (e.g., "inhibits") or symmetric (e.g., "interacts with").
"""

# Directional biological relationships (A → B implies direction)
DIRECTIONAL_RELATIONS = {
    # Regulatory relationships
    "inhibits",
    "activates",
    "increases",
    "decreases",
    "upregulates",
    "downregulates",
    "regulates",
    "induces",
    "suppresses",
    "represses",
    "enhances",
    "promotes",
    "stimulates",
    "blocks",
    # Modification relationships
    "phosphorylates",
    "methylates",
    "acetylates",
    "ubiquitinates",
    "modifies",
    # Causal relationships
    "causes",
    "leads_to",
    "results_in",
    "triggers",
    # Therapeutic relationships
    "treats",
    "prevents",
    "cures",
    "ameliorates",
    # Metabolic relationships
    "metabolizes",
    "synthesizes",
    "degrades",
    "catalyzes",
    # Expression relationships
    "expresses",
    "transcribes",
    "translates",
}

# Symmetric relationships (bidirectional or non-directional)
SYMMETRIC_RELATIONS = {
    "interacts_with",
    "associated_with",
    "co_occurs_with",
    "correlates_with",
    "binds_to",
    "complexes_with",
    "related_to",
    "co-mention",  # Default for co-occurrence edges
}

# Map common variations to canonical forms
RELATION_NORMALIZATIONS = {
    "inhibit": "inhibits",
    "inhibition": "inhibits",
    "inhibitor": "inhibits",
    "activate": "activates",
    "activation": "activates",
    "activator": "activates",
    "increase": "increases",
    "increasing": "increases",
    "decrease": "decreases",
    "decreasing": "decreases",
    "regulate": "regulates",
    "regulation": "regulates",
    "regulator": "regulates",
    "upregulate": "upregulates",
    "upregulation": "upregulates",
    "downregulate": "downregulates",
    "downregulation": "downregulates",
    "induce": "induces",
    "induction": "induces",
    "suppress": "suppresses",
    "suppression": "suppresses",
    "enhance": "enhances",
    "enhancement": "enhances",
    "promote": "promotes",
    "promotion": "promotes",
    "phosphorylate": "phosphorylates",
    "phosphorylation": "phosphorylates",
    "treat": "treats",
    "treatment": "treats",
    "cause": "causes",
    "interact": "interacts_with",
    "interaction": "interacts_with",
    "associate": "associated_with",
    "association": "associated_with",
    "bind": "binds_to",
    "binding": "binds_to",
}


def normalize_relation_type(relation_type: str) -> str:
    """
    Normalize a relation type to its canonical form.

    Args:
        relation_type: Raw relation type string from LLM

    Returns:
        Normalized relation type string

    Examples:
        >>> normalize_relation_type("inhibition")
        'inhibits'
        >>> normalize_relation_type("INHIBITS")
        'inhibits'
        >>> normalize_relation_type("interacts with")
        'interacts_with'
    """
    # Convert to lowercase and replace spaces with underscores
    normalized = relation_type.lower().strip().replace(" ", "_")

    # Apply normalization map if exists
    if normalized in RELATION_NORMALIZATIONS:
        return RELATION_NORMALIZATIONS[normalized]

    return normalized


def is_directional_relation(relation_type: str) -> bool:
    """
    Check if a relation type is directional (A → B).

    Args:
        relation_type: Relation type string (will be normalized)

    Returns:
        True if the relation is directional, False otherwise

    Examples:
        >>> is_directional_relation("inhibits")
        True
        >>> is_directional_relation("interacts_with")
        False
        >>> is_directional_relation("activates")
        True
    """
    normalized = normalize_relation_type(relation_type)
    return normalized in DIRECTIONAL_RELATIONS


def is_symmetric_relation(relation_type: str) -> bool:
    """
    Check if a relation type is symmetric (bidirectional).

    Args:
        relation_type: Relation type string (will be normalized)

    Returns:
        True if the relation is symmetric, False otherwise
    """
    normalized = normalize_relation_type(relation_type)
    return normalized in SYMMETRIC_RELATIONS


def get_relation_display_name(relation_type: str) -> str:
    """
    Get a human-readable display name for a relation type.

    Args:
        relation_type: Relation type string

    Returns:
        Display-friendly version of the relation type

    Examples:
        >>> get_relation_display_name("interacts_with")
        'interacts with'
        >>> get_relation_display_name("inhibits")
        'inhibits'
    """
    normalized = normalize_relation_type(relation_type)
    # Replace underscores with spaces for display
    return normalized.replace("_", " ")


def classify_relation(relation_type: str) -> dict[str, bool | str]:
    """
    Classify a relation type with full metadata.

    Args:
        relation_type: Relation type string

    Returns:
        Dictionary with classification metadata

    Example:
        >>> classify_relation("inhibits")
        {
            'normalized': 'inhibits',
            'display_name': 'inhibits',
            'is_directional': True,
            'is_symmetric': False
        }
    """
    normalized = normalize_relation_type(relation_type)

    return {
        "normalized": normalized,
        "display_name": get_relation_display_name(normalized),
        "is_directional": is_directional_relation(normalized),
        "is_symmetric": is_symmetric_relation(normalized),
    }
