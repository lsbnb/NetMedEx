# Anchor/Gate v2 Q001 Diagnostic Replay

Date: 2026-08-09

## Scope

- Question: Q001 (mechanism)
- Model: GPT-4.1
- Frozen PubTator corpus: 9 articles
- Generated systems: Hybrid RAG only
- General-LLM and traditional-answer generation: skipped
- Purpose: validate 60-candidate freezing, Tier gate, PATH compliance, and claim-to-hop audit

## Upstream Corpus Repair

The first successful API attempt built a 47-node/72-edge graph but returned zero query nodes because
the old frozen corpus contained the literal annotation display name `None`. PubTator offsets were
still intact. The parser now reconstructs missing mention names from `title + abstract`, and the
serializer falls back from a missing `identifier_name` to the mention name.

After repair, offline matching recovered `icariin` before the replay was repeated.

## Valid Replay Result

| Measure | Result |
|---|---:|
| Graph nodes | 55 |
| Graph edges | 95 |
| Frozen pre-gate candidates | 60 |
| Candidate Tier A | 4 |
| Candidate Tier B | 0 |
| Candidate Tier C | 56 |
| Tier A in strict top-20 | 4 |
| Exposed claim-safe paths | 4 |
| Rescue triggered | No |
| PATH-cited claims | 4 |
| Deterministically supported claims | 3 |
| Deterministically unsupported claims | 1 |

The remaining unsupported claim mapped to the `icariin -> regulates -> miR-23a` path. Its quote
described a study focused on miR-23a-mediated pathway activation but did not literally support the
selected `regulates` edge, so the strict verifier correctly rejected it.

## Model Decision

GPT-4.1 cited all four exposed PATH signatures after the signature shown in the prompt was preserved
unchanged in the result payload. The old zero-PATH baseline was therefore primarily a path-ID and
frozen-corpus pipeline failure, not evidence of a GPT-4.1 capability ceiling. No generation-model
upgrade is justified by this diagnostic.

## Token Accounting

- Successful pre-fix diagnostic: 25,257 recorded tokens
- Successful post-fix valid diagnostic: 27,407 recorded tokens
- Total across successful Q001 API attempts: 52,664 recorded tokens
- DNS-blocked sandbox attempts reached no API endpoint and added no provider tokens

Q007 was not run in this phase to prevent further cost after Q001 had validated the complete
diagnostic pipeline.

## Limitation and Next Decision

This single development question validates implementation behavior, not Hybrid RAG superiority.
Zero-Tier-A rescue was not exercised because four Tier A paths already appeared in the strict
top-20. The next paid question should be selected only after a token-free or cached-graph screen
identifies a case whose strict top-20 has zero Tier A paths.
