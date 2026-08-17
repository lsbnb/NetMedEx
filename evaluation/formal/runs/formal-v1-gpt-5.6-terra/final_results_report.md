# Formal-v1 Evaluation Results

## Scope and status

- Benchmark: 50 frozen biomedical questions and 384 AI-adjudicated qrels.
- Systems: NetMedEx Hybrid RAG, Traditional RAG, and General LLM.
- Generator model: OpenAI `gpt-5.6-terra`.
- Retrieval generation did not read the frozen qrels.
- The strict retrieval summary was generated from the complete 50-question checkpoint set.
- The answer-only repair pass completed successfully: all three arms contain 50/50 nonblank
  answers (150 total), and the run manifest records zero failed questions.

## Strict frozen-qrels retrieval results

| System | Precision@5 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|
| NetMedEx Hybrid RAG | 0.1040 | 0.0786 | 0.1019 |
| Traditional RAG | 0.1040 | 0.0863 | 0.1025 |
| General LLM | N/A | N/A | N/A |

General LLM has no retrieval stage, so retrieval metrics are not defined for that arm.

Paired question-level comparisons did not demonstrate a NetMedEx advantage:

| Metric | NetMedEx minus Traditional | Bootstrap 95% CI | Exact sign-test p |
|---|---:|---:|---:|
| Precision@5 | 0.0000 | -0.0160 to 0.0160 | 1.0000 |
| Recall@10 | -0.0077 | -0.0171 to 0.0000 | 0.2500 |
| nDCG@10 | -0.0006 | -0.0198 to 0.0166 | 1.0000 |

The nDCG calculation uses graded gain `2^relevance - 1` and logarithmic rank discount.

## Qrels coverage limitation

The complete retrieval snapshot contained 399 ranked records per RAG system. Only 31 NetMedEx
records (7.8%) and 34 Traditional RAG records (8.5%) occurred in the frozen qrels. The remaining
retrieved records are unjudged, not confirmed irrelevant.

- NetMedEx had no judged-positive hit for 29 of 50 questions.
- Traditional RAG had no judged-positive hit for 28 of 50 questions.
- Every retrieved record that did overlap the qrels was graded relevant; none was a judged
  grade-0 record.

The strict scores are therefore lower-bound estimates dominated by incomplete judgment pools.
They do not establish that approximately 90% of retrieved records are irrelevant. A pooled human
adjudication pass over the union of both systems' top-10 results is required before making a
retrieval-quality claim.

## Citation traceability

Across the complete RAG answers, NetMedEx produced 802 explicit PMID mentions and Traditional RAG
produced 752. All explicit PMID mentions referred to records in the corresponding question's
retrieved corpus. General LLM answers contained no explicit PMID citations.

This is corpus traceability, not claim citation support. Direct support, partial support, and
unsupported-claim rates still require claim-level blinded annotation.

## System performance

For the original 50-question execution:

- Mean total processing time: 108.1 seconds per question.
- Median total processing time: 110.0 seconds per question.
- P90 total processing time: 138.6 seconds per question.
- Mean semantic graph construction time: 64.6 seconds per question.
- Median answer generation time: 11.0 seconds for NetMedEx, 10.0 seconds for Traditional RAG,
  and 18.2 seconds for General LLM.
- Corpus processed: 531 PubTator documents, 1,499 graph nodes, and 1,951 graph edges.

These measurements describe single-run processing, not simultaneous-user capacity.

## Interpretation

The earlier 10-question pilot advantage was not reproduced under the current strict formal-v1
qrels. NetMedEx and Traditional RAG were effectively tied on Precision@5 and nDCG@10, while
Traditional RAG had a small, statistically non-significant Recall@10 advantage.

This is not yet a publication-ready final comparison because the qrels pool is highly incomplete
for the actual run. The next defensible analysis is:

1. Pool the union of both RAG systems' top-10 PMIDs for all 50 questions.
2. Obtain blinded biomedical-expert relevance judgments for the pooled PMIDs.
3. Freeze a new qrels version and recompute retrieval metrics with confidence intervals.
4. Conduct blinded answer, citation-support, hallucination, edge-quality, and hypothesis ratings.
