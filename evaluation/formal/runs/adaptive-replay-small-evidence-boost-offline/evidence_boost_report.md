# Evidence-Margin Adaptive Replay

## Configuration

- Questions: Q001, Q002, Q007
- Corpus: frozen PubTator artifacts from `formal-v1-gpt-5.6-terra`
- Graph exposure: frozen paths from `adaptive-replay-small-gpt41`
- Answers: not generated
- Completion-token usage: 0
- Reranker: `evidence_margin_blend_v1`
  - require complete evidence on every path hop
  - require `graph_score >= text_score + 0.15`
  - blend 35% of the graph/text score gap instead of applying a fixed multiplier

## Results

| Question | Metric | Adaptive Hybrid | Text RAG | Hybrid - Text |
|---|---|---:|---:|---:|
| Q001 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q001 | Recall@10 | 0.7500 | 0.7500 | 0.0000 |
| Q001 | nDCG@10 | 0.9662 | 0.9536 | +0.0126 |
| Q002 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q002 | Recall@10 | 0.4545 | 0.4545 | 0.0000 |
| Q002 | nDCG@10 | 0.5906 | 0.5906 | 0.0000 |
| Q007 | P@5 | 1.0000 | 1.0000 | 0.0000 |
| Q007 | Recall@10 | 0.4545 | 0.4545 | 0.0000 |
| Q007 | nDCG@10 | 0.9014 | 0.8442 | +0.0572 |

Macro means:

| Metric | Adaptive Hybrid | Text RAG | Hybrid - Text |
|---|---:|---:|---:|
| P@5 | 1.0000 | 1.0000 | 0.0000 |
| Recall@10 | 0.5530 | 0.5530 | 0.0000 |
| nDCG@10 | 0.8194 | 0.7961 | +0.0233 |
| bpref | 0.6023 | 0.6023 | 0.0000 |

Compared with the prior unconditional graph boost, Hybrid macro nDCG@10 increased from 0.7912
to 0.8194 (+0.0282). The retrieval CSV was regenerated from scratch a second time and retained
the exact same SHA-256 hash, confirming deterministic replay for these frozen inputs.

## Interpretation and limitation

The result is a positive engineering signal: conservative evidence-margin blending corrected the
ranking regression seen with the unconditional 1.5x boost, while the text-only route remained
unchanged. It is not independent proof of Hybrid superiority. These three questions informed the
reranker design and therefore form a development set, not a holdout test; the sample is also too
small for meaningful inference. The parameters must now be frozen and evaluated on untouched
questions before making an overall-superiority claim.
