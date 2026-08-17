# Query-Anchor Frozen Replay

- Frozen exposure source: `evaluation/formal/runs/adaptive-replay-small-gpt41/questions`
- LLM/API calls: 0
- Scope: rerank only the paths already present in each frozen top-20 exposure
- Anchor bonus cap: 0.12

| Question | Paths | Rank changes | Top-10 Δ | Mean bonus | Target@5 | Path cites |
|---|---:|---:|---:|---:|---:|---:|
| Q001 | 20 | 0 | 0 | 0.012 | 3 → 3 | 0 |
| Q002 | 0 | 0 | 0 | 0.000 | 0 → 0 | 0 |
| Q007 | 20 | 0 | 0 | 0.002 | 1 → 1 | 0 |

## Interpretation

This deterministic development replay is not a superiority test.
It measures ordering only inside the already exposed path pool.
It cannot recover omitted candidates or regenerate answers.
The frozen GPT-4.1 answers contain no explicit PATH citations, including the two questions with graph exposure (Q001 and Q007). This is a citation-compliance failure for the old run; the new verifier will record it automatically in future results.
