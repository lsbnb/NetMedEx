# Adaptive Evidence-Boost Holdout Pilot

## Design

The selection was frozen before the run in `evaluation/formal/adaptive_holdout_pilot_v1.json` and
did not use qrels. Q022 (mechanism, one article), Q032 (association, four articles), and Q014
(retrieval, six articles) were the smallest untouched frozen corpora for their respective adaptive
routes. Q001, Q002, and Q007, which informed reranker development, were excluded. No answers or AI
judge calls were made.

## Cost and routing

| Question | Route | Graph | Paths | Boosted PMIDs | Completion tokens |
|---|---|---:|---:|---:|---:|
| Q014 | A_text_only | 0 nodes / 0 edges | 0 | 0 | 0 |
| Q022 | G_evidence_gated_two_hop | 14 nodes / 18 edges | 20 | 1 | 3,483 |
| Q032 | C_one_hop | 33 nodes / 78 edges | 4 | 3 | 18,218 |
| **Total** | | | | | **21,701** |

## Frozen-qrels result

| Metric | Adaptive Hybrid | Text RAG | Hybrid - Text |
|---|---:|---:|---:|
| P@5 | 0.6667 | 0.6667 | 0.0000 |
| Recall@10 | 0.3704 | 0.3704 | 0.0000 |
| nDCG@10 | 0.4256 | 0.4256 | 0.0000 |
| bpref | 0.6667 | 0.6667 | 0.0000 |

The low returned-at-10 value (0.3667) reflects the deliberately small corpora; both systems were
evaluated against exactly the same candidates. Graph boosts were triggered for Q022 and Q032 but
did not change the effectiveness metrics.

## Conclusion

The positive +0.0233 macro nDCG@10 signal on the three-question development replay did not
replicate on this independent low-cost pilot. The holdout result is a tie, not evidence of Hybrid
superiority. It also does not establish equivalence because there are only three questions and the
cost-based selection is not representative.

A second run reused the newly frozen graph exposures, consumed zero completion tokens, and produced
an identical retrieval CSV SHA-256 (`74fa44bb...0062a9c`). Further paid expansion is intentionally
deferred: the next useful evaluation should use a larger preregistered holdout with sufficiently
large corpora and report quality/cost tradeoffs, not continue tuning on these six questions.
