# Controlled bridge pilot v3 development report

## Decision

The pilot does **not** validate the claim that Hybrid RAG is superior to Text-RAG.
It produced one traceable Hybrid-only candidate, but the independent pre-generation
selector rejected that candidate for inconsistent causal polarity. No Hybrid answer
was generated after the rejection.

## Controlled corpus

- Question: BW008, chronic hepatitis B infection to hepatocellular carcinoma.
- Both systems used the same frozen 15-document corpus.
- No article contains both endpoint ontology identifiers.
- Mediators were used only for corpus construction and were absent from the system
  question.
- Target-side bridge documents were forbidden from mentioning HBV or hepatitis B.
- STAT1 source evidence was present in Text top-10; all STAT1 target-side documents
  were outside Text top-10.
- Cirrhosis remained a positive confirmation control visible to Text-RAG.

## Retrieval result before polarity correction

The bounded four-hop replay recovered this fully evidenced path:

`chronic hepatitis B -> HBV -> STAT1 -> HKDC1 -> hepatocellular carcinoma`

- Relations: `associated_with`, `inhibits`, `binds_to`, `promotes`.
- PMIDs: 24574713, 30842274, 38351096.
- PMID 38351096 was outside Text top-10.
- The deterministic exposure classifier marked it graph-incremental.

The Text-RAG answer mentioned HBV-related STAT1 dysregulation but did not contain
the STAT1-HKDC1-HCC immune-evasion link.

## Independent selector

Anthropic Claude Sonnet 4.6 scored the candidate:

- Hybrid-only: 1
- Path traceable: 1
- Evidence support: 1
- Multi-document or multi-hop: 1
- Non-obviousness: 4/5
- Research utility: 4/5
- Relation direction correct: 0
- Unsupported novelty: 1

The rejected inference combined HBV inhibition of STAT1 with an HCC mechanism in
which HKDC1 activates STAT1/PD-L1. The individual edges were supported, but their
composition did not form a coherent forward mechanism.

## System changes made

1. Added endpoint-isolated controlled-corpus construction with lexical and ontology
   endpoint leak checks and canonical mediator IDs.
2. Added a broader target-side source-leak rule for cross-domain bridge construction.
3. Fixed word-order-insensitive bridge visibility (`hepatitis chronic` versus
   `chronic hepatitis`).
4. Added adaptive bounded four-hop endpoint search for mechanism/hypothesis tasks.
5. Preserved a bounded endpoint path tail so complete low-frequency mechanisms are
   not truncated before evidence gating.
6. Allowed viral pathogen Species nodes while retaining the exclusion of general
   organism/model Species nodes.
7. Added long-path polarity gating: an unresolved odd number of negative causal
   relations is retrieval-only unless the question explicitly requests an
   inhibitory/protective mechanism.

The relevant regression suite passes: 83 tests.

## Provider-reported completion tokens used in this phase

- Initial BW008 union path selector: 3,740
- Controlled pilot v1 semantic graph: 36,795
- Controlled pilot v3 semantic graph: 36,036
- Controlled pilot v3 Text-RAG answer: 4,844
- Controlled pilot v3 pre-generation selector: 3,028
- Total: 84,443

Embedding calls are not included in these completion-token counters.

## Next expansion gate

Before scaling to ten questions, each proposed mediator must satisfy all of the
following without answer generation:

1. endpoint-isolated documents exist on both sides with the same canonical entity;
2. at least one required hop is outside Text top-k;
3. every graph hop has a supporting quote and PMID;
4. directional edges follow traversal direction;
5. the composed path has resolvable causal polarity;
6. an independent AI selector scores Hybrid-only=1, non-obviousness >=4, research
   utility >=4, and unsupported novelty=0.

Only candidates passing this gate should receive Hybrid answer generation and two
independent final AI judges.
