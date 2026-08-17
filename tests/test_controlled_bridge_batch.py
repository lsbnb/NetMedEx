from types import SimpleNamespace

import pytest

from evaluation.build_controlled_bridge_batch import (
    eligible_for_side,
    eligible_endpoint_distractor,
    matching_annotation_identifiers,
)


@pytest.fixture
def patterns():
    return {
        "source_patterns": [r"\bchronic hepatitis b\b", r"\bchronic hbv\b"],
        "target_patterns": [r"\bhepatocellular carcinoma\b", r"\bhcc\b"],
        "mediator_patterns": [r"\bstat1\b"],
    }


def article(text):
    return SimpleNamespace(title=text, abstract="", annotations=[])


def test_source_side_requires_source_and_mediator_without_target(patterns):
    accepted, reasons = eligible_for_side(
        article("STAT1 signaling in chronic hepatitis B"), side="source", **patterns
    )
    assert accepted
    assert reasons == []


def test_source_side_rejects_target_leak(patterns):
    accepted, reasons = eligible_for_side(
        article("STAT1 in chronic HBV and HCC"), side="source", **patterns
    )
    assert not accepted
    assert reasons == ["target_leak"]


def test_target_side_requires_target_and_mediator_without_source(patterns):
    accepted, reasons = eligible_for_side(
        article("STAT1 predicts hepatocellular carcinoma"), side="target", **patterns
    )
    assert accepted
    assert reasons == []


def test_target_side_rejects_source_leak(patterns):
    accepted, reasons = eligible_for_side(
        article("STAT1 links chronic hepatitis B to HCC"), side="target", **patterns
    )
    assert not accepted
    assert reasons == ["source_leak"]


def test_ontology_endpoint_is_rejected_even_when_text_uses_an_unlisted_synonym(patterns):
    item = article("STAT1 signaling in chronic hepatitis B and liver cancer")
    item.annotations = [SimpleNamespace(mesh="MESH:D006528")]
    accepted, reasons = eligible_for_side(
        item,
        side="source",
        target_identifiers=["MESH:D006528"],
        **patterns,
    )
    assert not accepted
    assert reasons == ["target_leak"]


def test_mediator_identifier_is_required_when_preregistered(patterns):
    item = article("STAT1 signaling in chronic hepatitis B")
    item.annotations = [SimpleNamespace(mesh="20846")]
    accepted, reasons = eligible_for_side(
        item,
        side="source",
        mediator_identifiers=["6772"],
        **patterns,
    )
    assert not accepted
    assert reasons == ["mediator_absent"]


def test_target_side_can_apply_broader_source_leak_vocabulary(patterns):
    item = article("STAT1 predicts HCC in patients with HBV infection")
    item.annotations = [SimpleNamespace(mesh="6772")]
    accepted, reasons = eligible_for_side(
        item,
        side="target",
        mediator_identifiers=["6772"],
        target_side_forbidden_source_patterns=[r"\bhbv\b", r"\bhepatitis b\b"],
        **patterns,
    )
    assert not accepted
    assert reasons == ["source_leak"]


def test_source_side_can_apply_broader_target_leak_vocabulary(patterns):
    item = article("STAT1 in chronic hepatitis B with persistent tumor progression")
    accepted, reasons = eligible_for_side(
        item,
        side="source",
        source_side_forbidden_target_patterns=[r"\btumor progression\b"],
        **patterns,
    )
    assert not accepted
    assert reasons == ["target_leak"]


def test_matching_annotation_identifiers_excludes_unnormalized_mentions():
    item = article("STAT1 and STAT3")
    item.annotations = [
        SimpleNamespace(name="STAT1", mesh="6772"),
        SimpleNamespace(name="STAT1", mesh="-"),
        SimpleNamespace(name="STAT3", mesh="6774"),
    ]
    assert matching_annotation_identifiers(item, [r"\bstat1\b"]) == {"6772"}


def test_endpoint_distractor_requires_one_endpoint_and_excludes_mediator(patterns):
    accepted, reasons = eligible_endpoint_distractor(
        article("Chronic hepatitis B natural history"),
        side="source",
        source_patterns=patterns["source_patterns"],
        target_patterns=patterns["target_patterns"],
        mediator_patterns=patterns["mediator_patterns"],
    )
    assert accepted
    assert reasons == []

    accepted, reasons = eligible_endpoint_distractor(
        article("STAT1 signaling in chronic hepatitis B"),
        side="source",
        source_patterns=patterns["source_patterns"],
        target_patterns=patterns["target_patterns"],
        mediator_patterns=patterns["mediator_patterns"],
    )
    assert not accepted
    assert reasons == ["mediator_leak"]
