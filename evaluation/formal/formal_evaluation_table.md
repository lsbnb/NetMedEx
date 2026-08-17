# Formal Evaluation Table

Table X. Formal quantitative evaluation framework and current results for
NetMedEx Hybrid RAG.

| Evaluation Domain | Metric | Current Result | Formal Target / Decision Rule | Required Input File(s) | Current Status |
|---|---:|---:|---:|---|---|
| Retrieval relevance | Precision@5 | Formal-v1: NetMedEx 0.1040; traditional RAG 0.1040; difference 0.0000 (95% CI -0.0160 to 0.0160) | NetMedEx >= 0.70 and higher than both baselines | `qrels.csv`, formal run `retrieval_runs.csv` | 50-question strict frozen-qrels result; 92% of top-10 records are unjudged, so this is a lower bound |
| Retrieval coverage | Recall@10 | Formal-v1: NetMedEx 0.0786; traditional RAG 0.0863; difference -0.0077 (95% CI -0.0171 to 0.0000) | NetMedEx >= 0.65, or statistically higher than baselines | `qrels.csv`, formal run `retrieval_runs.csv` | 50-question run complete; exact sign-test p=0.2500 |
| Ranking quality | nDCG@10 | Formal-v1: NetMedEx 0.1019; traditional RAG 0.1025; difference -0.0006 (95% CI -0.0198 to 0.0166) | NetMedEx >= 0.75 and higher than both baselines | `qrels.csv`, formal run `retrieval_runs.csv` | 50-question run complete; exact sign-test p=1.0000 |
| Answer correctness | Expert correctness score | Placeholder 4.0/5 for NetMedEx | Mean >= 4.0/5 with 2-3 blinded expert raters | `answer_ratings.csv` | Requires blinded expert review |
| Answer completeness | Expert completeness score | Placeholder 4.0/5 for NetMedEx | Mean >= 4.0/5 | `answer_ratings.csv` | Requires blinded expert review |
| Answer relevance | Expert relevance score | Placeholder 5.0/5 for NetMedEx | Mean >= 4.0/5 | `answer_ratings.csv` | Requires blinded expert review |
| Citation grounding | Citation support rate | NetMedEx 0.9231; traditional RAG 0.50; general LLM 0.00 | NetMedEx >= 0.85 | `claims.csv` | Seed claim annotation; redo after actual system outputs |
| Hallucination control | Unsupported claim rate | NetMedEx 0.00; traditional RAG 0.00; general LLM 0.80 | NetMedEx <= 0.10 | `claims.csv` | Seed claim annotation; curated set is not final evidence |
| Relationship quality | Biological edge precision | AI panel: 0.5312 (95% CI 0.4833–0.6187; 224 unique edges, 448 ratings) | >= 0.75 across >= 100 sampled semantic edges | `edge_ratings.csv` | Two-model blinded AI cross-check complete; requires human expert confirmation |
| Relation typing | Relation-type precision | AI panel: 0.3281 (95% CI 0.2799–0.3980; 224 unique edges, 448 ratings) | >= 0.70 across >= 100 sampled semantic edges | `edge_ratings.csv` | Two-model kappa 0.747; requires human expert confirmation |
| Path-level discovery | Bridge F1 / supported path precision / direction accuracy | Not yet frozen; template added | Require frozen `path_qrels.csv` and matched `path_runs.csv` | `path_qrels.csv`, `path_runs.csv`, `evidence_exposure.csv` | Needed for the Hybrid RAG / 2-hop superiority claim |
| Use efficiency | Time saved vs manual PubMed | Placeholder 79.17% | >= 50% median time reduction | `task_times.csv` | Requires timed user tasks |
| Hypothesis value | Mean novelty/plausibility/testability/research-value score | AI panel: NetMedEx 4.2105; traditional RAG 4.0658; paired difference 0.1447 (95% CI -0.0197–0.3158; p=0.1460) | Mean >= 3.8/5 | `hypothesis_ratings.csv` | 19 questions, two-model blinded AI cross-check; difference not statistically distinguishable and human review remains required |
| System performance | End-to-end processing latency | Formal run median 110.0 s; p90 138.6 s per question | Median <= 30 s for target workload | formal run `run_metrics.csv` | Single-run workload measured; does not characterize concurrent capacity |
| System scalability | Build/index latency and failure rate | Placeholder build 30 s, index 8 s, failure 0.0 | Report by 100/500/1000/3000+ document workloads | `performance_logs.csv` | Requires formal performance run |
| User acceptance | SUS | Placeholder 75 | SUS >= 70 | `user_survey.csv` | Requires 5-15 target users |
| Trust and continued-use intent | Likert trust / intent-to-continue | Placeholder trust 4.0/5, intent 4.0/5 | Mean >= 4.0/5 | `user_survey.csv` | Requires target-user survey |

## Interpretation Rules

- Formal-v1 retrieval results are strict lower-bound estimates because more than 90% of retrieved
  top-10 records are outside the frozen judgment pool.
- `questions.csv` and `qrels.csv` are frozen as formal-v1; fixed Q001-Q050 retrieval and answer
  outputs are complete.
- Fixed formal answers are complete, but answer, citation-support, and hallucination metrics still
  require blinded annotation of those outputs.
- Expert-dependent metrics should be reported with rater count and, when possible, inter-rater agreement.
- Human, animal, and in vitro evidence should be stratified for mechanism and cross-species questions.
