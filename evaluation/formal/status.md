# Formal Evaluation Status

| Area | File | Status | Next Action |
|---|---|---|---|
| Benchmark questions | `questions.csv` | 50 questions frozen as formal-v1 | Use unchanged for all fixed system runs |
| Gold relevance labels | `qrels.csv` | 384 judgments internally AI-adjudicated and frozen | Optional independent human sign-off for publication claims |
| Gold PMID candidate worksheet | `qrels_candidates_q011_q050.csv` | Q011-Q050 finalized | Preserve as adjudication evidence |
| Adjudication audit trail | `qrels_adjudication_log.csv` | Complete for all 384 judgments | Human reviewer may countersign or add a separate pass |
| Freeze manifest | `benchmark_freeze_v1.json` | Checksums and counts recorded | Verify before each formal run |
| Qrels curation instructions | `qrels_curation_guide.md` | Finalized with adjudication history | Reuse only when creating a future benchmark version |
| Formal 50-question run | `runs/formal-v1-gpt-5.6-terra/` | Complete: 50 questions, 0 failures | Preserve the frozen run artifacts |
| Retrieval outputs | `runs/formal-v1-gpt-5.6-terra/retrieval_runs.csv` | Complete and scored against formal-v1 qrels | Expand the judgment pool before publication claims |
| Path-level outputs | `runs/formal-v1-gpt-5.6-terra/path_runs.csv` | Not present in the completed legacy run | Generate a fixed A-E/path run before path-level scoring |
| Exposure audit | `runs/formal-v1-gpt-5.6-terra/evidence_exposure.csv` | Not present in the completed legacy run | Generate matched exposure artifacts with the A-E/path run |
| A-E replay wrapper | `evaluation/run_formal_ae_replay.py` | Available: replays frozen corpora into versioned A-E subruns | Use this to materialize the missing path/exposure artifacts |
| System answers | `runs/formal-v1-gpt-5.6-terra/system_outputs.csv` | Complete: 50 nonblank answers in each of 3 arms | Blind system labels before expert rating |
| Claim support | `claims.csv` | Seed annotation present | Re-annotate actual outputs |
| Answer quality | `answer_ratings.csv` | Template only | Collect 2-3 blinded expert ratings |
| Relation quality | `edge_ratings.csv` | 224 unique edges rated by two blinded AI models; preliminary metrics calculated | Obtain blinded human biomedical review |
| Hypothesis value | `hypothesis_ratings.csv` | 19 questions rated by two blinded AI models; preliminary paired metrics calculated | Obtain blinded human biomedical review |
| Efficiency | `task_times.csv` | Template only | Run manual PubMed vs NetMedEx timed tasks |
| Performance | `performance_logs.csv` | Template only | Run 100/500/1000/3000+ document tests |
| User acceptance | `user_survey.csv` | Template only | Collect SUS and Likert responses |
| Formal metric table | `formal_evaluation_table.md` | Formal retrieval and preliminary AI-panel metrics updated | Update after pooled qrels and human review |
| Manuscript text | `manuscript_results_draft.md` | Pilot draft present; formal run section pending | Revise after pooled qrels and human review |

## Minimum Criteria for Final Reporting

- At least 50 frozen benchmark questions. Complete for formal-v1.
- At least 2 expert raters for answer and hypothesis quality.
- At least 100 sampled semantic edges for relationship quality.
- Fixed system versions and prompts for all compared systems.
- A frozen `path_qrels.csv` plus matching `path_runs.csv` / `evidence_exposure.csv` for any
  path-level or A-E ablation claims.
- Separate reporting for pilot seed, formal automatic metrics, and blinded expert ratings.
