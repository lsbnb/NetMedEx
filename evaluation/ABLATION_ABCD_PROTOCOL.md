# NetMedEx A/B/C/D ablation

All arms use the same frozen question set, first-stage corpus, answer model, top-k, and answer
budget. Arms C and D share a content-addressed semantic-graph cache.

| Arm | System | KG build | KG rerank | KG expansion | Path context |
|---|---|---:|---:|---:|---:|
| A | Closed-book LLM | No | No | No | No |
| B | Traditional text RAG | No | No | No | No |
| C | Text RAG + KG reranking | Yes/cache | Yes | No | No |
| D | KG expansion + reranking + path-grounded answer | Yes/cache | Yes | Yes | Claim-safe only |

Report answer quality, Recall@10, nDCG@10, claim citation correctness, claim-safe path coverage,
retrieval-expansion coverage, latency, input/output tokens, and cost per accepted answer. Do not
raise path coverage by weakening claim-safety gates; Tier-B paths may generate expansion queries
but may not be stated as evidence.

Tier A edge evidence requires an aligned PMID quote and confidence >=0.8. Aligned evidence below
0.8 is Tier B and is retrieval-only. The runner exposes this as
`--claim-confidence-threshold 0.8` for preregistered sensitivity analysis; 0.8 is the default.
Cross-PMID, multi-hop Tier-A paths are ranked before single-PMID paths but are not mandatory.
Overall path coverage, multi-hop coverage, and cross-PMID coverage must be reported separately;
single-PMID or one-hop support must not be described as graph discovery.
