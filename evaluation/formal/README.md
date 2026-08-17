# Formal Evaluation Workspace

This folder contains the frozen internal formal-v1 retrieval benchmark and the remaining
workspaces for NetMedEx quantitative evaluation.

## Current Status

- `questions.csv`: 50 frozen formal questions with adjudicated gold PMIDs.
- `qrels.csv`: 384 PMID relevance judgments across Q001-Q050.
- `qrels_candidates_q011_q050.csv`: finalized candidate worksheet for Q011-Q050.
- `qrels_adjudication_log.csv`: row-level original/final grades, rationale, adjudicator type,
  and date for all 384 judgments.
- `benchmark_freeze_v1.json`: benchmark version, scope, counts, and SHA-256 checksums.
- `qrels_curation_guide.md`: relevance rules and adjudication history.
- `retrieval_runs.csv`: initialized with seed rankings for NetMedEx, traditional RAG, and general LLM.
  Replace these rows with fixed-version system runs before final reporting.
- `path_runs.csv`: path-level outputs for the active hybrid profile, including 2-hop structured
  paths, relation labels, direction labels, and supporting PMIDs. This is the file that supports
  the new path-level discovery endpoints.
- `evidence_exposure.csv`: per-question evidence exposure audit for the active ablation profile.
  Use this to confirm that A-E arms are not just different prompts, but truly expose different
  node/path/PMID sets.
- `system_outputs.csv`: initialized with curated answer drafts. Replace with actual model/system outputs.
- `claims.csv`: initialized with seed claim-level annotations. Re-annotate after actual system outputs are frozen.
- `answer_ratings.csv`, `task_times.csv`, `performance_logs.csv`, `user_survey.csv`: initialized
  from templates and still require formal data collection.
- `edge_ratings_worksheet.csv`: real NetMedEx graph edges reconstructed per-question from
  `corpus.pubtator` (the frozen run only persisted `edge_count`/`path_count` summaries, not the
  edge tuples) via `build_edge_ratings_worksheet.py`, which rebuilds the graph with
  `PubTatorGraphBuilder(edge_method="semantic", ...)` (same LLM, `gpt-5.6-terra`, as the original
  run -- not free) and extracts the real `(source, target, relation_type, supporting PMIDs)` edges
  that land on 2-hop retrieval paths. **No `traditional_rag` counterpart** -- Traditional RAG has
  no graph, so this audits NetMedEx's own edge quality rather than a head-to-head comparison.
  Initially only 12/19 questions produced any edges; `find_relevant_nodes()`'s substring-only
  entity matching was suspected, so the script was extended to build a `NodeRAG` semantic index
  (already implemented in `netmedex/node_rag.py`, already wired into `netmedex/chat_bridge.py` and
  one `webapp/callbacks/chat_callbacks.py` path -- just not into this eval script or 3 other
  webapp "auto" paths, which skip it for latency). Uses ChromaDB's bundled local embedding model,
  not an LLM call, so re-enabling it here was effectively free. Re-running just the 7 zero-edge
  questions with `--question-ids Q015 Q016 Q022 Q028 Q035 Q040 Q050` recovered 2 (Q015: 0->15
  edges, Q016: 0->10) -- confirming entity-wording mismatch was the cause for those two. The
  other 5 (Q022, Q028, Q035, Q040, Q050) stayed at 0 edges even with semantic matching, which more
  likely reflects genuinely sparse semantic-edge extraction over those 15-article corpora than an
  entity-linking bug; this was not investigated further. Final: 224 candidate edges across 14/19
  questions (95 with `min_hop_count=2`, i.e. real 2-hop path edges; 129 with `min_hop_count=1`).
- `edge_ratings_worksheet_gemini.csv` / `edge_ratings_worksheet_openai.csv`: the 224 edges rated
  by the same two independent AI raters as the hypothesis worksheet (Gemini 3.1 Pro via
  `rate_edge_ratings_gemini.py`; GPT-5.6-sol via `rate_edge_ratings_openai.py`) for
  `biologically_meaningful` and `relation_type_correct` (0/1 each), grounded in the supporting
  article titles. Merged into `edge_ratings.csv` (448 rows: 2 raters x 224 edges).

  **This is the least flattering result of the whole evaluation effort, and it is a robust one --
  inter-rater agreement is 80% raw / Cohen's kappa 0.62 (biologically_meaningful) and 89% raw /
  kappa 0.75 (relation_type_correct) -- "substantial" agreement on the Landis-Koch scale, so this
  is not rating noise:**

  | Metric | Value | 95% bootstrap CI |
  | --- | ---: | ---: |
  | biological_precision | 0.53 | [0.48, 0.62] |
  | relation_type_precision | 0.33 | [0.28, 0.40] |

  (CIs are computed by `evaluation/metrics.py`'s `score_edge_ratings`, bootstrapped at the
  question level -- 19 resampling units, not 448 rows -- so they correctly reflect that edges
  within the same question aren't independent draws.)

  Broken down by `min_hop_count`, the 2-hop edges specifically -- the ones that are the actual
  "hypothesis-generating" value proposition -- score *worse* on relation correctness than 1-hop
  edges (28% vs 36% relation_type_correct; biological_meaningful is roughly flat, ~53% both).
  Concrete failure modes seen in the rater notes: **direction reversal** (e.g. an edge labeled
  `runx2 --upregulates--> mir153` when the source article says miR-153 targets Runx2, the reverse
  direction; `cystic fibrosis --causes--> cftr` when CFTR mutations cause CF, not the other way),
  and **extraction artifacts** -- at least two edges (Q001-E19, Q001-E20) have a target entity of
  literally `"0409"`, a non-biological string that leaked through as a graph node. The direction
  reversal issue looks like the semantic relation extractor's more actionable fix; the artifact
  strings look like a separate, narrower node-normalization bug worth its own look.

  Rebuild with `python evaluation/build_edge_ratings_worksheet.py` (defaults to all 19 questions;
  pass `--question-ids` to target a subset, `--no-node-rag` to reproduce the old substring-only
  behavior).

  **v1.4 relation-direction verification pass -- measured effect.** After implementing the
  optional second-LLM verification pass (see the main `CHANGELOG.md` v1.4.0 entry), the same
  19-question graph rebuild + 2-rater audit was repeated with `--verify-relations
  --verifier-provider google` on top of the same `--model gpt-5.6-terra` primary extractor
  (`edge_ratings_worksheet_verified.csv` / `edge_ratings_verified.csv`, 448 rows: 2 raters x 224
  edges). Building this rerun surfaced and fixed a real bug first: the verifier (Gemini via the
  OpenAI-compatible endpoint) reliably appended a stray trailing character after an otherwise
  well-formed JSON object, so the *first* attempt verified 0/224 edges silently-safely (every
  edge fell back to "keep as extracted" on a parse error) -- fixed in `semantic_re.py` with a
  lenient JSON loader (`json.JSONDecoder().raw_decode`, tolerates trailing garbage) plus a regex
  fallback, covered by two new regression tests.

  | Metric | Baseline | With verification | Raw delta |
  | --- | ---: | ---: | ---: |
  | biological_precision | 0.53 | 0.51 | -0.02 |
  | relation_type_precision (overall) | 0.33 | 0.35 | +0.02 |
  | relation_type_precision, hop_count=2 only | 0.28 | 0.34 | +0.06 |
  | relation_type_precision, hop_count=1 only | 0.36 | 0.36 | 0.00 |

  **Paired per-question bootstrap CI on these deltas** (`score_edge_verification_delta`,
  13 questions have both a baseline and a verified edge set to pair -- Q018 only has baseline
  edges, Q028 only has verified edges, both excluded from the paired analysis):

  | Comparison | n paired questions | Mean diff (verified − baseline) | 95% bootstrap CI | Sign-test p |
  | --- | ---: | ---: | ---: | ---: |
  | relation_type_precision, overall | 13 | -0.018 | [-0.105, 0.058] | 0.58 |
  | relation_type_precision, hop_count=1 only | 13 | -0.046 | [-0.154, 0.046] | 1.00 |
  | relation_type_precision, hop_count=2 only | 10 | +0.005 | [-0.111, 0.098] | 0.73 |
  | biological_precision, overall | 13 | -0.062 | [-0.163, 0.036] | 0.58 |

  **This overturns the previous framing of this section.** Every CI above comfortably contains
  zero and every sign-test p-value is far from significant -- including the hop_count=2 row,
  which the raw percentages (0.28 -> 0.34) had made look like "a small but targeted improvement."
  Paired properly by question with only 10-13 questions available, that specific claim does not
  hold up: it is statistically indistinguishable from the run-to-run extraction noise flagged
  below. The two honest caveats from the original analysis stand and are now the *headline*
  finding, not a footnote: (1) `gpt-5.6-terra`'s extraction is not perfectly deterministic, so the
  "baseline" and "verified" edges are two independent draws over the same corpora, not the same
  edges re-scored -- with only 10-13 paired questions, ordinary run-to-run variance is easily
  large enough to produce a 0.06 swing in either direction by chance. (2) A live single-question
  instrumented check (Q001) found the verifier only downgraded ~1/23 (~4%) of directional edges it
  reviewed -- far below the ~67% direction-error rate the original 2-rater audit found -- so the
  mechanism demonstrably runs and can catch errors (see the unit tests in
  `tests/test_semantic_prompt.py`), but at this sample size we cannot say it moved the needle on
  the actual edge population. A larger paired sample (more questions, or repeated extraction runs
  per question to average out non-determinism) would be needed before claiming a real effect
  either way.
- `hypothesis_ratings_worksheet.csv` (blank, reproducible master) / `hypothesis_ratings_key.csv`:
  a blinded rating worksheet built from the real `netmedex_hybrid_rag` vs `traditional_rag`
  answers to the 9 `hypothesis`/`two_hop_path` questions (see
  `hypothesis_rating_instructions.md`). This stratum is where a KG-driven advantage would show up
  that document-retrieval metrics (P@5/R@10/nDCG@10) cannot capture. Rebuild the blank master with
  `python evaluation/build_hypothesis_worksheet.py` (fixed seed=42, so the A/B blinding assignment
  in `hypothesis_ratings_key.csv` never changes).
- `hypothesis_ratings_worksheet_gemini.csv` / `hypothesis_ratings_worksheet_openai.csv`: two
  **independent blinded AI raters'** completed copies of the worksheet above (Gemini 3.1 Pro via
  `rate_hypothesis_worksheet_gemini.py`; GPT-5.6-sol via `rate_hypothesis_worksheet_openai.py`),
  merged with the key into `hypothesis_ratings.csv`.
  The stratum was widened from the original 9 `hypothesis`/`two_hop_path` questions to 19 by
  also including `mechanism`-type questions that are structurally the same "does a chain of
  genes/pathways connect X to Y" shape (Q001, Q011, Q016, Q022, Q023, Q029, Q031, Q034, Q037,
  Q048). **Q005 was excluded** despite being `question_type: mechanism` because it is phrased as
  a negative-control question ("does X directly support..."), not a hypothesis-generation one --
  scoring a deliberately hedged answer on "novelty" is a category error for this rubric.
  `build_hypothesis_worksheet.py` preserves any already-assigned A/B mapping in
  `hypothesis_ratings_key.csv` exactly (keyed per-question, not by a single shared RNG sequence),
  so widening the stratum never invalidates ratings already collected for earlier questions --
  rerunning it only ever appends new questions and writes them to
  `hypothesis_ratings_worksheet_new.csv` for rating.
  Final result (76 rows: 2 raters x 19 questions x 2 systems):

  | Dimension | NetMedEx Hybrid RAG | Traditional RAG |
  | --- | ---: | ---: |
  | overall_mean | 4.21 | 4.07 |
  | novelty | 3.26 | 3.05 |
  | plausibility | 4.71 | 4.66 |
  | testability | 4.74 | 4.63 |
  | research_value | 4.13 | 3.92 |

  Paired per-question (mean of 4 dimensions, averaged across both raters): NetMedEx scores higher
  on 9/19 questions, Traditional on 3/19, tied on 7/19 (mean diff +0.145) -- a consistent lean
  toward NetMedEx, not a large effect size.

  **Statistical rigor, computed by `score_mean_ratings`'s `_paired_comparison` /
  `_inter_rater_agreement` (bootstrapped at the question level, 19 resampling units):**

  | Statistic | Value |
  | --- | ---: |
  | Paired mean diff (NetMedEx − Traditional), n=19 questions | +0.145 |
  | 95% bootstrap CI | [-0.020, 0.316] |
  | Sign-test p (9 wins / 3 losses / 7 ties, ties excluded) | 0.146 |

  **The 95% CI includes zero and the sign-test p-value is well above 0.05 -- with 19 questions,
  NetMedEx's edge on this stratum is a real, consistent lean (12 of the 12 non-tied questions'
  worth of evidence points the same direction, 9-to-3) but is not statistically significant at the
  conventional threshold.** Read it as "the best available directional evidence that a KG helps on
  hypothesis-generation questions," not as a validated effect -- the honest headline from this
  whole evaluation effort is still "supplementary AI signal, promising direction, underpowered
  sample," not "proven."

  Per-dimension inter-rater agreement (quadratic-weighted Cohen's kappa, appropriate for 1-5
  ordinal scores -- penalizes a 1-vs-5 disagreement far more than a 3-vs-4 one):

  | Dimension | Weighted kappa | Interpretation (Landis-Koch) |
  | --- | ---: | --- |
  | novelty | 0.40 | fair-to-moderate |
  | plausibility | 0.42 | moderate |
  | testability | 0.12 | slight -- the two raters barely agree beyond chance on this dimension |
  | research_value | 0.43 | moderate |

  `testability`'s low kappa is worth flagging on its own: raw exact-match rate for that dimension
  didn't stand out earlier, but kappa corrects for chance agreement given each rater's marginal
  distribution, and reveals `testability` is the dimension the two AI raters agree on least. This
  is a supplementary AI signal from two independent models, not a human-expert-reviewed result --
  see `hypothesis_rating_instructions.md` for the blinding rules and rubric.
- `formal_evaluation_table.md`: manuscript/report-ready metric table.
- `manuscript_results_draft.md`: draft Results text for the current pilot seed evaluation.

## Scoring Command

```bash
python evaluation/metrics.py --input-dir evaluation/formal --output-json evaluation/formal/summary_formal_seed.json
```

`relation_quality` (from `edge_ratings.csv`) and `hypothesis_value` (from `hypothesis_ratings.csv`)
each include an `_inter_rater_agreement` block (Cohen's kappa -- quadratic-weighted for the 1-5
hypothesis dimensions, unweighted for the binary edge fields) and, where applicable, a
`_paired_comparison` block (bootstrap 95% CI + exact sign-test p-value on the paired per-question
NetMedEx-vs-Traditional-RAG difference). `path_retrieval` is scored from `path_qrels.csv` and
`path_runs.csv`, and `arm_exposures` is scored from `evidence_exposure.csv`. To additionally
compare a baseline `edge_ratings.csv` against a second pipeline configuration's edge ratings
(e.g. v1.4's `verify_relations`), pass `--edge-ratings-verified`:

```bash
python evaluation/metrics.py --input-dir evaluation/formal \
  --edge-ratings-verified evaluation/formal/edge_ratings_verified.csv
```

This adds an `edge_verification_delta` block: paired bootstrap CI + sign-test p-value on
`biological_precision` and `relation_type_precision`, pairing by `edge_id` when the two worksheets
share the same frozen edge set and otherwise falling back to question-level pairing on the
`edge_id` prefix.

## Formalization Rules

1. Freeze `questions.csv` and `qrels.csv` before generating final system outputs.
2. Use the same questions for all systems.
3. Record model/provider/version/prompt settings in `system_outputs.csv` or a companion run log.
4. For path-level benchmarking, freeze `path_qrels.csv` alongside `qrels.csv` and keep
   `path_runs.csv` / `evidence_exposure.csv` together with the answer and retrieval outputs.
5. Keep expert raters blinded to system identity when rating answer quality, edge quality, and hypotheses.
6. Treat `partial` claim support as weaker than direct support in final reporting.
7. Report pilot-seed and final-system-run results separately.

## Review Status

The retrieval benchmark was internally AI-adjudicated and frozen on 2026-07-27. PMID metadata
and all disputed grades were checked against PubMed records and abstracts. This is sufficient for
an internal reproducible benchmark, but it must not be described as human expert-reviewed. If a
publication requires that claim, have a biomedical expert sign `qrels_adjudication_log.csv` or
record a separate human adjudication pass before reporting final results.

The next operational step is to generate fixed-version retrieval, path-level, and answer outputs
for all 50 questions and then collect blinded expert ratings.

## Completed Formal Run

The formal-v1 50-question run completed at
`runs/formal-v1-gpt-5.6-terra/`. It uses OpenAI `gpt-5.6-terra` for all three comparison
arms, PubMed ESearch relevance ordering, up to 15 PubTator-annotated records per question,
semantic graph edges, and top-10 retrieval. The runner now also records structured 2-hop paths
when a non-legacy profile emits them. The completed legacy run contains retrieval, answer, and
timing outputs but no `path_runs.csv` or `evidence_exposure.csv`, so it cannot support path-level
or A-E ablation claims. The runner did not read `qrels.csv` during generation.

If you need a remedy for the missing path/exposure artifacts, replay the frozen per-question
`corpus.pubtator` files into a new versioned workspace with:

```bash
python evaluation/run_formal_ae_replay.py \
  --source-run-dir evaluation/formal/runs/formal-v1-gpt-5.6-terra \
  --output-root evaluation/formal/runs/formal-v1-gpt-5.6-terra-ae-replay-v1
```

That wrapper replays all five A-E profiles into separate subdirectories and writes an
`ae_replay_manifest.json` alongside them so the replay itself is versioned and auditable.

For a cost-controlled smoke replay, `evaluation/run_formal_ae_replay_reuse_graphs.py` performs
semantic extraction once with Terra, persists one `graph.pkl` per question, then reuses those
graphs for all A-E profiles while generating answers with Luna. The resulting benchmark is a
separate version and must not be pooled with Terra-only formal-v1 scores.

```bash
python evaluation/run_formal_ae_replay_reuse_graphs.py \
  --source-run-dir evaluation/formal/runs/formal-v1-gpt-5.6-terra \
  --output-root evaluation/formal/runs/formal-v1-ae-replay-terra-graphs-luna-answers-v1 \
  --queries evaluation/formal/formal_run_queries_q001_q010.csv \
  --expected-question-count 10 \
  --graph-model gpt-5.6-terra \
  --answer-model gpt-5.6-luna
```

After a replay, build the blinded candidate worksheet with
`evaluation/build_path_qrels_review.py`. It intentionally leaves `relevance`, verification, and
evidence-level fields blank; only an adjudicated copy may be used as `path_qrels.csv` for formal
path metrics.

When manual review is too large, `evaluation/ai_assist_path_qrels.py` can draft an explicitly
provisional qrels file with an independent Anthropic model. The output includes a per-path audit
trail and must remain labeled AI-assisted until a human accepts or edits the labels.

Inspect the frozen completion manifest with:

```bash
sed -n '1,120p' evaluation/formal/runs/formal-v1-gpt-5.6-terra/run_manifest.json
```
