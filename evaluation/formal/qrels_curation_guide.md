# Qrels Curation Guide

This guide records the grading rules and adjudication history used to freeze formal-v1.
`qrels.csv` now contains the final internal AI-adjudicated judgments for Q001-Q050.

## Relevance Grades

- `2`: Directly relevant. The PMID directly addresses the question, mechanism, entity relation,
  intervention, disease context, or requested study type.
- `1`: Partially relevant. The PMID supports an adjacent concept, review-level background,
  a related model system, or one edge of a multi-hop mechanism.
- `0`: Not relevant. The PMID is a false positive, off-topic, wrong disease/context, or too broad
  to support the requested answer.

## Workflow for a Future Version

1. For each question, run the PubMed query in `pubmed_search_query`.
2. Save 10-30 candidate PMIDs in `candidate_pmids`, separated by semicolons.
3. Have at least one curator assign relevance grades; explicitly record whether the curator is
   human or AI.
4. Append only reviewed labels to `qrels.csv` with one row per `(question_id, pmid, relevance)`.
5. Mark `curation_status` as `reviewed` after gold PMIDs are added to `qrels.csv`.
6. Freeze `questions.csv` and `qrels.csv` before generating final system outputs.

## Quality Checks

- Each final question should ideally have 5-15 PMIDs with relevance grade `1` or `2`.
- Include at least two grade-`2` PMIDs when available.
- For negative-control questions, it is acceptable to have few or no grade-`2` PMIDs, but the
  curator should document why.
- Cross-species questions should include study-type notes in `notes`.
- Multilingual questions should use English PubMed search terms but preserve the original user-facing
  question in `questions.csv`.

## Adjudication History

`qrels_candidates_q011_q050.csv` was initially populated by an LLM agent using PubMed/PMC
searches, then independently audited in a second pass. A final abstract-level adjudication accepted
or rejected every flagged regrade and froze the worksheet with
`curation_status = final-ai-adjudicated`.

- The final internal benchmark has 384 judgments: 253 grade-2, 126 grade-1, and 5 grade-0.
- Sixty-three grades changed from their original values: 9 in Q001-Q010 and 54 in Q011-Q050.
- `qrels_adjudication_log.csv` preserves every original grade, final grade, basis, adjudicator type,
  and date.
- **Q047 decision:** evidence shows quercetin activates (not necessarily
  transcriptionally upregulates) CFTR-mediated chloride transport in intestinal tissue (wrong genotype)
  and in human CF respiratory tissue (wrong organ). Q047 is retained as an activation-versus-
  upregulation stress test, with both adjacent papers graded 1 and no grade-2 evidence.
- Q046 and Q048 are retained as clean negative controls and have no grade-2 evidence.

## Second-Pass Audit (`audit_flags_2nd_pass` column)

Every row's initial grade was independently re-checked by a second, separate agent (fresh
PubMed fetch, no access to the first agent's reasoning) specifically hunting for miscalibrated
grades. The historical `audit_flags_2nd_pass` column is a semicolon-separated list aligned 1:1
with `candidate_pmids` and the pre-adjudication grades preserved in
`qrels_adjudication_log.csv`:

- `-` — second pass confirms the current grade, no change suggested.
- `^N` — second pass judged the original grade too low and proposed grade `N`.
- `vN` — second pass judged the original grade too high and proposed grade `N`.

The final adjudication resolved all of these flags. One systematic pattern was that the first-pass
drafting agents were conservative at the 2-vs-1 boundary for
reviews and secondary papers that are actually just as mechanistically direct as their grade-2
peers (see Q036, Q037, Q038 especially, where roughly half the grade-1 papers were flagged `^2`).
Q039 (BDNF/depression) had the most internally inconsistent initial grading; its direct review was
upgraded, while generic plasticity and human peripheral-biomarker papers were downgraded or retained
as partial evidence.

## Q001-Q010 Seed Regrades (qrels.csv)

`qrels.csv` retains `original_relevance`, `audit_status`, and `notes`. Final statuses are
`final-ai-confirmed`, `final-ai-regraded`, or `final-ai-adjudicated`.

9 of 65 rows were regraded (all with a stated reason in `notes`): Q001/24956021 (2->1, no miRNA
content), Q002/28240263 (2->1, osteoclast not osteogenesis paper), Q002/40713676 (1->2,
undergraded), Q005/21547208 (1->2), Q006/18808324 (1->2), Q007/22096355 (1->2), Q007/33072104
(1->2), Q008/22649552 (1->0, real mismatch -- no intestinal content at all), Q009/21388555 (2->1,
no chemical intervention tested despite the question asking "which chemicals").

Correction to an earlier verbal report: Q001/33339654 was initially flagged as possibly overgraded
during the audit, but that flag was based on the auditing agent misstating the PMID's existing
grade in its own output -- the true original value (1) already matched the agent's recommendation,
so no change was made or was ever actually needed. Caught during implementation, not before.

## Interpretation

Formal-v1 is frozen and reproducible for internal system comparison. The manifest explicitly records
`human_expert_review_claimed: false`. A future human expert pass should create a new benchmark
version or countersigned adjudication record rather than silently changing formal-v1.
