# Hybrid RAG evidence examples

## Executive result

The examples should be presented as a portfolio rather than as four equivalent
successes.  CFTR is the clearest positive demonstration, Metformin is a clean
path-extraction control, Icariin is a useful strict-gate negative control, and
HBV is an exploratory four-hop stress test that still needs stronger endpoint
entity grounding.

| Example | Evidence result | Hidden-information value | Recommended role |
|---|---|---|---|
| CFTR → intestinal inflammation | Multiple claim-safe molecular paths plus a separately qualified microbiome branch | High: exposes two convergent evidence streams | Primary demonstration |
| Metformin → AMPK → mTOR | Two independent Tier-A two-hop paths | Medium: consolidates replicated pathway evidence | Positive/calibration control |
| Icariin → osteogenic differentiation | 61 bounded 3–4-hop candidates, 0 Tier A; one shorter direct Tier-A path | High diagnostic value: shows that the gate prevents cross-species overclaiming | Negative/safety control |
| Chronic HBV → HCC | One Tier-A two-hop path; one formal Tier-A four-hop candidate | Potentially high, but the four-hop endpoint quote requires stricter entity grounding | Exploratory stress test |

## 1. CFTR dual-pathway convergence — primary example

### Molecular signaling branch

`CFTR dysfunction → disrupted CFTR–β-catenin interaction → β-catenin
destabilization → NF-κB nuclear translocation → intestinal inflammation`

- PMID [27588407](https://pubmed.ncbi.nlm.nih.gov/27588407/)
- Models: ΔF508 mouse intestine and human intestinal epithelial cell lines.
- Formal graph results include claim-safe `CFTR → NF-κB → inflammation` and
  `CFTR → β-catenin → inflammation` paths.

### Microbiome branch

`CFTR dysfunction → altered intestinal environment → gut dysbiosis ⇢
intestinal inflammation`

- CFTR mutation reshapes the microbiome: PMID
  [31961914](https://pubmed.ncbi.nlm.nih.gov/31961914/).
- Intestinal-specific Cftr loss drives dysbiosis and inflammation: PMID
  [37546931](https://pubmed.ncbi.nlm.nih.gov/37546931/).
- Dysbiosis–inflammation synthesis: PMID
  [26973296](https://pubmed.ncbi.nlm.nih.gov/26973296/) and systematic review
  PMID [36600119](https://pubmed.ncbi.nlm.nih.gov/36600119/).
- The final dysbiosis-to-inflammation edge remains a candidate mediator rather
  than a settled causal edge.

### Why it demonstrates Hybrid RAG

The molecular and microbiome literatures are independently retrievable.  The
graph adds value by showing that both streams converge on the same inflammatory
phenotype while preserving the difference between direct mechanism and
cross-study association.

Final figure:
[`cftr_dual_pathway_convergence_v1.png`](cftr_dual_pathway_reference_v1/cftr_dual_pathway_convergence_v1.png)

## 2. Metformin–AMPK–mTOR — positive control

Two Tier-A paths were recovered:

1. `Metformin → activates AMPK → inhibits mTOR`
   - PMID [34062070](https://pubmed.ncbi.nlm.nih.gov/34062070/)
   - PMID [40140842](https://pubmed.ncbi.nlm.nih.gov/40140842/)
2. `Metformin → activates AMPK → suppresses mTOR`
   - PMID [24009772](https://pubmed.ncbi.nlm.nih.gov/24009772/)
   - PMID [29167573](https://pubmed.ncbi.nlm.nih.gov/29167573/)

This is the cleanest extractor/gate control because every hop is directional
and the polarity is consistent.  It should not be used as the sole proof of
hidden information because the cited studies span different cancer contexts
(ALL, CRC and ESCC); those contexts must remain visible in any figure.

## 3. Icariin–osteogenesis — strict-gate negative control

- Fixed endpoints: Icariin and osteoblast differentiation/osteogenesis.
- Bounded 3–4-hop candidates audited: **61**.
- Strict Tier-A 3–4-hop paths: **0**.
- Shorter claim-safe direct path:
  `Icariin → promotes osteogenic differentiation`, PMID
  [35002378](https://pubmed.ncbi.nlm.nih.gov/35002378/).
- Same-named miR-21/PTEN nodes with distinct Gene IDs were not merged across
  species.

This example is valuable because it demonstrates that Hybrid RAG does not gain
apparent performance by silently composing cross-species fragments.

Audit:
[`species_safe_endpoint_audit_v2.json`](image_chain_acceptance_v1/species_safe_endpoint_audit_v2.json)

Figure:
[`icariin_species_safe_evidence_diagram_v2.png`](image_chain_acceptance_v1/icariin_species_safe_evidence_diagram_v2.png)

## 4. Chronic HBV–HCC — exploratory four-hop stress test

### Confirmed two-hop bridge

`Chronic hepatitis B → liver cirrhosis → hepatocellular carcinoma`

- PMIDs [41997336](https://pubmed.ncbi.nlm.nih.gov/41997336/) and
  [39411648](https://pubmed.ncbi.nlm.nih.gov/39411648/).
- Formal gate: Tier A, two hops.

### Four-hop candidate

`Chronic hepatitis B → HBV → STAT1 → HKDC1 → hepatocellular carcinoma`

- PMIDs [24574713](https://pubmed.ncbi.nlm.nih.gov/24574713/),
  [30842274](https://pubmed.ncbi.nlm.nih.gov/30842274/) and
  [38351096](https://pubmed.ncbi.nlm.nih.gov/38351096/).
- Formal gate: Tier A, four hops.
- PMID 38351096 was outside the text top-k in the frozen comparison, making
  this a graph-incremental candidate.
- Limitation: the final supporting quote describes HKDC1-promoted tumor immune
  evasion but does not explicitly name HCC in the quote.  It should therefore
  be re-audited with a rule requiring both endpoint entities in every quote
  before publication use.

## Recommended presentation order

1. **Metformin:** show that extraction and directional gating work.
2. **CFTR:** show the positive Hybrid RAG contribution—convergent hidden
   biological meaning with evidence tiers.
3. **Icariin:** show that species-safe gating rejects an attractive but
   unsupported long chain.
4. **HBV:** present as future four-hop stress-test work, not as the headline
   validated result.

