# Triage Notes: 3-Way Full-Disagreement Candidates (final, all 50 questions)

Supersedes `disagreement_triage_Q_batch1.md` (which only covered 35/50 questions, before rater 3
finished). Rater 3 (Gemini, `gemini-3.1-pro-preview`) completed all 877 candidates with genuine,
non-templated content -- verified: 0% duplicate notes across all 50 questions, 67.8% relevance
agreement with rater 1 (0% identical note text), 75.8% agreement with rater 2, checkpoint
timestamps spread realistically over ~23 hours.

Full 3-way (Claude / GPT-5.6-sol / Gemini) comparison across all 877 candidates: **10 candidates**
have a complete 0/1/2 split (down from 13 in the partial 35-question pass -- the newly finished
15 questions did not add net new full disagreements).

## Category 1 -- broad review lacks the specific gene/entity the question requires (9 of 10)

All resolved going forward by the "Gene/entity-specificity requirement" clause added to
`relevance_guidelines.md`: cap at grade 1. Consistent pattern across all 9: Claude graded 2,
GPT-5.6-sol graded 1, Gemini graded 0 -- a strictness gradient, not random noise, which is itself
evidence the disagreement is rule-shaped rather than a reading-comprehension error by any one
rater.

| Candidate | PMID | Question | Why it's Category 1 |
|---|---|---|---|
| Q004-C001 | 29693253 | genes mediating curcumin->apoptosis 2-hop | "curcumin ... PI3K/AKT pathway" broad review, no single named gene |
| Q004-C003 | 31223280 | genes mediating curcumin->apoptosis 2-hop | "cellular signaling pathways and miRNAs" broad review |
| Q004-C011 | (see expert_rater_1.csv) | genes mediating curcumin->apoptosis 2-hop | primary paper, but no single terminal gene named either -- borderline |
| Q025-C007 | 26803842 | DMD-to-inflammation mechanisms | mdx mouse fast-myofiber characterization paper, no specific inflammatory gene named as the mediating link |
| Q032-C001 | 18328887 | cytokines linking asthma exacerbation to remodeling | broad review of persistence/progression mechanisms, no cytokine pinned to the exacerbation-remodeling link specifically |
| Q032-C010 | 19075788 | cytokines linking asthma exacerbation to remodeling | TGF-beta/eosinophil/IL-13 review, general not exacerbation-specific |
| Q032-C011 | 15032597 | cytokines linking asthma exacerbation to remodeling | general asthma persistence/progression review |
| Q032-C012 | 12170265 | cytokines linking asthma exacerbation to remodeling | TGF-beta/Smad2 remodeling association, not exacerbation-specific |
| Q040-C010 | 36864508 | metabolic pathways connecting KRAS to immune evasion | KRAS/PD-L1 review, not metabolic-pathway-specific |

Note: the four Q032 candidates and Q040-C010 were sourced from formal-v1 qrels (already graded 1
or 2 there during the original curation/audit pass), not from live system retrieval -- they were
legitimately literature-relevant at curation time, they just sit on the exact review-vs-primary
boundary this rubric clause was written for. Re-grade to **1** per the new rule.

## Category 2 -- adjacent entity, not the one asked about (1 of 10)

- **Q012-C018** (PMID 40640358, NetMedEx rank 6, Traditional rank 6 -- real system retrieval, keep
  in pool) -- TREM2/Wnt-beta-catenin exosome mechanism; question asks about cytokines mediating
  microglial activation, and TREM2 is a receptor, not a cytokine. Claude=2, GPT-5.6-sol=0,
  Gemini=1. This was a genuine human judgment call (how strictly should "cytokine" be read when
  IL-6/IL-1beta/TNF-alpha appear as measured inflammatory readouts of an upstream TREM2/Wnt
  mechanism, rather than as the tested causal mediator itself).

  **RESOLVED by human reviewer: relevance = 2.** Decision: cytokines counted as relevant even when
  measured as outcome/readout markers rather than the paper's primary tested mechanism, as long as
  they are tied to the microglial activation state in an AD model. Apply this same interpretation
  consistently to any other Q012 candidates with the same marker-vs-mediator pattern.

  **Consistency sweep of the rest of Q012 (24 candidates total) applying this same standard:**
  three more candidates had the identical structure (an upstream non-cytokine intervention/factor
  as the paper's tested subject, cytokines/inflammation measured only as a downstream readout,
  but in a genuine AD model, not a generic LPS model) and were majority-graded 1 by GPT-5.6-sol/
  Gemini against Claude's 2:

  - **Q012-C004** (hearing-loss induction in 5xFAD/Tg2576 mice, cytokine/inflammation as readout of the hearing-loss intervention) -- **RESOLVED: relevance = 2**.
  - **Q012-C008** (BMSC-exosome/BDNF treatment in AD-like mice, inflammation as readout of the exosome treatment -- same structure as C018) -- **RESOLVED: relevance = 2**.
  - **Q012-C012** (TOMM40 genetic variant carriers, neuroinflammation as readout of the genetic variant) -- **RESOLVED: relevance = 2**.

  Six other Q012 candidates (C001, C005, C009, C013, C015, C020) have the same readout structure
  but use a generic LPS-induced neuroinflammation model rather than a genuine AD model (transgenic
  mouse or AD patient tissue) -- left as-is (already consistently graded low by all three raters)
  since their lower grade is attributable to the model/disease-context mismatch, not the
  marker-vs-mediator question this standard addresses.

## Action items

1. Re-grade the 9 Category-1 candidates to `1` (their current grades of 0/1/2 across the three AI
   raters should all be superseded by this rule, not adjudicated by majority vote).
2. Send **Q012-C018** to the human reviewer as a genuine borderline case.
3. The 6 candidates from the earlier 35-question pass (`disagreement_triage_Q_batch1.md`
   Categories 2-4: Q028-C004, Q028-C012, Q019-C005, Q029-C010, Q035-C006, Q049-C006, Q049-C011)
   are unaffected by this update -- their guidance stands as written there.
4. `finalize_pooled_reviews.py` still only reads `expert_rater_1.csv`/`expert_rater_2.csv` --
   rater 2 is still missing real human confirmation (it is AI/GPT-5.6-sol output) and adjudication
   has not been run. These 10 (now effectively 1, after applying the rubric rule) full-disagreement
   candidates are a starting priority list for whoever adjudicates, not a replacement for full
   human review of the rest of the pool.
