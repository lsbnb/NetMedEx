# Strict Gate Improvement Spec

Date: 2026-08-09
Scope: Improve negative outcomes from strict graph gating without loosening evidence standards.

## Goal

Reduce false negatives from strict gating so Hybrid RAG preserves genuinely useful graph evidence while continuing to block unsupported path-based claims.

This spec targets the main production graph retrieval path in [netmedex/graph_rag.py](/home/cylin/NetMedEx/netmedex/graph_rag.py) and its downstream use in [netmedex/chat.py](/home/cylin/NetMedEx/netmedex/chat.py).

## Current Failure Modes

Observed from the current implementation:

1. Primary relation selection is unstable.
   The path builder currently selects a per-edge `primary` relation by `Counter(all_rels).most_common(1)`. This ignores whether the chosen relation has the best confidence, best quote support, or best match to the query.

2. Evidence is only loosely attached to the chosen relation.
   The formatter emits one deterministic quote for the edge, but the structured path only stores a list of PMIDs and quote strings. It does not preserve a first-class `(pmid, relation, quote, confidence)` bundle per hop.

3. Path ranking is graph-aware but not sufficiently question-aware.
   `_extract_top_k_paths()` uses edge score, bottleneck scoring, and node semantic relevance, but it does not explicitly reward paths whose start/end/bridge nodes align with the query's asked source, target, or mechanism.

4. Gate output is binary in practice.
   The system effectively yields either usable paths or zero-path. That collapses "weak but still useful" paths together with truly unsupported paths.

5. No post-generation path-claim verification exists.
   The LLM is instructed to inspect quotes, but there is no deterministic verifier that checks whether a generated hidden claim is actually supported hop by hop.

## Design Principles

1. Do not reduce evidence standards.
2. Separate retrieval utility from claim-generation utility.
3. Preserve auditability at the hop level.
4. Prefer deterministic heuristics before adding more LLM cost.
5. Keep evaluation token-light until offline metrics improve on dev replay.

## Proposed Changes

### 1. Edge Evidence Pairing

Add a canonical per-edge support object so every hop can carry evidence as structured data instead of loosely coupled lists.

Target shape per hop:

```json
{
  "selected_relation": "inhibits",
  "selected_pmid": "12345678",
  "selected_quote": "EGFR inhibition reduced MAPK signaling...",
  "selected_confidence": 0.91,
  "directional": true,
  "support_tier": "A",
  "support_reasons": ["quote_present", "directional_relation", "confidence_ge_0.8"]
}
```

Implementation notes:

- Add a helper that iterates edge `relations`, `evidences`, and `confidences` together.
- Score candidate supports at the `(pmid, relation)` level rather than at the edge level only.
- Prefer candidates with:
  - available quote
  - matching confidence entry
  - directional/mechanistic relation when present
  - better query alignment if multiple supported relations exist
- Keep the existing text formatter for backward compatibility, but derive it from the selected support object.

### 2. Query-Aware Anchor Scoring

Introduce deterministic query anchors so path ranking rewards question alignment, not just graph quality.

Anchor types:

1. `source_anchor`
2. `target_anchor`
3. `mechanism_anchor`
4. `context_anchor` for disease/process/drug terms

Implementation notes:

- Start with low-cost heuristics:
  - exact or normalized node-name overlap with query
  - existing node semantic relevance hits from `node_rag.search_nodes()`
  - cue words in query such as `how`, `why`, `mechanism`, `via`, `through`, `between`, `effect of`
- Compute per-path anchor features:
  - `start_matches_query_focus`
  - `end_matches_query_focus`
  - `bridge_matches_mechanism_context`
  - `path_spans_multiple_anchor_types`
- Add a bounded anchor bonus to the path score. This should rerank close candidates, not overpower low-evidence edges.

### 3. Tiered Gate Output

Replace implicit pass/fail behavior with a 3-tier path gate.

Tier definitions:

- `Tier A`: claim-safe
  - every hop has selected `(pmid, relation, quote, confidence)`
  - relation direction is not contradicted
  - endpoints align with the question
  - two-hop bridge is semantically plausible

- `Tier B`: retrieval-safe but not claim-safe
  - path is relevant
  - at least one hop is incomplete or weak
  - may be used for reranking or "possible association" context
  - must not be exposed as hidden mechanistic evidence

- `Tier C`: discard
  - poor question alignment, missing critical evidence, or relation/direction instability

Required structured fields per path:

```json
{
  "gate_tier": "B",
  "gate_reasons": ["missing_quote_hop_2", "good_endpoint_alignment"],
  "claim_safe": false,
  "retrieval_safe": true
}
```

### 4. Zero-Path Rescue

Only trigger rescue when strict gating produces zero Tier A paths.

Rescue flow:

1. Expand candidate path pool modestly.
2. Re-rank using anchor-aware score.
3. Admit Tier B paths as retrieval context only.
4. If still no usable candidate, keep graph hidden from claim generation.

Important:

- Rescue must not bypass evidence requirements for Tier A.
- Rescue is a fallback for recall, not a shortcut for hidden-claim generation.

### 5. Claim-to-Hop Verifier

Add a deterministic verification stage after generation for any claimed graph-derived insight.

Checks:

1. Every claim maps to one explicit path ID.
2. The mapped path is Tier A.
3. Each hop relation and direction match the claim wording.
4. Quotes do not get stretched beyond their literal support.

Minimum output:

```json
{
  "claim_id": "HC-03",
  "path_id": "PATH-02",
  "verdict": "unsupported",
  "reasons": ["hop_2_quote_does_not_support_activation"]
}
```

## Implementation Order

### Phase 1: Core Data Repair

1. Add edge support selection helper.
2. Replace ad hoc primary relation selection in structured paths.
3. Attach canonical hop support objects to every emitted path.
4. Preserve current prompt compatibility.

### Phase 2: Path Relevance Repair

1. Add anchor extraction from query.
2. Add anchor-aware features to path scoring.
3. Re-rank candidate paths before final truncation.

### Phase 3: Gate Repair

1. Add Tier A/B/C path classification.
2. Expose `gate_tier`, `gate_reasons`, `claim_safe`, `retrieval_safe`.
3. Update prompt construction so only Tier A paths are eligible for hidden-claim generation.

### Phase 4: Recovery and Verification

1. Add zero-path rescue.
2. Add claim-to-hop verifier.
3. Run small frozen dev replay before any paid holdout rerun.

## Evaluation Plan

Run evaluation in increasing cost order.

### Offline / Deterministic First

- `% paths with canonical hop support`
- `% strict-gated questions with >=1 Tier A path`
- `% questions with >=1 Tier B path when Tier A is absent`
- relation-direction consistency rate
- quote completeness rate
- endpoint alignment rate

### Low-Cost Replay Next

Use existing frozen dev or small replay artifacts before any new formal panel.

Primary targets:

| Metric | Current problem | Target |
| --- | --- | --- |
| Tier A availability | Too many 0-path cases | >= 80% on dev replay |
| Path traceability | Claims often cannot cleanly map back | >= 80% |
| Relation/direction correctness | Unstable path semantics | >= 80% |
| Unsupported novelty | Too many overextended claims | <= 15% |
| Validated hybrid-only hidden claims | Currently near zero | materially above current baseline |

### Multi-LLM Panel Only After Offline Improvement

Re-run the low-cost AI panel only after the upstream path metrics improve. Otherwise we would spend tokens measuring the same failure mode again.

## Current Frozen-Replay Status (2026-08-09)

- Q001 post-repair diagnostic produced 4 Tier A paths; GPT-4.1 cited all 4 path signatures and the deterministic verifier accepted 3/4 claims. This does not justify a generation-model upgrade for PATH compliance.
- A token-free legacy-cache screen initially labeled Q008 and Q011 as zero-A. Both were false negatives caused by duplicate entity IDs sharing the CFTR or mTOR alias; grouping IDs by the matched query span changed each question to 1 Tier A path.
- The remaining zero-A mechanism case, Q022, belongs to the frozen adaptive holdout and is excluded from development selection.
- The synthetic frozen-pool regression verifies that a Tier A path ranked below 20 is recovered from candidates 21–60 without an extra semantic-search or LLM call.
- Therefore no further paid replay is currently warranted. The next valid paid test requires a new preregistered development candidate that remains zero-A after corpus-name repair and duplicate-alias grouping.

### Development v2 follow-up

A later three-question development pilot added node-alias preservation, longest-span entity
matching, context-role anchors, frozen-replay gate parity, and bounded Tier A bridge-diversity
expansion. It produced 9 deterministically supported candidates for two-provider blinded review.
Eight of nine passed consensus traceability/evidence/direction, but zero were judged Hybrid-only
because the Text-RAG answers already contained equivalent content. The active bottleneck is now
contrastive incremental-information selection, not merely Tier A availability. See
`runs/hybrid-hidden-meaning-dev-v2-diversity-paired/development_report.md`.

## Concrete Code Touchpoints

- [netmedex/graph_rag.py](/home/cylin/NetMedEx/netmedex/graph_rag.py)
  - `get_subgraph_context_with_paths()`
  - `score_edge_components()`
  - `_extract_top_k_paths()`
  - `_format_path()`
  - `_format_edge_evidence()`
  - new helper(s) for support selection and gate classification

- [netmedex/chat.py](/home/cylin/NetMedEx/netmedex/chat.py)
  - restrict graph-derived hidden-claim generation to Tier A
  - allow Tier B as retrieval/reranking aid only
  - surface no-path vs no-claim-safe-path more explicitly

## Non-Goals

1. No immediate model upgrade.
2. No human expert blind review in this phase.
3. No threshold-loosening that converts unsupported paths into claim evidence.
4. No full formal rerun until dev replay improves.

## Immediate Next Step

Implement Phase 1 first:

1. add canonical hop support selection
2. replace unstable `primary` relation picking
3. emit structured path evidence bundles

This is the highest-leverage fix because it improves both strict gate precision and downstream auditability without requiring any new provider cost.

## Implementation Status — 2026-08-09

- Phase 1 complete: canonical `(relation, PMID, quote, confidence)` support is emitted for every
  hop, with deterministic selection and legacy-field compatibility.
- Phase 2 complete: source/target/mechanism/context anchors apply a bounded `0.12` reranking bonus;
  every structured path exposes its base score, bonus, and anchor features.
- Phase 3 complete: paths are classified as Tier A claim-safe, Tier B retrieval-only, or Tier C
  discard. Only Tier A directional paths can enable graph-grounded causal generation.
- Phase 4a complete: when the strict top-20 contains no Tier A path, zero-Tier-A rescue examines
  candidates 21–60 from the already scored pool. Recovered Tier A paths are prioritized; otherwise
  Tier B remains retrieval-only. Tier C is retained only in structured audit output.
- Phase 4b complete: the formal runner preserves the exact path signature shown during generation
  and runs a deterministic claim-to-hop audit. It checks Tier A eligibility, node order, relation,
  per-hop PMID citation, and quote/relation agreement, then writes `claim_verification.csv`.
- Production chat and formal evaluation now exclude Tier C paths from PMID boosting and prohibit
  Tier B paths from supporting graph-derived claims.

### Token-Free Frozen Replay Result

The three-question replay used the existing `adaptive-replay-small-gpt41` top-20 path exposures and
made zero LLM/API calls. Anchors correctly identified three Q001 miRNA endpoints and the Q007
IL-17/autoimmune-disease endpoints, but no path changed rank and no 2-hop mechanism bridge existed
in the frozen exposure. This indicates that the remaining false-negative bottleneck is candidate
path availability/bridge quality, not answer-model capacity or anchor ordering within this sample.
The old GPT-4.1 answers also contained zero explicit PATH citations for Q001 and Q007 despite graph
exposure. Because the old prompt signature and saved result ID were inconsistent, this is recorded
as a baseline compliance failure rather than proof of a model ceiling. If a new signature-aligned
run still omits PATH citations, that will satisfy the predefined condition for testing a stronger
generation model.

Artifacts:

- `evaluation/formal/runs/adaptive-replay-small-anchor-offline/anchor_replay_report.md`
- `evaluation/formal/runs/adaptive-replay-small-anchor-offline/anchor_replay_summary.json`
- `evaluation/formal/runs/adaptive-replay-small-anchor-offline/anchor_path_reranking.csv`

The next step is a newly frozen graph replay that preserves at least 60 pre-gate candidates per
question. The existing frozen top-20 artifacts cannot measure rescue recall because the omitted
candidates were never saved.

### Q001 Anchor/Gate v2 Diagnostic

A new GPT-4.1 Q001 diagnostic successfully froze 60 pre-gate candidates after repairing literal
`None` annotation names in the old corpus. The valid graph contained 55 nodes and 95 edges. Candidate
tiers were A=4, B=0, C=56; all four Tier A paths were already inside the strict top-20, so rescue was
correctly not triggered. GPT-4.1 cited all four exposed path signatures. Deterministic verification
accepted three claims and rejected one quote/relation mismatch.

This result removes the current justification for upgrading GPT-4.1 on PATH-compliance grounds. It
does not test rescue recall and does not establish Hybrid superiority. See
`evaluation/formal/runs/adaptive-replay-anchor-gate-v2-gpt41/diagnostic_report.md`.
