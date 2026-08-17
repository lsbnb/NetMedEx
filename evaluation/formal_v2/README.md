# Formal-v2 Pooled Evaluation

This workspace calibrates the retrieval benchmark without changing `evaluation/formal` or its
frozen formal-v1 qrels.

## Current state

- 50 questions
- 877 pooled question-PMID candidates
- 0 candidates missing a PubMed title; 4 PubMed records have no abstract
- Two source-blinded expert worksheets
- Separate provenance retained for audit only
- **`expert_rater_1.csv` is filled in, but by an AI (Claude), not a human reviewer.** Every
  `reviewer_notes` cell for these 877 rows is prefixed
  `[AI-GENERATED RATING -- NOT A HUMAN EXPERT REVIEW. Preliminary reference pass only.]`. This
  directly departs from this workspace's own rule below ("do not use model outputs as relevance
  rationales") and from the intended two-independent-human-rater design -- it was done at the
  project owner's explicit request as a preliminary/bootstrap pass, not a substitute for real
  review. `review_status.csv`/`review_summary.json` mark this as
  `ai_pass_complete_pending_human_review`, distinct from a genuine human `complete` status, so
  downstream tooling and readers don't mistake it for the real thing.
- `expert_rater_2.csv` is fully rated (877/877) by OpenAI `gpt-5.6-sol`, as recorded in
  `expert_rater_2_manifest.json`. This is an AI rating pass, not a human review.
- `ai_rater_3.csv` (+ `ai_rater_3_instructions.md`, `ai_rater_3_manifest.json`): a **third,
  supplementary** worksheet fully rated (877/877 candidates) via **Google Gemini 3.1 Pro API** (`gemini-3.1-pro-preview`), deliberately kept outside the two-rater pipeline (not read by
  `finalize_pooled_reviews.py`), meant as a multi-model cross-check. Purpose:
  compare all 3 AI sources and use their disagreements to triage which candidates most need a
  real human's attention -- not to replace human review, and not to be reported as inter-rater
  reliability.
- Status: internal multi-model AI adjudication is complete. A total of 867 candidates were resolved
  by 2/3 AI majority and 10 three-way ties were independently adjudicated by `gpt-5.6-sol`.
  `qrels.csv` is the completed internal-AI benchmark. Real human review is still required before
  describing it as expert-validated.

## Files

- `expert_rater_1.csv`: worksheet for reviewer 1.
- `expert_rater_2.csv`: worksheet for reviewer 2.
- `adjudication.csv`: agreement and third-review workspace.
- `pool_provenance.csv`: system rank, PubMed-corpus membership, and formal-v1 provenance. Do not
  provide this file to blinded reviewers.
- `pubmed_metadata_cache.json`: metadata used to construct the worksheets.
- `pool_manifest.json`: candidate-pool scope and status.
- `review_status.csv`: question-level assignment and progress.
- `relevance_guidelines.md`: mandatory grading rules.
- `formal_v1_diagnostic_metrics.json`: diagnostic metrics showing judgment-pool incompleteness.
- `ai_rater_3.csv`: completed supplementary Gemini 3.1 Pro worksheet.
- `ai_adjudication_log.csv`: row-level three-model labels, final label, method, and rationale.
- `ai_adjudication_manifest.json`: internal-AI adjudication scope and model record.
- `qrels.csv`: completed internal-AI formal-v2 relevance judgments.
- `summary_formal_v2_internal_ai.json`: retrieval metrics against internal-AI qrels.
- `formal_v2_internal_ai_results.md`: results and interpretation limits.

## Review workflow

1. Assign different biomedical reviewers to `expert_rater_1.csv` and `expert_rater_2.csv`.
2. Reviewers independently label every row without opening `pool_provenance.csv`.
3. Accept only relevance values `0`, `1`, or `2`; record confidence as `1`, `2`, or `3`.
4. Merge the two reviews into `adjudication.csv`.
5. A third reviewer adjudicates every disagreement and low-confidence item.
6. Calculate inter-rater agreement before adjudication.
7. Export adjudicated rows to a new `qrels.csv` and freeze checksums.
8. Recompute retrieval metrics against formal-v2 qrels.

Merge completed worksheets and prepare adjudication with:

```bash
python evaluation/finalize_pooled_reviews.py --input-dir evaluation/formal_v2
```

The command calculates raw agreement and Cohen's kappa. It exports `qrels.csv` only after every
candidate has an adjudicated label.

Do not modify formal-v1 labels in place and do not use model outputs as relevance rationales.

## Rebuild

```bash
python evaluation/build_pooled_benchmark.py \
  --output-dir evaluation/formal_v2 \
  --fetch-missing-metadata
```

The builder preserves rater and adjudication files once review entries are present.
