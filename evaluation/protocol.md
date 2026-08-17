# NetMedEx Quantitative Validation Protocol

## Study Objective

Estimate whether NetMedEx Hybrid RAG improves biomedical literature discovery quality,
evidence grounding, mechanistic relationship extraction, time efficiency, and user acceptance
compared with manual PubMed search, a traditional text-only RAG baseline, and a general LLM
baseline.

## Evaluation Arms

- `netmedex_hybrid_rag`: NetMedEx graph-guided Hybrid RAG with semantic edges enabled.
- `traditional_rag`: vector/text retrieval over the same PubMed/PubTator corpus without graph traversal.
- `general_llm`: direct LLM answer without local PMID-grounded retrieval.
- `manual_pubmed`: expert or trained curator using PubMed manually.

## Benchmark Questions

Target size: 50-100 questions.

Recommended strata:

- 20% direct entity-literature retrieval questions.
- 20% gene/chemical/disease association questions.
- 20% mechanism/pathway questions.
- 20% cross-species or preclinical-vs-human questions.
- 20% hypothesis-generation or latent 2-hop path questions.

Each question should include:

- `question_id`
- biomedical domain
- original question
- expected concept aliases
- gold relevant PMIDs, if known
- minimum acceptable answer criteria
- notes for curators

## Metric Definitions

### Retrieval Accuracy

Inputs: `qrels.csv`, `retrieval_runs.csv`.

- Precision@5 = relevant documents among the top 5 retrieved PMIDs divided by 5.
- Recall@10 = relevant documents among top 10 retrieved PMIDs divided by all known relevant PMIDs.
- nDCG@10 = discounted cumulative gain normalized by the ideal ranking.

Primary comparison: `netmedex_hybrid_rag` vs `traditional_rag`.

### Answer Correctness

Inputs: `answer_ratings.csv`.

At least 2-3 blinded domain experts rate each answer:

- correctness: 1-5
- completeness: 1-5
- relevance: 1-5

Primary endpoint: mean correctness score. Secondary endpoints: completeness and relevance.

### Citation Support Rate

Inputs: `claims.csv`.

Each major claim is annotated as:

- `direct`: cited PMID directly supports the claim.
- `partial`: cited PMID supports only part of the claim or requires cautious inference.
- `unsupported`: no cited PMID supports the claim.

Citation support rate = direct claims / all evaluated claims.

Optional lenient support rate = (direct + 0.5 * partial) / all evaluated claims.

### Hallucination Rate

Inputs: `claims.csv`.

Hallucination rate = unsupported claims / all evaluated claims.

Compare `general_llm`, `traditional_rag`, and `netmedex_hybrid_rag`.

### Relationship Quality

Inputs: `edge_ratings.csv`.

Randomly sample semantic graph edges from multiple domains. Experts judge whether each edge has
biological meaning and whether the relation type is correct.

- biological_precision = biologically meaningful edges / evaluated edges.
- relation_type_precision = correct relation labels / evaluated edges.

**No `traditional_rag` counterpart** -- Traditional RAG has no graph, so this audits
`netmedex_hybrid_rag`'s own edge quality rather than a head-to-head comparison.

**Data collection procedure** (this metric has no automated harness the way retrieval does --
someone has to actually produce `edge_ratings.csv`; the steps below are the repeatable version of
what was done for the formal-v1 benchmark, so a future run doesn't have to reinvent it):

1. **Extract real edges.** The frozen system run (`run_formal_50.py`) only persists
   `edge_count`/`path_count` summaries per question, not the edge tuples, so real edges must be
   reconstructed: `python evaluation/build_edge_ratings_worksheet.py --questions <questions.csv>
   --runs-dir <run's per-question corpus.pubtator directory>`. This rebuilds the graph per
   question from the already-fetched `corpus.pubtator` (no PubTator refetch) via
   `PubTatorGraphBuilder(edge_method="semantic", ...)` using the same LLM as the original run --
   this step is not free, it re-runs semantic edge extraction. Enable the `NodeRAG` semantic
   entity-matching fallback (on by default; `--no-node-rag` to disable) so questions whose wording
   doesn't lexically match the graph's node names still resolve. Pass `--verify-relations
   --verifier-provider <provider>` to also enable the v1.4 relation-direction verification pass
   (see `netmedex/semantic_re.py`); use a provider different from the primary extractor when
   possible. Output: `edge_ratings_worksheet.csv` with blank rating columns, one row per extracted
   `(source, target, relation_type, supporting_titles, pmids)` edge, tagged with `min_hop_count`
   so 2-hop path edges (the actual hypothesis-generating ones) can be analyzed separately from
   1-hop edges.
2. **Blind-rate the edges.** Copy the worksheet once per rater (do not let multiple raters
   overwrite the same file). At minimum, run two independent AI raters from different
   model families for a supplementary cross-check (`rate_edge_ratings_gemini.py` /
   `rate_edge_ratings_openai.py`), scoring `biologically_meaningful` and `relation_type_correct`
   (0/1 each) grounded in the supporting article titles. **This AI pass is a preliminary signal,
   not a substitute for real review** -- recruit blinded human biomedical reviewers to repeat the
   same rating task on the same worksheet (or at minimum, spot-check the AI raters' disagreements)
   before reporting results as validated. Tag every AI-generated `notes` cell with a disclosure
   prefix (e.g. `[AI-GENERATED RATING -- <model>. Not a human expert review.]`), matching the
   convention used for the pooled relevance-judgment raters in `evaluation/formal_v2/`.
3. **Merge and score.** Concatenate the rated copies (one `system,edge_id,...,rater_id,...` row
   per rater per edge) into `edge_ratings.csv`, then run
   `python evaluation/metrics.py --input-dir <dir>`. `score_edge_ratings` reports
   `biological_precision`/`relation_type_precision` with a question-level bootstrap 95% CI, plus
   an `_inter_rater_agreement` block (Cohen's kappa per field) whenever exactly two distinct
   `rater_id` values are present in the data -- with more or fewer than two raters, kappa is
   skipped (report simple agreement/majority vote instead).
4. **To compare two pipeline configurations** (e.g. a baseline extractor vs. one with
   `verify_relations` enabled), build and rate a second edge set the same way, then pass
   `--edge-ratings-verified <second file>` to `metrics.py` for a paired bootstrap CI + sign-test
   p-value on the delta (`score_edge_verification_delta`). When the two worksheets share the same
   frozen edge set, the scorer pairs by `edge_id` directly; otherwise it falls back to
   question-level pairing on the `edge_id` prefix. **Caveat:** if the underlying extraction LLM is
   not fully deterministic, part of any observed delta is ordinary run-to-run variance rather
   than the configuration change -- treat a delta whose bootstrap CI excludes zero as a real
   signal, and one that doesn't (even if the raw percentage moved) as statistically
   indistinguishable from noise.

### Path-Level Discovery

Inputs: `path_qrels.csv`, `path_runs.csv`.

Use this when the benchmark is meant to show Hybrid RAG's mechanistic synthesis rather than only
document ranking.

- `path_qrels.csv` should freeze gold paths with the following canonical fields:
  `question_id`, `path_id`, `source`, `bridge`, `target`, `relation_1`, `relation_2`,
  `direction_1`, `direction_2`, `pmids`, `relevance`, `path_type`, `is_negative_control`,
  `evidence_level_1`, `evidence_level_2`, `bridge_valid`, `direction_verified`, and `notes`.
  The scorer consumes the structural path fields plus `pmids` and `relevance`; the remaining
  fields exist so human raters can record why a path is gold, partial, or a negative control.
- `path_runs.csv` should record the surfaced path set for each system or ablation arm.
- The scorer reports bridge entity precision/recall/F1, supported path precision, exact and
  partial path recall, relation and direction alignment, evidence completeness, cross-document
  synthesis rate, and negative-control false-positive rate.
- Keep a separate `evidence_exposure.csv` so each ablation arm can be audited for genuinely
  different evidence visibility, not just a different answer string.

### A-E Ablation Presets

Use the following run profiles when comparing evidence exposure:

- `A_text_only`: text-only RAG, no NodeRAG, no graph context, no 2-hop traversal.
- `B_entity_validated`: text retrieval plus NodeRAG-based entity validation, no graph context.
- `C_one_hop`: graph-assisted retrieval with NodeRAG and 1-hop traversal.
- `D_two_hop`: graph-assisted retrieval with NodeRAG and 2-hop traversal.
- `E_verified_gated_two_hop`: 2-hop traversal plus directional and multi-document evidence gates.
- `legacy`: the current baseline behavior, preserved for backward compatibility with the existing
  formal-v1 run directory.

### Use Efficiency

Inputs: `task_times.csv`.

Compare completion time and successful completion across `manual_pubmed` and NetMedEx.

- median minutes per task
- percent time saved
- completion rate

### Hypothesis Value

Inputs: `hypothesis_ratings.csv`.

Experts rate each generated hypothesis on:

- novelty: 1-5
- plausibility: 1-5
- testability: 1-5
- research_value: 1-5

Primary endpoint: mean of the four dimensions.

**This is the metric most likely to show a `netmedex_hybrid_rag` advantage that Retrieval
Accuracy (document-level P@5/R@10/nDCG@10) structurally cannot capture** -- retrieval metrics
only ask whether relevant documents rank highly, never whether the system surfaced a non-obvious
multi-hop connection across them. Score it specifically on the `hypothesis`/`two_hop_path`-type
questions (plus any `mechanism`-type question whose `expected_concepts` name a specific
gene/entity chain -- see the note on `mechanism`-question inclusion below), not the full benchmark.

**Data collection procedure:**

1. **Identify the stratum.** Filter `questions.csv` to `question_type in {hypothesis,
   two_hop_path}`. Optionally widen to `mechanism`-type questions that share the same "does a
   chain of genes/pathways connect X to Y" shape -- **but exclude any `mechanism` question phrased
   as a negative control** ("does X directly support a link between...", scored under Negative
   Controls in `relevance_guidelines.md`-style rubrics): scoring a deliberately hedged,
   evidence-cautious answer on "novelty" is a category error for this rubric, since the correct
   answer to a negative-control question is often "no direct evidence," not a hypothesis.
2. **Extract the real answers and blind them.** `netmedex_hybrid_rag` and `traditional_rag`
   answers to these questions should already exist in `system_outputs.csv` from the frozen system
   run -- no new system run is needed. `python evaluation/build_hypothesis_worksheet.py` extracts
   them, strips system identity, and assigns each question's two answers a randomized `Q0NN-A` /
   `Q0NN-B` label (fixed seed, so the assignment is reproducible) recorded only in
   `hypothesis_ratings_key.csv` (never share this file with a rater). Re-running the script after
   widening the stratum **preserves every already-assigned label** (keyed per-question, not by a
   single shared random sequence) and writes only the newly added questions to
   `hypothesis_ratings_worksheet_new.csv` -- widening the stratum never invalidates ratings
   already collected for earlier questions.
3. **Blind-rate.** Copy the worksheet once per rater. At minimum, run two independent AI raters
   (`rate_hypothesis_worksheet_gemini.py` / `rate_hypothesis_worksheet_openai.py`) as a
   supplementary cross-check, scoring all four dimensions per answer with a justification citing
   the answer text. As with Relationship Quality, **this is a preliminary AI signal** -- recruit
   blinded human biomedical reviewers to repeat the rating task (`hypothesis_rating_instructions.md`
   has the rubric) before treating results as validated.
4. **Merge and score.** Merge each rated worksheet against the key (recovering `system` per
   `hypothesis_id`) into `hypothesis_ratings.csv`, then run `evaluation/metrics.py`.
   `score_mean_ratings` reports, in addition to the per-system dimension means: an
   `_inter_rater_agreement` block (quadratic-weighted Cohen's kappa per dimension -- appropriate
   for 1-5 ordinal scores, since a 3-vs-4 disagreement should count for less than a 1-vs-5 one)
   whenever exactly two raters are present, and a `_paired_comparison` block (bootstrap 95% CI +
   exact sign-test p-value on the per-question `netmedex_hybrid_rag` minus `traditional_rag`
   difference, averaged across raters within each system+question first) whenever exactly two
   systems are present. **Report the CI and p-value alongside the raw mean difference** -- a
   consistent directional lean (e.g. more questions won than lost) is suggestive but is not the
   same claim as a statistically distinguishable effect, and both should be stated explicitly
   rather than only the more flattering raw number.

### System Performance

Inputs: `performance_logs.csv`.

Record:

- document count
- edge method
- build time seconds
- indexing time seconds
- query response seconds
- concurrent users
- success flag

Report medians, p90, throughput limits, and failure rate by document-count bucket.

### User Acceptance

Inputs: `user_survey.csv`.

Use SUS when possible. Also collect Likert scores for:

- ease_of_use: 1-5
- trust: 1-5
- intent_to_continue: 1-5

SUS score is calculated from the standard 10-item questionnaire.

## Initial Execution Plan

1. Prepare 10 pilot questions across 3-5 biomedical domains.
2. Run all automated scoring scripts on pilot CSVs.
3. Expand to 50-100 questions after the schema is stable.
4. Recruit 2-3 blinded expert raters.
5. Freeze the benchmark before running final systems.
6. For mechanism/2-hop work, run an A-E ablation sweep first, confirm exposure fingerprints differ,
   then do a small human pilot, revise the rubric, estimate variance, complete power analysis, and
   only then recruit the full panel.
7. Report mean, median, 95% bootstrap CI, and per-domain breakdown.

## Reporting Rules

- Separate direct evidence from speculative 2-hop inference.
- Report animal/in vitro and human evidence separately when applicable.
- Do not count a claim as directly supported unless the cited PMID explicitly supports it.
- Count incorrect or fabricated PMIDs as unsupported claims.
- Keep final benchmark questions and qrels versioned.
- For any AI-generated rating pass (Relationship Quality, Hypothesis Value, or a supplementary
  cross-check on any other metric), tag every `notes`/rationale cell with an explicit disclosure
  prefix naming the model and stating it is not a human expert review, and never report an
  AI-only pass's numbers as "expert-reviewed" or as inter-rater reliability in the human sense --
  it is a preliminary signal pending real human review.
- Whenever a metric compares two systems or two pipeline configurations on a sample of fewer than
  ~30 questions, report the bootstrap 95% CI and sign-test (or equivalent) p-value alongside the
  raw mean/percentage difference, not instead of it. A raw difference alone invites reading
  ordinary sampling variance as a real effect; state plainly when a CI includes zero, since that
  means the direction is suggestive at best, not established.
- When exactly two independent raters produced a metric, report Cohen's kappa (quadratic-weighted
  for ordinal 1-5 scores, unweighted for binary judgments) alongside raw percent agreement --
  percent agreement alone overstates reliability whenever the marginal distribution is skewed
  toward one category, and kappa is what corrects for that.
