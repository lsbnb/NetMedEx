# Hybrid Hidden Biomedical Meaning — Development v2 Report

Date: 2026-08-09  
Status: development analysis; not an independent superiority test

## Objective

Improve Hybrid RAG so the knowledge graph gives users evidence-grounded biomedical meaning that
is not already available from the same frozen corpus through traditional Text-RAG.

## Design

- Source development batch: 10 previously frozen questions.
- Paid graph rebuild was restricted to Q008, Q011, and Q037 because they were graph-oriented and
  had cached paths after deterministic screening.
- Generator: OpenAI GPT-4.1 for both Hybrid and Text arms.
- Same frozen corpus and top-k for both arms.
- Hidden-claim judges: Claude Sonnet 4.6 and Gemini 3.1 Pro Preview, blinded to system identity.
- Consensus required both judges to agree on every binary validity condition.
- No human-expert validation is claimed.

## Systemic Repairs Made During the Batch

1. Preserve all graph-node mention aliases instead of only the most frequent display name.
2. Group duplicate ontology/species node IDs that match the same query span.
3. Treat trailing `in/within/among ...` entities as context rather than relation targets.
4. Prefer the longest biomedical phrase over nested generic fragments.
5. Reapply the live strict gate during frozen-exposure replay.
6. Add bounded mechanistic diversity expansion: up to three lower-ranked Tier A two-hop paths
   with novel bridges may replace Tier B/C paths, without replacing an existing Tier A path.
7. Make claim verification alias-aware and audit every PATH reference on a line.
8. Add a per-process provider-reported chat-token checkpoint.

These rules are global and contain no question-ID-specific branches.

## Retrieval and Gate Outcome

| Question | Tier A paths exposed | Notable bridges |
|---|---:|---|
| Q008 | 4 | cystic fibrosis, NF-kappaB, beta-catenin |
| Q011 | 4 | AMPK (two independently supported paths) |
| Q037 | 5 | chronic inflammation, fibrosis, liver fibrosis |

The diversity expansion recovered Q008 paths ranked 44 and 59 and Q011 paths ranked 41 and 43
from the already-scored 60-candidate pool. It required no additional semantic-search or LLM call.

## Deterministic and Multi-model Results

- Final paired-answer generation: 3/3 questions completed.
- Deterministically supported candidate claims sent to judges: 9.
- Consensus path traceability/evidence/direction: 8/9 (88.9%).
- Consensus multi-document or multi-hop: 6/9 (66.7%).
- Consensus unsupported novelty: 0/9 (0%).
- Consensus Hybrid-only claims: 0/9 (0%).
- Validated hidden claims: 0/9.

One Q008 NF-kappaB candidate received median non-obviousness 4.0 and research utility 4.5, but both
judges found an equivalent mechanism in the Text-RAG answer. It therefore cannot be counted as
Hybrid-only hidden information.

## Interpretation

The v2 changes improved graph-path relevance, bridge diversity, citation traceability, and safety.
They did **not** yet demonstrate incremental hidden information over Text-RAG. The current
bottleneck is no longer simply path availability: the system lacks an incremental-value selector
that distinguishes a good graph path from a graph path that merely restates information already
visible in the text answer/context.

The correct claim at this checkpoint is:

> Hybrid RAG now provides more structured and traceable mechanistic paths, but this three-question
> development pilot found no validated Hybrid-only biomedical claim beyond Text-RAG.

## Next Global Improvement

Add a contrastive incremental-information layer after Tier A gating:

1. Separate `graph-confirmed` claims from `graph-incremental` claims.
2. Compare each Tier A path's bridge and relation tuple against the Text-RAG context/answer.
3. Mark a claim `graph-incremental` only when its supported bridge/relation is absent from the text
   evidence synthesis; document novelty alone is insufficient.
4. Prefer cross-document Tier A paths with a novel bridge, while retaining ordinary Tier A paths
   as traceability aids rather than calling them hidden information.
5. Freeze 10 new bridge-withheld questions before generation and validate on a separate holdout.

## Provider-reported Token Accounting

| Stage | Tokens |
|---|---:|
| Three-question graph-only rebuild | 100,516 |
| Initial two-question paired diagnostic | 19,889 |
| Final three-question diversity paired generation | 30,687 |
| Claude hidden-claim judge | 13,566 |
| Gemini hidden-claim judge | 16,635 |
| **Total provider-reported chat tokens** | **181,293** |

Embedding usage is not included in the chat-completion counters.
