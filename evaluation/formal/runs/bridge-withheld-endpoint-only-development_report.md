# Endpoint-only bridge-withheld development report

## Outcome

The current development evidence does not establish that Hybrid RAG produces
biomedical claims unavailable to Text-RAG. It does establish that the graph can
produce traceable, directionally correct, multi-document evidence chains.

For the strongest valid path, `CFTR -> dysbiosis -> inflammation`, Claude Sonnet
4.6 and Gemini 3.1 Pro agreed on path traceability, hop evidence, relation
direction, multi-hop status, and research utility. Both also judged that the
Text-RAG answer already contained an equivalent dysbiosis mechanism, so the
claim was not Hybrid-only.

## Experimental corrections

- Removed mediator leakage from PubMed retrieval queries. The prior CFTR query
  explicitly contained `NF-kB OR dysbiosis OR cytokines`.
- Froze 39-document endpoint-only corpora for BW003 and BW008.
- Fixed explicit endpoint role contamination and ontology word-order fallback.
- Added relation/quote consistency to the strict edge gate.
- Required fixed source-relation-bridge-relation-target ordering in generated
  graph claims.
- Restricted hidden-claim worksheets to graph-incremental candidates.
- Added underscore normalization for canonical relation labels.

## Runs and provider-reported tokens

- Expanded CFTR semantic graph: 95,465
- Expanded CFTR paired generation: 11,389
- First CFTR Claude/Gemini panel: 6,237
- Endpoint-only HBV semantic graph: 79,365
- HBV paired diagnostic: 8,298
- Endpoint-only CFTR semantic graph: 91,744
- Endpoint-only CFTR paired generation: 9,951
- Final CFTR Claude/Gemini panel: 8,215
- Total for this development phase: 310,664

PubMed/PubTator retrieval and local deterministic audits are not included because
they reported no chat-completion usage.

## Bottleneck

The bottleneck is now candidate diversity, not answer-model capacity. A strict
scan of all cached frozen artifacts produced only five unique claim-safe two-hop
paths with support outside Text top-10: four CFTR variants and one metformin path
whose bridge was already named in the question. Existing query-local graphs are
too narrow and overlap too strongly with Text-RAG's highest-ranked abstracts.

## Next architecture

Build the graph over a frozen union corpus collected independently from source,
target, and endpoint-pair queries, while giving Text-RAG access to the same union
corpus and the same top-10 context budget. Persist the full semantic graph so
candidate mining and re-gating do not require repeated extraction calls. Before
answer generation, require both:

1. semantic non-equivalence to the frozen Text-RAG answer; and
2. a non-trivial mediator score from an independent AI selector.

Final validation must use different providers from the selector and continue to
report traceable evidence-chain gains separately from genuinely Hybrid-only
biomedical meaning.
