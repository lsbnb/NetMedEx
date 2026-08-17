# Relevance Grading Guidelines

## Labels

- `2` - Directly relevant. The article directly addresses the question's entity relationship,
  mechanism, intervention, disease context, population, or requested study type.
- `1` - Partially relevant. The article supplies useful adjacent evidence, review-level context,
  a different but informative model, or one supported segment of a multi-hop mechanism.
- `0` - Not relevant. The article is off-topic, uses the wrong entity or disease context, is too
  broad to support the requested answer, or only shares keywords.

Judge relevance to the question, not article quality. A weak study can be directly relevant, while
a high-quality study can still be irrelevant to the specific question.

## Negative controls

For questions asking whether direct evidence exists:

- Assign `2` only when the requested direct causal or mechanistic link is actually tested.
- Assign `1` to adjacent evidence, such as a different tissue, genotype, species, direction of
  effect, or one incomplete segment of the proposed pathway.
- Assign `0` when the paper cannot support even the adjacent proposition.

Do not upgrade a paper because the proposed relationship is biologically plausible.

## Gene/entity-specificity requirement for mechanism and two_hop_path questions

For `two_hop_path` questions and `mechanism` questions whose `expected_concepts` name specific
genes/entities forming a chain (e.g. "which genes mediate a path between X and Y"), a candidate
that only discusses the general pathway or signaling family in broad terms -- without naming the
specific gene(s)/entity(ies) that would complete the requested chain -- should be capped at `1`
regardless of how topically prominent or on-subject the general discussion is. Reserve `2` for
candidates that name the actual mediating gene(s).

This rule exists because three independent AI raters (Claude, GPT-5.6-sol, Gemini) fully
disagreed (0/1/2 split) on 13 candidates during formal-v2 triage, and roughly a third of those
disagreements traced to exactly this ambiguity -- e.g. a broad "curcumin and the PI3K/AKT
pathway" review being graded anywhere from 0 to 2 for a question asking which specific gene
mediates a 2-hop path. Applying this cap resolves that class of disagreement without requiring
per-case human adjudication.

## Confidence

- `3` - Clear decision from title and abstract.
- `2` - Reasonable decision with some ambiguity.
- `1` - Full text or specialist adjudication is needed.

## Exclusion reasons

For grade `0`, use one of:

- `off_topic`
- `wrong_entity`
- `wrong_context`
- `wrong_study_type`
- `too_broad`
- `no_usable_evidence`
- `duplicate`
- `other`

## Blinding

Reviewers must not inspect `pool_provenance.csv`, system names, retrieval scores, ranks, previous
formal-v1 grades, or the other reviewer's labels before submitting their independent pass.

Reviewers may consult the PubMed record or full text when the supplied abstract is insufficient,
but should record that action in `reviewer_notes`.
