# Instructions for AI Rater 3 (supplementary multi-model cross-check)

## What this is

`ai_rater_3.csv` is a blank rating worksheet, structurally identical to `expert_rater_1.csv` /
`expert_rater_2.csv`, for use with a **third, architecturally different LLM** (a different
company/model family than whatever produced rater 1 and rater 2) as a supplementary
cross-check — not as a replacement for genuine human review.

This file sits **outside** the formal two-rater pipeline (`finalize_pooled_reviews.py` only reads
`expert_rater_1.csv` and `expert_rater_2.csv`). Its purpose is triage: where all three AI sources
agree, that grade is probably safe to provisionally trust; where they disagree, that is exactly
where a human reviewer's time is best spent.

**This is still not human review.** Do not report agreement among 3 LLMs as "inter-rater
reliability" or "expert validation" — label it explicitly as multi-model AI consensus.

## Task

For each row, read `question` + `title` + `abstract` and fill in:

- `relevance` — `2`, `1`, or `0` (see rubric below)
- `confidence` — `3`, `2`, or `1`
- `exclusion_reason` — only when `relevance` is `0`; leave blank otherwise
- `reviewer_notes` — one short sentence citing the specific reason from the abstract

Do not touch `candidate_id`, `question_id`, `domain`, `question`, `pmid`, `title`, or `abstract`.

## Grading rubric (verbatim from `relevance_guidelines.md`)

**Relevance labels**
- `2` = Directly relevant. The article directly addresses the question's entity relationship,
  mechanism, intervention, disease context, population, or requested study type.
- `1` = Partially relevant. The article supplies useful adjacent evidence, review-level context,
  a different but informative model, or one supported segment of a multi-hop mechanism.
- `0` = Not relevant. The article is off-topic, uses the wrong entity or disease context, is too
  broad to support the requested answer, or only shares keywords.

Judge relevance to the question, not article quality. A weak study can be directly relevant, while
a high-quality study can still be irrelevant to the specific question.

**Negative controls** (questions asking whether direct evidence exists for a specific causal/
mechanistic claim — this benchmark includes several deliberate negative-control questions):
- Assign `2` only when the requested direct causal or mechanistic link is actually tested.
- Assign `1` to adjacent evidence: different tissue, genotype, species, direction of effect, or
  one incomplete segment of the proposed pathway.
- Assign `0` when the paper cannot support even the adjacent proposition.
- Do not upgrade a paper because the proposed relationship is biologically plausible. It is fine
  and expected for a negative-control question to end up with mostly 0s and 1s.

**Confidence**
- `3` = Clear decision from title and abstract.
- `2` = Reasonable decision with some ambiguity.
- `1` = Full text or specialist adjudication would really be needed — use honestly, don't default
  to a higher number just because a decision was made.

**Exclusion reasons** (only when `relevance` = 0, pick exactly one):
`off_topic`, `wrong_entity`, `wrong_context`, `wrong_study_type`, `too_broad`,
`no_usable_evidence`, `duplicate`, `other`.

**Blinding**: judge only from `question` + `title` + `abstract`. Do not seek out or use any
information about which retrieval system found this PMID, its rank, or any prior grade — none of
that is present in this file, so this should not be an issue, but flagging it for completeness.

## How to run this with a chat-only LLM (no file-editing tools)

If the third model is used through a plain chat interface (no direct CSV editing), don't paste
all 877 rows at once — context limits and attention both degrade over very long inputs. Instead:

1. Split the work by `question_id` (50 questions, 3–25 candidates each — see `review_status.csv`
   for exact counts) or into fixed batches of ~15–20 rows.
2. For each batch, paste: this file's rubric section, plus the `question`, `title`, and `abstract`
   for each candidate `candidate_id` in that batch.
3. Ask the model to output one line per candidate in this exact tab-separated format, nothing
   else:

   ```
   candidate_id	relevance	confidence	exclusion_reason	note
   ```

   (use `NA` in the `exclusion_reason` slot when relevance is not 0)
4. Save all batches' output into one combined text file and bring it back — it can be merged into
   `ai_rater_3.csv` the same way `expert_rater_1.csv` was populated (match on `candidate_id`).

## After rating

Update this file's status in a new `ai_rater_3_manifest.json` (copy the structure used by
`expert_rater_2_manifest.json`) recording which provider/model was actually used, and note in
`README.md` that a third AI cross-check is available. Do not rename this file to
`expert_rater_3.csv` or wire it into `finalize_pooled_reviews.py` — the formal pipeline is
deliberately a fixed two-rater design; this file is a side channel for triage only.

### Completion Status (Updated)

- **Status**: Completed (877 / 877 candidate rows rated)
- **Model**: Google Gemini 3.1 Pro (`gemini-3.1-pro-preview` via Google Gemini API)
- **Manifest**: `evaluation/formal_v2/ai_rater_3_manifest.json`
- **Checkpoints**: `evaluation/formal_v2/ai_rater_3_checkpoints/*.json`
- **Live Gemini 3.1 Pro API Results**:
  - `relevance = 2` (Directly relevant): 400 candidates (45.61%)
  - `relevance = 1` (Partially relevant): 367 candidates (41.85%)
  - `relevance = 0` (Not relevant): 110 candidates (12.54%)
- **Multi-Model Consensus / Triage Comparison (Rater 1 Claude vs Rater 3 Gemini 3.1 Pro)**:
  - **Agreement**: 595 candidates (67.84%)
  - **Disagreement (Triage Focus for Human Expert Review)**: 282 candidates (32.16%)
- **Reviewer Notes Prefix**: `[AI-GENERATED RATING -- Gemini 3.1 Pro. Supplementary multi-model cross-check.]`

