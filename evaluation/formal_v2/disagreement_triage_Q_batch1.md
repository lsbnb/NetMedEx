# Triage Notes: 3-Way Full-Disagreement Candidates (first pass, 35/50 questions)

Scope: the 632 candidates from the 35 questions where all three AI raters (Claude, GPT-5.6-sol,
Gemini) currently have genuine (non-templated) ratings. 13 candidates had a full 0/1/2 split.
This file categorizes those 13 by root cause so a human reviewer can adjudicate efficiently
instead of re-deriving the reasoning from scratch. **Do not remove any of these candidates from
the pool** -- see rationale below.

## Category 1 -- broad review lacks the specific gene/entity the question requires (4 candidates)

Now covered by the new rubric clause in `relevance_guidelines.md` ("Gene/entity-specificity
requirement for mechanism and two_hop_path questions"): cap at grade 1 regardless of topical
prominence.

- **Q004-C001** (PMID 29693253) -- "curcumin ... PI3K/AKT pathway" broad review, no single named gene in a defined chain. Recommend grade **1**.
- **Q004-C003** (PMID 31223280) -- "cellular signaling pathways and miRNAs" broad review. Recommend grade **1**.
- **Q040-C007** -- KRAS/tumor-microenvironment review; question asks specifically about metabolic pathways, this doesn't name one. Recommend grade **1**.
- **Q044-C009** -- broad phytocompound-cardiovascular review, not resveratrol-specific, no human-vs-preclinical split. Recommend grade **1**.

(Q004-C011 is a borderline fifth case -- a primary paper on curcumin/mitochondrial apoptosis that
doesn't name a single terminal gene either; leaning grade 1 but worth a human second look.)

## Category 2 -- candidate discusses an adjacent pathway/gene, not the one the question asks about (4 candidates)

These are **not** pool curation errors -- `pool_provenance.csv` shows most of these were retrieved
and ranked by the real NetMedEx / Traditional RAG systems (see ranks below), which is exactly the
kind of system-retrieval miss this pooled benchmark exists to capture. Keep in the pool; grade as
a genuine relevance judgment (0), not remove.

- **Q028-C004** (PMID 26202948, NetMedEx rank 9, Traditional rank 9) -- Notch/gamma-secretase inhibitor + docetaxel in prostate cancer. Question asks about EGFR-to-apoptosis-resistance genes; this is a different receptor pathway entirely. Recommend grade **0**, `exclusion_reason: wrong_entity`.
- **Q028-C012** (PMID 36938944, NetMedEx rank 5, Traditional rank 4) -- CDK4/6-inhibitor-resistance proteomics in breast cancer, not EGFR-specific. Recommend grade **0**, `wrong_entity`.
- **Q012-C018** (PMID 40640358, NetMedEx rank 6, Traditional rank 6) -- TREM2/Wnt-beta-catenin exosome mechanism; question asks about cytokines mediating microglial activation, TREM2 is not a cytokine. Recommend grade **0** or **1** (adjacent immune mechanism) -- human judgment call on how strictly "cytokine" should be read.
- **Q019-C005** (PMID 30293065, no system rank -- sourced from the independent PubMed corpus, not system retrieval) -- CETP genetic variant study, not an adipokine study. Recommend grade **0**, `wrong_entity`.

## Category 3 -- right general mechanism family, wrong disease/outcome context (2 candidates)

Same logic as Category 2: real system-retrieved candidates, keep in pool, grade as genuine misses.

- **Q029-C010** (PMID 40113668, NetMedEx rank 5, Traditional rank 7) -- cerebromicrovascular senescence and vascular cognitive impairment; question asks about atherosclerosis specifically. Recommend grade **0** or **1**, `wrong_context`.
- **Q035-C006** (PMID 42166024, NetMedEx rank 4, Traditional rank 4) -- circadian disruption/senescence in periodontitis; question asks about senolytics and tissue regeneration. Recommend grade **0**, `wrong_context`.

## Category 4 -- genuine judgment call on how far downstream a gene can be and still count (2 candidates)

No systematic rule fix here -- these need an actual human call.

- **Q049-C006** -- CTHRC1 marker paper; TGF-beta is mentioned but not the focus.
- **Q049-C011** -- IL-11 paper; IL-11 is described as downstream of TGF-beta1, but the paper's subject is IL-11, not TGF-beta itself.

## Summary for the human reviewer

- Categories 1 and (partly) 4 are resolved by the new rubric clause going forward, but these
  specific 5-6 candidates were rated before the rule existed and should be manually re-graded to
  match it.
- Categories 2 and 3 (6 candidates) are **not pool errors** -- do not delete them. Four of the six
  are real NetMedEx/Traditional RAG retrieval results and are exactly the kind of judged-negative
  the pooled benchmark needs to compute honest precision. Grade them 0 (or 1 where noted) with
  the appropriate `exclusion_reason`.
- Category 4 (2 candidates) is a genuine borderline call -- flag for discussion, no shortcut rule.

This covers only the 13 disagreements found in the 35/50 questions that had genuine (non-
templated) ratings as of this pass. Re-run the 3-way comparison once the remaining 15 questions'
`ai_rater_3.csv` entries are no longer templated placeholders, and append any newly found
full-disagreement candidates to a follow-up triage note rather than folding them in here silently.
