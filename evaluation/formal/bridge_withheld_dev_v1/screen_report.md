# Bridge-withheld development screen v1

## Result

This 10-question batch is not suitable as-is for testing whether Hybrid RAG
retrieves hidden biomedical information beyond Text-RAG. Only BW003 and BW008
pass the pre-generation eligibility audit: both source and target are represented
as graph nodes, and their corpora contain documents outside Text-RAG top-10.

Six questions have no documents outside Text-RAG top-10. Three lack a graph-
representable source and three lack a graph-representable target (categories
overlap). These are structural exclusions, not negative evidence against Hybrid
RAG.

## Paid large-corpus screen

BW002 and BW005 were screened before the endpoint audit was added. The run used
73,300 provider-reported tokens in total:

- BW002: 33,648 tokens; 59 nodes, 81 edges, one exposed one-hop path, and zero
  graph-incremental candidates.
- BW005: 39,652 tokens; 88 nodes, 177 edges, no exposed paths, and zero graph-
  incremental candidates.

The BW002 path connected curcumin to pyroptosis even though the requested target
was apoptosis. This exposed a general semantic endpoint-substitution bug. The
strict gate now requires lexical/acronym compatibility for semantic endpoint
fallback and requires both endpoints of an explicit bridge question to resolve.
Therefore this path would now be rejected instead of treated as Tier A.

## Decision

No paired answer generation or LLM judging is warranted for this batch. The next
development batch should be constructed with pre-generation constraints:

1. both endpoints must be graph-representable;
2. corpus size should be at least 30 documents when Text-RAG uses top-10;
3. a frozen graph must contain at least one claim-safe two-hop path;
4. at least one supporting PMID must lie outside Text-RAG top-10;
5. mediator names must remain withheld from the question.

Only candidates passing all five rules should consume answer-generation and
multi-provider judge tokens.
