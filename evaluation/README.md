# NetMedEx Evaluation Plan

This folder contains the first-pass evaluation protocol and scoring tools for the
NetMedEx quantitative validation study.

The current implementation is designed to support a staged evaluation:

1. Build a 50-100 question biomedical benchmark with expert relevance labels.
2. Run NetMedEx, a traditional RAG baseline, and a general LLM baseline on the same tasks.
3. Collect blinded expert ratings for answer quality, relationship quality, and hypothesis value.
4. Score retrieval quality, path-level 2-hop discovery, citation support, hallucination rate,
   efficiency, system performance, and user acceptance from structured CSV/JSON files.

## Files

- `quantitative_analysis_restructured_zh.md`: reorganized Traditional Chinese analysis of the
  formal results, limitations, and a validation roadmap tailored to Hybrid RAG, semantic
  integration, and 2-hop discovery.
- `protocol.md`: detailed study design, metrics, and acceptance criteria.
- `metrics.py`: command-line scorer for the structured evaluation files.
- `templates/`: CSV templates for question sets, qrels, path qrels, system outputs, exposure
  audits, expert ratings, timing logs, performance logs, and SUS/Likert surveys.
- `sample_results/`: tiny fixture dataset used for smoke testing the scorer.
- `templates/system_outputs.csv`: curated pilot answer drafts for NetMedEx, traditional RAG,
  and general LLM arms. These are seed outputs and should be replaced by fixed-version system
  runs before final reporting.

## Quick Start

Run the smoke test scorer:

```bash
python evaluation/metrics.py --input-dir evaluation/sample_results --output-json /tmp/netmedex_eval_summary.json
```

Run the automated unit test:

```bash
pytest -q tests/test_evaluation_metrics.py
```

## Metric Inputs

Required files are optional by metric. The scorer calculates only the metrics for files that exist.

- Retrieval: `qrels.csv`, `retrieval_runs.csv`
- Path-level discovery: `path_qrels.csv`, `path_runs.csv`
- Evidence exposure audit: `evidence_exposure.csv`
- System answer archive: `system_outputs.csv`
- Claim grounding: `claims.csv`
- Relation quality: `edge_ratings.csv`
- Answer quality: `answer_ratings.csv`
- Hypothesis value: `hypothesis_ratings.csv`
- Efficiency: `task_times.csv`
- System performance: `performance_logs.csv`
- User acceptance: `user_survey.csv`
