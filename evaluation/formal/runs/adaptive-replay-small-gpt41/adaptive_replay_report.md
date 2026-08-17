# Small Adaptive Frozen Replay Report

Run directory: `evaluation/formal/runs/adaptive-replay-small-gpt41`

## Scope

- Model: `gpt-4.1`
- Systems: NetMedEx adaptive Hybrid RAG and traditional text-only RAG
- Questions: Q001 (mechanism), Q002 (retrieval), Q007 (association)
- Corpus source: the previously saved per-question PubTator corpora from
  `formal-v1-gpt-5.6-terra`; PubMed was not queried during this replay.
- Gold labels: `evaluation/formal_v2/qrels.csv`, read only after generation.
- General-LLM arm and additional AI judging were skipped to control token cost.

## Routing and cost

| Question | Adaptive route | Graph | Exposed paths | Recorded tokens |
|---|---|---:|---:|---:|
| Q002 | A_text_only (0-hop) | 0 nodes / 0 edges | 0 | 8,560 |
| Q007 | C_one_hop | 70 nodes / 158 edges | 20 | 45,836 |
| Q001 | G_evidence_gated_two_hop | 52 nodes / 73 edges | 20 | 34,063 |
| **Total** | | | | **88,459** |

Recorded usage comprises 54,759 input and 33,700 output tokens. One earlier Q007 attempt
completed graph extraction but failed before answer generation because NodeRAG and AbstractRAG
shared a Chroma collection; the runner did not checkpoint usage on that failed path. Consequently,
88,459 is a lower bound on total API usage for this session. The collection collision is fixed by
using a dedicated `_nodes` collection.

## Frozen-qrels retrieval result

| Question | Metric | Adaptive Hybrid | Text RAG | Hybrid - Text |
|---|---|---:|---:|---:|
| Q001 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q001 | Recall@10 | 0.7500 | 0.7500 | 0.0000 |
| Q001 | nDCG@10 | 0.9389 | 0.9536 | -0.0148 |
| Q002 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q002 | Recall@10 | 0.4545 | 0.4545 | 0.0000 |
| Q002 | nDCG@10 | 0.5906 | 0.5906 | 0.0000 |
| Q007 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q007 | Recall@10 | 0.4545 | 0.4545 | 0.0000 |
| Q007 | nDCG@10 | 0.8442 | 0.8442 | 0.0000 |

Three-question macro means:

| Metric | Adaptive Hybrid | Text RAG | Hybrid - Text |
|---|---:|---:|---:|
| P@5 | 1.0000 | 1.0000 | 0.0000 |
| Recall@10 | 0.5530 | 0.5530 | 0.0000 |
| nDCG@10 | 0.7912 | 0.7961 | -0.0049 |
| bpref | 0.6023 | 0.6023 | 0.0000 |

## Interpretation

The routing implementation behaved as intended: the retrieval question skipped graph construction,
the association question used one hop, and the mechanism question required evidence on every
exposed two-hop path. This replay does **not** show an overall retrieval advantage for Hybrid RAG.
P@5 and Recall@10 were tied, while Hybrid nDCG@10 was slightly lower because Q001 was reordered
less favorably. With only three deliberately selected questions, no inferential superiority claim is
appropriate.

"Frozen" here means corpus-frozen and post-run artifact-frozen. Semantic graph extraction still uses
a generative model and is not deterministic unless the extracted graph itself is cached and replayed.
The failed and successful Q007 attempts produced slightly different graph sizes, which confirms that
future controlled comparisons should freeze graph artifacts as well as corpora.

## Next decision

Before expanding evaluation, improve the graph boost so that graph-preferred PMIDs are promoted only
when the query-matched path evidence is stronger than the text ranker's evidence. Then rerun a small
paired set with both corpus and graph artifacts frozen. Expand to the full benchmark only if the gate
shows a positive retrieval or blinded-answer signal without unacceptable token and latency cost.
