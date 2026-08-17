# Edge Disagreement Calibration Report

## Scope

- Frozen edge population: 224 edges across the mechanism/hypothesis stratum.
- Legacy Gemini/OpenAI disagreements: 54 edges.
- Token-budgeted sample: at most two disagreements per question, 23 edges across 12 questions.
- Rich evidence supplied to judges: question, edge endpoints/type, PMIDs, article titles, and
  abstracts. This sample is deliberately disagreement-enriched and is not a population precision
  estimate.

## Independent rich-rubric results

OpenAI GPT-4.1 and Claude Haiku 4.5 both rated all 23 calibration edges. Their exact agreement was:

| Field | Exact agreement | Krippendorff alpha |
|---|---:|---:|
| Entity valid | 91.3% | 0.0918 |
| Relation exists | 95.7% | 0.6905 |
| Relation type correct | 78.3% | 0.4049 |
| Direction correct | 100.0% | 1.0000 |
| Evidence support | 82.6% | 0.5602 |

Low alpha despite high entity-valid agreement reflects prevalence sensitivity: almost every
sampled entity was accepted, so the small number of disagreements has a large chance-corrected
effect. Relation type remains the least stable decision-relevant field.

Claude's positive rates were 91.3% entity-valid, 91.3% relation-exists, 73.9%
relation-type-correct, 87.0% direction-correct, and 82.6% evidence-supported. OpenAI's corresponding
rates were 100.0%, 95.7%, 87.0%, 87.0%, and 73.9%. These are calibration-sample rates only.

## Consensus gate audit

Across the 23 doubly rated edges, consensus failed or the two judges disagreed on nine edges:

- Q004-E15, Q008-E05, Q025-E04, Q037-E03: relation-type concerns.
- Q016-E02, Q029-E17, Q037-E05: multi-field failures including entity/relation/evidence concerns.
- Q048-E01, Q048-E05: evidence-support concerns.

This supports an automatic evidence-completeness gate and shows that relation-type verification
needs further calibration. It does not support treating every extracted directional label as
reliable.

## Engineering actions completed

- Added graph-native node IDs and per-hop evidence completeness to structured paths.
- Added an evidence-gated 2-hop profile and routed adaptive mechanism/hypothesis questions to it.
- Fixed path ranking to read nested `{pmid: {relation: confidence}}` values instead of applying a
  constant 0.5 confidence to every semantic edge.
- Moved adaptive routing before graph construction so text-only questions skip semantic graph
  extraction entirely.
- Added exact provider-reported token usage to future judge checkpoints/manifests.

## Token accounting limitation

Earlier checkpoints predate exact usage capture. Their manifests retain prompt-character estimates;
provider-reported token counts will be available for all subsequent calls. Failed schema/empty
responses were never silently retried after the calibration runner was switched to one attempt.
