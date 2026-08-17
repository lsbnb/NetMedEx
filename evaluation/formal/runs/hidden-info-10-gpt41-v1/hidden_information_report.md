# Ten-Question Hidden-Information Evaluation

## Outcome

The preregistered hypothesis was **not supported** in this pilot. Hybrid RAG produced 22
traceable graph-derived candidate claims across 5 of 10 questions, but none passed every
predeclared validation criterion after per-field 2/3 AI-panel adjudication.

This result does not show that Hybrid RAG can never expose hidden information. It shows that the
current graph extraction, path selection, and answer synthesis pipeline did not produce a
validated advantage on this untouched ten-question set.

## Design

- Ten untouched graph-oriented questions; prior six development/pilot questions excluded.
- Frozen PubMed corpora with 10–15 articles per question.
- GPT-4.1 generated both Hybrid and Traditional answers.
- Hybrid alone received graph paths, with PMID and evidence quote on every exposed hop.
- Claude Haiku and Gemini independently rated anonymous candidates.
- Claude Sonnet adjudicated only disagreements.
- No human-expert validation is claimed.

Five zero-path questions initially exposed a prompt bug that requested graph claims despite having
no graph context. The prompt was fixed, those paired answers were regenerated from their original
rankings without rebuilding graphs, and the invalid pre-repair outputs were retained as audit
backups. The repaired answers contain no fabricated PATH identifiers.

## Primary endpoint

| Endpoint | Preregistered threshold | Result |
|---|---:|---:|
| Validated Hybrid-only claims per question | ≥ 0.5 advantage | 0.0 |
| Questions with ≥1 validated Hybrid-only claim | ≥ 30% | 0% |
| Validated hidden-claim precision | ≥ 70% | 0% |
| Judge reliability target | alpha ≥ 0.60 | Not met for most fields |

Because validated Hybrid-only yield was zero, the positive Hybrid-minus-Text endpoint cannot be
met even without separately estimating Text-only hidden claims.

## Candidate funnel

| Criterion | Consensus-positive candidates | Rate |
|---|---:|---:|
| Hybrid-only | 2 / 22 | 9.1% |
| Path traceable | 10 / 22 | 45.5% |
| Evidence supported | 11 / 22 | 50.0% |
| Relation/direction correct | 13 / 22 | 59.1% |
| Multi-document or multi-hop | 4 / 22 | 18.2% |
| Unsupported novelty | 11 / 22 | 50.0% |
| Fully validated hidden claim | 0 / 22 | 0% |

The two claims considered Hybrid-only did not pass path/evidence validation. Many supported claims
were already present in the Traditional answer or were direct single-document restatements rather
than non-obvious hidden information.

## Judge reliability

Krippendorff alpha was 0.291 for Hybrid-only, 0.322 for path traceability, 0.569 for evidence
support, 0.297 for relation/direction, 0.522 for multi-document/hop, 0.630 for unsupported novelty,
0.487 for non-obviousness, and 0.056 for research utility. The high disagreement—21 of 22 items
required adjudication—means subjective novelty and utility scores should not be treated as stable.
The zero validated result nevertheless also failed on the more concrete evidence/path criteria.

## Retrieval guardrail

Hybrid did not gain conventional retrieval quality: P@5 tied at 0.9400; Hybrid Recall@10 was
0.4956 versus 0.5006 for Text; Hybrid nDCG@10 was 0.6662 versus 0.6716; Hybrid bpref was 0.4279
versus 0.4404.

## Cost

- Paired generation, graph extraction, and zero-path repairs: 535,976 recorded tokens.
- Successful judge checkpoints: 72,597 recorded tokens.
- Combined recorded total: 608,573 tokens.

This is a lower bound because two failed Gemini schema attempts and tiny connectivity checks were
not included in successful checkpoint totals.

## Engineering conclusion

Upgrading GPT-4.1 is not justified by these results. The dominant limitations are upstream and
structural: only half the questions exposed any path, only 45.5% of candidate claims fully traced
to the supplied paths, half contained unsupported novelty, and most supported claims duplicated
Text-RAG content. The next improvement should target entity/query alignment, path-level evidence
completeness, and explicit claim-to-hop entailment before another paid generation study.
