# Formal-v2 Internal-AI Results

## Benchmark completion

- Questions: 50
- Pooled candidate judgments: 877
- Final relevance distribution: 462 grade-2, 361 grade-1, and 54 grade-0
- AI-majority adjudications: 867
- Three-way AI ties independently adjudicated by OpenAI `gpt-5.6-sol`: 10
- Human expert review claimed: no
- Qrels SHA-256: `1967169d9ac7e57199e2eefc18f648abad12b899b3f2b78bb95cd6e589d60e18`

The completed qrels are suitable for an internal multi-model AI-adjudicated benchmark. They must
not be described as human expert-reviewed.

## Formal run completeness

- Complete questions: 50/50
- System answers: 150/150 nonblank
- Failed questions: 0
- New repair attempts are recorded in `run_manifest.json`.
- Q010 and Q041 were regenerated with a 6,000 completion-token limit.
- Thirteen blank General LLM answers were regenerated without changing their RAG outputs or ranks.

## Retrieval results

| System | Precision@5 | Recall@10 | nDCG@10 | Judged@10 | Bpref |
|---|---:|---:|---:|---:|---:|
| NetMedEx Hybrid RAG | 0.8520 | 0.4316 | 0.6289 | 1.0000 | 0.3954 |
| Traditional RAG | 0.8520 | 0.4394 | 0.6341 | 1.0000 | 0.4254 |

General LLM has no retrieval stage and therefore has no retrieval metrics.

## Paired comparison

| Metric | NetMedEx minus Traditional | Bootstrap 95% CI | Wilcoxon p |
|---|---:|---:|---:|
| Precision@5 | 0.0000 | -0.0160 to 0.0160 | 0.9836 |
| Recall@10 | -0.0079 | -0.0146 to -0.0023 | 0.0144 |
| nDCG@10 | -0.0053 | -0.0182 to 0.0059 | 0.8080 |

Traditional RAG had a small Recall@10 advantage on six questions. Precision@5 was tied, and the
nDCG@10 difference was not significant. These results do not demonstrate a NetMedEx retrieval
advantage under the internal-AI formal-v2 labels.

## Interpretation limits

The new pool eliminates the prior unjudged-document problem: both systems have Judged@10 of 1.0
and Unjudged@10 of 0.0. However, all final relevance labels were resolved through multi-model AI
review and AI adjudication. Biomedical experts should independently audit disagreements, negative
controls, and a random agreement sample before publication-level claims are made.

