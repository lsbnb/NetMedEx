# Controlled bridge expansion v1 development report

## Decision

This expansion still does **not** prove that Hybrid RAG is globally superior to
Text-RAG. It produced two controlled retrieval opportunities, but neither survived
the deterministic claim-safe gate. No Hybrid answer was generated for either case.

The negative results identified three general system defects and now distinguish
provider/routing failures from genuine evidence insufficiency.

## BW010: dysbiosis, serotonin, and bone loss

- Frozen corpus: 26 documents with 10 endpoint-only distractors per side.
- Endpoint leaks: zero.
- Canonical serotonin evidence existed on both sides.
- Text top-10 exposed source-side serotonin evidence but no target-side serotonin
  evidence.
- Semantic graph: 209 nodes, 297 edges; GPT-4.1 usage 63,417 tokens.

The initial gate incorrectly promoted this path to Tier A:

`dysbiosis ->[decreases] serotonin ->[treats] bone diseases`

The second hop only stated that *manipulating serotonin production* could become a
treatment strategy. A treatment relation is not a signed biological influence that
can safely be composed with the preceding decrease. The general gate now treats
`treats` as non-composable in multi-hop causal claims while retaining it as a valid
direct retrieval fact.

After zero-completion-token frozen replay:

- serotonin path: Tier B, retrieval-only;
- Tier A paths: zero;
- graph-incremental candidates: zero;
- Hybrid answer generation: skipped.

## N=3 exploratory preflight

Three candidates with AI-review scores polarity=1, canonical=1, isolation=1,
non-obviousness=3, and utility=4 received deterministic preflight only:

- BW003 / ER stress: rejected; no shared canonical mediator across both sides.
- BW006 / NLRP3 inflammasome: rejected; no shared canonical mediator across both
  sides.
- BW009 / ketone bodies: canonical bridge existed, but all six core documents were
  visible in Text top-10.

Adding endpoint-only distractors to BW009 produced a valid 26-document comparison:
all three target-side ketone/renal-protection documents were outside Text top-10.

## BW009: SGLT2 inhibition, ketone bodies, and renal protection

- Endpoint leaks: zero.
- Canonical ketone-body evidence existed on both sides.
- Exactly one bridge side was outside Text top-10.
- Semantic graph: 90 nodes, 186 edges; GPT-4.1 usage 50,794 tokens.

The first attempted graph build suffered an API network outage. All 26 semantic
extractions failed and the old runner incorrectly recorded an empty graph as a
successful result. The live runner now fails closed whenever a non-empty corpus
produces a zero-node semantic graph.

The successful graph contained the intended bridge, but the Traditional Chinese
question did not initially seed any graph nodes. Multilingual normalization now maps
the query endpoints `SGLT2 抑制劑` and `腎臟保護` to English graph labels before
endpoint/path routing.

Frozen replay recovered:

`SGLT2 inhibitor ->[increases] ketone bodies ->[ameliorates] kidney diseases`

- PMIDs: 32665641 and 41801188.
- PMID 41801188 was outside Text top-10.
- The `ameliorates` verifier vocabulary was completed so explicit `protects` and
  `improved` evidence can qualify normally.
- Hop 2 became Tier A.
- Hop 1 remained Tier B because its quote described a potentially beneficial
  substrate *shift* rather than directly supporting the extracted `increases`
  relation.

Final result:

- intended path: Tier B, retrieval-only;
- Tier A paths: zero;
- graph-incremental candidates: zero;
- Hybrid answer generation: skipped.

## General system changes

1. Multi-hop `treats` edges cannot be composed into causal claims.
2. Live semantic graph construction fails closed on a zero-node graph from a
   non-empty corpus.
3. Traditional/Simplified Chinese endpoint terms receive deterministic biomedical
   normalization before graph routing.
4. The claim verifier recognizes the allowed `ameliorates` relation through direct
   lexical evidence such as amelioration, alleviation, improvement, and protection.

## Provider-reported completion tokens

- Anthropic 10-question mediator proposals: 8,744
- OpenAI GPT-4.1 independent review: 11,610
- Gemini near-pass adjudication: 1,733
- BW010 semantic graph: 63,417
- BW009 semantic graph: 50,794
- Total for this expansion: 136,298

The failed BW009 network attempt returned no successful completions and is not
included. Frozen replays, Text retrieval screens, and deterministic preflights used
zero completion tokens. Embedding calls are not included.

## Next gate

Do not generate an answer from either candidate. The next candidate must have:

1. endpoint isolation and a canonical bridge on both sides;
2. exactly one bridge side outside Text top-k;
3. explicit relation-aligned evidence for every hop, not merely a plausible semantic
   paraphrase;
4. composable direction and polarity;
5. Tier A claim-safe status before any Text answer, Hybrid answer, or AI judging.

## Reviewed N>=3 expansion

A deterministic selector converted the existing Anthropic proposals and OpenAI
reviews into 14 previously untested mediators across eight questions. No additional
LLM proposal tokens were used.

Canonical endpoint-isolated bridges were found for five mediators:

- BW003 / IL-8
- BW005 / IL-17
- BW007 / p16INK4a
- BW009 / AMPK
- BW010 / short-chain fatty acids (SCFA)

After adding endpoint-only distractors and repeating the frozen Text top-10 screen,
only BW005/IL-17 and BW010/SCFA had exactly one bridge side withheld. Abstract-level
evidence audit rejected IL-17 before graph construction because its target record
supported treatment of a checkpoint-related psoriasis event with an IL-17 inhibitor,
not a general IL-17-to-irAE causal hop.

### BW010 / SCFA result

The 26-document semantic graph contained 166 nodes and 267 edges and used 62,841
GPT-4.1 tokens. It recovered one Tier A graph-incremental path:

`dysbiosis ->[decreases] SCFA ->[prevents] bone loss`

- PMID 35430804: decreased SCFA-producing flora and SCFA levels in a dysbiosis model.
- PMID 29302038: SCFA increased bone mass and prevented experimental bone loss.
- Both hops had aligned quotes, confidence, direction, and PMID provenance.
- PMID 35430804 was outside Text top-10.

The Text-RAG answer nevertheless generated the same semantic bridge, but attributed
the dysbiosis-to-SCFA hop to bone-side PMIDs that did not supply that hop. Anthropic's
blinded pre-generation selector therefore scored:

- Hybrid-only: 0
- Path traceable: 1
- Evidence support: 1
- Relation direction correct: 1
- Multi-document/multi-hop: 1
- Non-obviousness: 2/5
- Research utility: 3/5
- Unsupported novelty: 0

No Hybrid answer was generated. This is evidence that the graph improves explicit
cross-document provenance, but it is not evidence that Hybrid revealed a biomedical
meaning unavailable to Text-RAG.

Additional completion-token usage for this reviewed expansion:

- BW010/SCFA semantic graph: 62,841
- BW010 Text-RAG answer: 4,445
- Anthropic pre-generation selector: 2,398
- Additional total: 69,684
- Cumulative total for the full expansion described in this report: 205,982

All mediator selection, PubMed/PubTator preflight, distractor construction, Text
retrieval screening, and frozen graph replays used zero completion tokens.

## Revised next design criterion

`retrieval_incremental` and `answer_incremental` must be reported separately. A
withheld supporting PMID is insufficient to establish hidden biomedical meaning if
Text-RAG can reconstruct the same claim from familiar domain priors. Future proposal
generation should explicitly exclude textbook mediators and must pass the blinded
Hybrid-only and non-obviousness gates before Hybrid answer generation.

## Latent-hidden proposal phase

The proposal stage was tightened to require non-textbook mediators, two explicit
signed relations, a falsifiable hypothesis, and a reason Text-RAG may miss the
bridge. Query validation now also requires both concepts in every PubMed query to
carry an explicit `Title/Abstract` field qualifier.

Provider behavior and known token use:

- Gemini returned an invalid top-level schema; usage was not captured.
- OpenAI `gpt-5.6-sol` consumed 9,931 total tokens but returned no usable structured
  text, so it was not used again for this task.
- OpenAI GPT-4.1 produced proposals for five questions with 2,542 total tokens.
- Anthropic's valid strict review used 3,980 total tokens. An earlier invalid review
  used an out-of-range ordinal value; its usage was not captured and is excluded.

The AI consensus accepted three apparently non-textbook candidates: BW003/DUOX2,
BW006/HMGB1, and BW006/Galectin-3. After query correction and endpoint-only
distractors, all three satisfied the retrieval experiment: exactly one bridge side
was absent from Text top-10.

That retrieval result did **not** survive the abstract-level signed-evidence audit:

- DUOX2: the target hop was supported, but the source papers did not establish the
  proposed `CFTR dysfunction -> upregulates DUOX2` direction.
- HMGB1: broader symmetric endpoint isolation removed two source papers that already
  disclosed muscular-dystrophy inflammation. The remaining papers showed modulation,
  a burn-confounded observation, or a false-positive award announcement rather than
  the proposed first-hop causality.
- Galectin-3: DMD papers included recruitment/upregulation but also a beneficial
  regenerative role; cross-disease target papers did not establish the proposed
  chronic muscle-inflammation direction.

The preflight now reports three separate states: `retrieval_eligible`,
`evidence_eligible`, and final `graph_build_eligible`. When a signed-hop audit is
supplied, the last state fails closed unless both directional relations, their
composition, and semantic endpoint isolation all pass. In this phase the counts were
3/3 retrieval-eligible, 0/3 evidence-eligible, and 0/3 graph-build-eligible. No
semantic graph or answer was generated.

Known additional token usage was 16,453; the cumulative known total is 222,435.
PubMed/PubTator rebuilding, Text screening, signed-audit enforcement, and tests used
zero LLM completion tokens. The uncaptured Gemini and first Anthropic failures remain
explicitly excluded rather than estimated.

This negative result narrows the next search: candidate generation must be grounded
in PMID-level relation evidence before mediator novelty review. A mediator should no
longer reach graph construction merely because both endpoint-isolated document sets
mention the same canonical entity.

### Automated PMID-level evidence gate

The abstract audit was then implemented as a reusable, provider-independent stage.
It compacts each abstract while preserving its background and results/conclusion
regions, validates that cited PMIDs belong to the frozen corpus, and emits a
screen-compatible audit. Anthropic independently reviewed all three candidates with
5,914 input and 585 output tokens (6,499 total) and also passed 0/3. This confirms the
negative audit without a human expert and raises the cumulative known total to
228,934 tokens. Because every candidate failed, a second evidence reviewer and all
semantic graph builds were skipped.
