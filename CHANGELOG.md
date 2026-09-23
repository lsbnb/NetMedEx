# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.3] - 2026-09-22

### Fixed & Hardened

- **Follow-up Retrieval Had No Memory of the Previous Reply's Citations**: `send_message`'s normal (non-strict) flow already re-searches the full index fresh on every turn -- never restricted to a prior turn's results, that hard restriction is a separate, opt-in mode (`_answer_with_pmid_grounding`'s Tier 1, gated by `strict_pmid_grounding`, off by default). But `preferred_pmids` (the ranking-boost set passed into `AbstractRAG.search()`/`get_context()`) started empty each turn and was populated only from *that turn's own* fresh 2-hop graph paths, so a still-relevant PMID the previous reply had cited had no path back into this turn's ranking unless this turn's own graph traversal happened to rediscover it independently -- the LLM's memory of the conversation text was the only thing carrying it forward. `preferred_pmids` now starts as `self._last_cited_pmids()` (the previous reply's citations) before this turn's own graph-derived PMIDs are unioned in. Still purely a ranking boost, not a filter: `AbstractRAG.search()` only ever multiplies a preferred PMID's score by 1.5x among candidates the dense/sparse arms already returned for the current query over the full index -- it never force-includes one they didn't surface, so a prior PMID that has become irrelevant to the new question simply gets no boost, exactly as before this change. Added regression test `test_followup_turn_boosts_previous_citations_without_restricting_the_index` (`tests/test_rag_chat.py`).

### Changed

- **Article-Fetch Defaults Changed to 50 Articles / Relevance Sort**: "Max Articles" defaulted to 30 and "Sort" defaulted to Recency (`webapp/components/advanced_settings.py`, `webapp/components/sidebar.py`), together capping AI Search / Analyze Selection to the 30 *most recent* matching articles regardless of how many actually matched -- a narrow, recency-biased sample for a step meant to build a representative knowledge network. Diagnosed live from a real user report ("the reply never mentions any miRNA" for a query about resveratrol/microRNA/Alzheimer's): the query correctly matched 2,492 articles (query translation itself was fine), but only the 30 most recent were fetched, and by chance none of that batch's articles mentioned any specific microRNA at all -- confirmed by grepping the actual fetched `corpus.pubtator` for `mir-`/`microrna`/`mirna` and finding zero hits anywhere, including in the 141 PubTator-tagged Gene entities. Not a graph-retrieval or ranking bug (every miRNA-visibility fix from v1.5.19 onward operates on entities already present in the fetched corpus; none can surface an entity that was never fetched) -- just too small and too recency-biased a default sample for a broad mechanistic question. New defaults: 50 articles, sorted by Relevance (also now matching the REST API's existing `sort` default in `fastapi_bridge.py`, which was already `"score"`). CLI defaults (`--sort date`, `--max_articles 1000`) are unchanged -- that entry point targets batch/automated corpus-building, a different use case with its own already-large default.

## [1.7.2] - 2026-09-22

### Fixed & Hardened

- **Concurrent Chat-Session Rebuilds After a Server Restart Could Both Fail**: A gunicorn graceful reload (SIGHUP) clears the in-process `_sessions` cache (`chat_callbacks.py`); the next message for an existing browser session correctly rebuilds it from the saved graph file via `_rebuild_chat_session_from_graph`, which constructs a fresh `AbstractRAG`/ChromaDB `EphemeralClient`. Observed live immediately after such a restart: the main chat panel and the expanded chat modal fired two rebuild requests for the same session within the same second, and both failed -- `'RustBindingsAPI' object has no attribute 'bindings'` followed immediately by `'ephemeral'` -- surfacing "Session expired and the chat context could not be rebuilt" to the user even though the on-disk graph and chat history were intact. ChromaDB's ephemeral-client machinery is not safe to construct concurrently for the same logical session. Added a module-level `_session_rebuild_lock` around the existing "rebuild if missing" block, with a re-check of `_sessions` immediately inside the lock (double-checked locking): a second near-simultaneous request for the same graph path now waits for the first rebuild to finish and reuses its result instead of racing it. One process-wide lock rather than one per graph path -- rebuilds are rare (only right after a restart), so briefly serializing rebuilds of two *different* sessions is a non-issue, and a per-path lock registry would need its own guard against concurrent creation anyway.

## [1.7.1] - 2026-09-22

### Fixed & Hardened

- **Query Translation Failure Was Invisible to the User**: `send_message`'s "English Intermediary" (translates a non-English/CJK query to English before any retrieval runs, since every dense/sparse/graph retrieval call downstream consumes only the translated `search_query`) degraded silently on failure: `LLMClient.translate_to_english` (`webapp/llm.py`) returned the untranslated original both when no LLM client was configured and when the translation call raised, with only the latter logged, and `chat.py`'s caller logged a warning for the "client doesn't support this method" case but never surfaced it beyond the log. Measured impact when this fires: on 3 real Chinese conceptual questions, nDCG@10 dropped from 0.393 (translated) to 0.230 (untranslated) -- roughly halved, with one case (`MiniLM dense-only`) going from 0.042 to 0.888 when translation succeeded. A translation outage was indistinguishable from an ordinary answer that just happened to retrieve less well.
  - `LLMClient.translate_to_english` now sets `self.last_translation_status` to `"ok"` (the call completed, whether or not it changed the text -- an already-English query is a legitimate no-op), `"unavailable"` (no client configured), or `"error"` (the call raised), and logs a warning for the previously-silent "unavailable" case.
  - `ChatSession.send_message` checks this status (and the pre-existing "client lacks `translate_to_english`" case) to compute a `translation_degraded` flag, threaded through `_finalize_chat_turn` and both strict-PMID-grounding tiers so it reaches every return path that could have retrieved on an untranslated query, not just the normal single-tier flow.
  - Surfaced in the webapp (`chat_callbacks.py`) as an inline ⚠️ caveat appended to the answer, following the same pattern as the existing "rebuild with Semantic Analysis" nudge (`suggest_semantic_edge_method`) -- a warning in the logs is not something a user is expected to go looking for.
  - Added regression tests: `tests/test_llm_usage.py` (the three `last_translation_status` outcomes) and `tests/test_rag_chat.py::TestTranslationDegradedVisibility` (the flag firing for a missing method and a reported "unavailable" status, and *not* firing on a successful translation or when translation was never needed).

### Verified

- **Preferred-PMID Boost (1.5x) Re-Calibrated on a Corpus That Can Actually Discriminate**: `evaluation/calibrate_hybrid_boost.py`'s prior finding that the boost multiplier is statistically insensitive was measured against `evaluation/formal_v2/qrels.csv`'s per-question corpora, which have a median of ~15 abstracts and are judged almost end-to-end (462 "highly relevant" vs. 54 "not relevant" labels across all 50 questions) -- retrieving top-10 out of ~15 mostly-relevant abstracts pushes nDCG@10 toward 1.0 regardless of ranking rule, so "insensitive" may have meant "no headroom to be sensitive on," not "genuinely doesn't matter." Added `evaluation/calibrate_hybrid_boost_pooled.py`, which re-runs the identical grid search and paired-bootstrap methodology (reusing `calibrate_hybrid_boost`'s `_fused_score`/`score_boost` so both scripts calibrate against the exact same live RRF scoring rule) against all 50 questions' `corpus.pubtator` files pooled into one ~518-abstract corpus, so each question's relevant abstracts sit among ~500 distractors instead of a handful. Reused the graph-derived `preferred_pmids` already cached in a prior calibration run's output (`is_preferred` is a property of the question's own graph, not of which corpus is then searched, so this needed zero new LLM spend) rather than rebuilding all 50 graphs. Result on the 11 questions with a non-empty preferred set: the grid still varies by only 0.006 nDCG@10 between boost 1.0 and 3.0, and 1.4x (the empirical optimum) vs. the current 1.5x differs by 0.0002 (95% bootstrap CI [-0.0012, +0.0016], sign-test p=1.0) -- confirming the boost genuinely doesn't matter much under RRF fusion, this time on a corpus with real discriminating power rather than one with none. No change to the shipped 1.5x constant.

## [1.7.0] - 2026-09-19

### Added

- **Hybrid Sparse + Dense Text Retrieval (BM25 + Reciprocal Rank Fusion)**: Chat's text arm was pure dense vector search over ChromaDB's default general-purpose embeddings, which encode "this passage is about microRNAs" but cannot separate biomedical symbols differing by a digit. Measured on a real 200-abstract HCV/liver-cancer corpus: a `miR-155` question put 1 of the 7 discussing abstracts in the top 10 (a *miR-122* review ranked 2nd), and `miR-34a` returned none of its 7.
  - `_BM25Index` (`rag.py`) implements BM25-Okapi in-repo rather than depending on `rank_bm25`, so existing Docker/pip installs keep working without a new dependency and retrieval stays reproducible across environments.
  - `_tokenize_biomedical` emits a canonical `mir<number>` token per miRNA surface form, so `miR-155` / `miRNA-155` / `microRNA-155` / `hsa-miR-21-5p` share a matching token -- the same surface-form mismatch that made the graph arm miss this entity (see the alias fix below). Distinct miRNAs stay distinct (`miR-129` vs `miR-1290`) and ordinary words ("mirror") produce no identifier token.
  - `search()` now fuses both arms by RRF. Two fusion details were required to make it actually work, each found by measurement: (a) a document an arm did not return is ranked just past that arm's tail instead of contributing nothing, because skipping it made mere presence in both arms worth ~2x the best possible single-arm score -- that alone sank a query whose 7 relevant abstracts BM25 had ranked 1-7 to a single hit; (b) `_RRF_K` is 10, not the paper's 60, which on a few-hundred-document corpus flattens the rank curve so far that a top-1 hit barely outscores a mid-ranked one.
  - Sparse-arm weighting is query-adaptive (`_BM25Index.has_exact_identifier`): tripled only when the query names an identifier the corpus knows (letters+digits: `mir155`, `tp53`, `c797s`). Applying it unconditionally matched the entity gains but disturbed conceptual-query rankings far more (overlap@8 with the dense baseline 0.656 -> 0.344), so it is applied only where the dense arm is the weaker ranker.
  - Measured end-to-end through `search()` across 4 entity questions: mean P@8 0.188 -> 0.844, mean R@8 0.106 -> 0.637; the original failing `miR-155` case went from 1 hit to all 7 relevant abstracts (R@8 = 1.00). `NETMEDEX_DISABLE_BM25=1` restores dense-only retrieval for A/B comparison.
  - `search_with_components()` now also reports both arms' ranks and the fusion constants, and `evaluation/calibrate_hybrid_boost.py` scores through a shared `_fused_score()`: calibrating the preferred-PMID boost against the previous `similarity * weight * boost` formula would otherwise tune a scoring rule the live path no longer uses.

### Fixed & Hardened

- **Entity Unreachable When Its Display Name Differs From the Form Users Type**: `GraphRetriever._build_node_index` indexed each node's ID and display name but not its aliases. A node's display name is whichever surface form the source abstract used, so the miR-155 node was stored as `mirna-155` while `mir-155` sat unused in its own alias set -- making the standard form unmatchable. Measured before the fix: "What is the role of miR-155 in HCV-related liver cancer?" found zero miR-155 nodes, contributed zero miR-155 PMIDs to `preferred_pmids`, and retrieved 0 of 8. Aliases are now indexed in a second pass (minimum 3 characters, since matching is plain substring containment; never overriding another node's primary name). `_extract_query_anchors` was already alias-aware, so this removes an inconsistency rather than introducing a new concept.
- **A Named miRNA Was Read as the Whole Family**: category expansion triggered on a plain `"mirna" in query` substring test, so "miRNA-155" -- one specific entity -- expanded to every miR-* node (~120 in the live corpus), diluting the asked-about entity to 1-in-120; the standard "miR-155" spelling meanwhile matched nothing at all, so neither phrasing worked. Added `mentions_category_generically` (`utils.py`), which fires only when a trigger is not immediately followed by an identifying number, and applied it at all three expansion sites (`find_relevant_nodes`, `_extract_query_anchors`, `PubTatorGraphBuilder.find_query_anchor_nodes`), also removing a duplicated trigger set. Verified both directions: "miRNA-155"/"microRNA-155"/"miR-155" now resolve to the single entity, while "Which microRNAs are linked to liver cancer?" still expands to all 117.

## [1.6.0] - 2026-09-19

### Added

- **Strict Citation Grounding for Follow-up Questions**: New optional Advanced Settings toggle (`strict-pmid-grounding-toggle`) implementing a user-designed two-tier "Hybrid Knowledge Hierarchy" retrieval policy for follow-up questions, addressing the observation that every Chat turn -- including follow-ups -- previously re-searched the full index and graph fresh from the current question's text alone, with no way to keep a multi-turn conversation's citations consistent or auditable.
  - **Tier 1 (核心證據圈 / core evidence circle)**: `ChatSession._answer_with_pmid_grounding` (`chat.py`) builds text context directly from `self.rag.documents[pmid]` for each PMID cited in the immediately preceding assistant reply (`_last_cited_pmids`), and a graph context from `_build_pmid_restricted_subgraph` -- a strict attribute filter (edges/nodes kept only if their recorded PMID is in the previous-reply set) rather than a neighbor expansion, so a node reachable only through a differently-sourced edge is never pulled in. The LLM is instructed to answer using only this restricted context, or to respond with an exact sentinel token (`_PMID_GROUNDING_SENTINEL`) if it's insufficient.
    - **Fixed during design review**: an edge co-cited by both a restricted and a non-restricted PMID (e.g. `relations={"1": {...}, "2": {...}}` where only PMID 1 is in the previous reply) initially passed the any-match keep/discard gate with its *entire* original data intact -- meaning PMID 2's own relation, evidence quote, and confidence could still be selected and cited by `_select_edge_support`, silently leaking a non-restricted source into a "restricted" answer and defeating the grounding guarantee. `_build_pmid_restricted_subgraph` now also trims each kept edge's PMID-keyed fields (`relations`, `confidences`, `evidences`, `mechanism_events`) down to the intersection with the restriction set, verified with a dedicated regression test (`test_restricted_subgraph_trims_non_restricted_pmid_out_of_shared_edge`) and confirmed live end-to-end afterward.
  - **Tier 2 (索引總庫圈 / index-wide circle, fallback)**: entered only when tier 1's context is empty or the sentinel fires; reuses the normal unrestricted retrieval, and the code -- not the LLM -- deterministically diffs cited PMIDs against the tier-1 set to append the required disclosure sentence for any newly-cited PMID (`_PMID_GROUNDING_DISCLOSURE_TEMPLATE`). If tier 2 is also empty, a fixed refusal string (`_PMID_GROUNDING_REFUSAL`) is returned directly, bypassing the LLM entirely so the wording can never be paraphrased away -- the same bypass-for-determinism pattern already used by `_build_entity_listing_response`.
  - Off by default; has no effect on a session's first substantive question (nothing to ground on yet), on meta-instructions, on internal bootstrap calls, or when `focus_nodes` is explicitly set. Threaded through the webapp (new toggle in `advanced_settings.py`, wired in `chat_callbacks.py`), the FastAPI bridge (`BridgeConfig.strict_pmid_grounding`, `chat_bridge.py`), and the REST API (`SessionConfigModel.strict_pmid_grounding`, `fastapi_bridge.py`).
  - Refactored `send_message`'s LLM-invocation block (provider-specific token budgets, timeouts, three-way SDK fallback) into `_call_llm_for_chat_completion`, and its citation-parsing/history-persistence tail into `_finalize_chat_turn`, so both new tiers and the normal single-tier flow share identical behavior rather than risking drift between duplicated copies.
  - Verified live end-to-end across a real 3-turn conversation (HCV/HCC/miRNA topic): a follow-up answerable from the first reply's own citations stayed within them (tier 1, one LLM call); a follow-up asking about a different, previously-uncited miRNA correctly widened to the full index and appended the exact required disclosure sentence naming the new PMID (tier 2, two LLM calls). Added regression tests (`tests/test_rag_chat.py`, `TestStrictPmidGrounding`) covering the first-turn no-op, tier-1 success without reaching tier 2, tier-1-sentinel fallback with disclosure, both-tiers-empty deterministic refusal with zero LLM calls, and the restricted-subgraph's neighbor-exclusion behavior.

## [1.5.22] - 2026-09-19

### Fixed & Hardened

- **Listing-Style Questions with the Entity Noun Between Trigger Words Not Recognized**: `_detect_entity_listing_request` (`chat.py`) matched trigger phrases as fixed literal substrings ("which are", "有哪些"), which only fires when the entity name sits *outside* the trigger phrase. A very natural phrasing like "哪一些miRNA與HCV引發的肝癌有關" (which miRNAs are related to HCV-induced liver cancer) -- and its literal English equivalent "Which miRNAs are associated with..." -- has the entity noun sitting *between* the two halves of the trigger ("哪一些...有關" / "which...are"), so neither matched and the question fell through to the normal LLM reasoning path instead of the deterministic full-entity-list response. Found live while verifying the v1.5.19-21 fixes end-to-end: a real HCV/liver-cancer graph with 109 real miRNA nodes surfaced only 8 of them via the normal path's top-k retrieval, versus the intended behavior of all 109 (with PMIDs each, plus the v1.5.18 completeness caveat for semantic-built graphs) via the listing path. Added "哪些"/"哪一些" as direct Chinese triggers and a `\bwhich\b.*\bare\b` regex for the equivalent English phrasing. Added regression test `test_entity_listing_query_recognizes_which_x_are_related_phrasing` (`tests/test_rag_chat.py`) covering both languages.

## [1.5.21] - 2026-09-18

### Fixed & Hardened

- **AI Search Query Translation Could Silently Drop Other Named Biological Families**: Following the v1.5.19/20 investigation into category-matched entities (miRNA, lncRNA) getting diluted in graph retrieval, audited the upstream `translate_query_to_boolean` prompt (`webapp/llm.py`) for the same class of risk one layer earlier -- before the PubMed search even runs. Its "MIRNA / NON-CODING RNA RULE" explicitly protected miRNA/microRNA/lncRNA from the "extract only 2-3 specific entities, drop generic mechanism words" simplification rule, but no equivalent protection existed for other narrow, well-known biological families a user might name generically: interleukin/cytokine, chemokine, circRNA, piRNA/siRNA, Toll-like receptor, matrix metalloproteinase, or drug classes with INN naming conventions (monoclonal antibody, kinase inhibitor, statin). A query naming one of these risked having it silently stripped as a "generic mechanism word" before search, making the term unrecoverable by any downstream graph-retrieval fix. Generalized the rule ("NAMED BIOLOGICAL FAMILY RULE") to cover all of these explicitly, with new examples. Live-verified: "How does curcumin reduce inflammation via an interleukin in arthritis?", "...via a chemokine...", and "...via circRNA..." all now translate with the family term preserved as an explicit `(@GENE OR "term")` OR-expansion, matching the existing miRNA/lncRNA pattern.

## [1.5.20] - 2026-09-18

### Added

- **lncRNA Category Detection (`is_lncrna_node`, `LNCRNA_QUERY_TRIGGERS` in `utils.py`)**: Extends the v1.5.19 category-matching fix to long non-coding RNAs. Unlike miRNA (a clean `mir-\d+`/`let-7` naming convention), lncRNA names have no single reliable pattern -- `MALAT1`, `GAS5`, `H19`, `PVT1` are indistinguishable from ordinary protein-coding gene symbols by name alone, and PubTator3 tags both under the same generic `Gene` type. Detection combines a curated list of well-known named lncRNAs with the `LINC*`/`SNHG*` prefixes and `-AS<n>` antisense-RNA suffix, which are reasonably specific to this RNA family; necessarily incomplete for lncRNAs matching neither the list nor these patterns. Wired into the same three points already extended for miRNA/SNP: `GraphRetriever.find_relevant_nodes`, `_extract_query_anchors`'s `mechanism_ids` expansion, and `PubTatorGraphBuilder.find_query_anchor_nodes` (`graph.py`) -- so a generic "lncRNA" query mention gets the same start-node inclusion, anchor-bonus scoring, gate-alignment credit, and render-time/build-time protection that "microRNA" already had. Verified live on a different real topic (curcumin/apoptosis/breast cancer, distinct from the miRNA reproduction): Chat's answer now names two specific lncRNAs (`LINC00691`, `H19`) with real PMID citations that were absent before this fix. Added regression tests: direct `is_lncrna_node` pattern coverage plus a synthetic dilution reproduction (`test_lncrna_category_entity_not_silently_dropped_by_generic_hub_edges`, `tests/test_semantic_prompt.py`) mirroring the miRNA one.

## [1.5.19] - 2026-09-18

### Fixed & Hardened

- **Category-Matched Query Entities Silently Excluded from Chat's Retrieved Context**: Reported and live-reproduced: "Resveratrol how does it regulate Neuroinflammation via microRNA to protect against Alzheimer's Disease" built a graph containing 11 real, evidenced miRNA nodes (e.g. `miR-155 —[promotes]→ neuroinflammation`, PMID:35008513, confidence 0.9) that survived graph construction correctly (v1.5.16/17's fixes both held), yet Chat's answer never mentioned any specific miRNA -- only a generic, unsupported "Resveratrol may regulate microRNA" guess.
  - Root cause, isolated by directly instrumenting `GraphRetriever`: `find_relevant_nodes` correctly includes all 11 miRNA nodes as retrieval-worthy (category expansion for "microRNA" works there), but `_extract_query_anchors` -- which drives both the anchor-bonus score boost and `_classify_path_gate`'s endpoint-alignment check -- matches query anchors purely by literal node name/alias substring. A generic category mention ("microRNA") never literally names any specific node, so none of the 11 miRNA nodes' edges ever received anchor credit anywhere in scoring or gating, and were systematically outranked by the numerous edges of literally-query-matching hub entities (Resveratrol, Alzheimer's disease) backed by far more corroborating literature -- `miR-155`'s real, cited edge (score 0.65) never even entered the top-60 candidate pool.
  - Fixed in three places: `_score_path_anchors` and `_classify_path_gate` (`graph_rag.py`) now also credit a path whose start/end node is a "novel" category-expanded match (one not already the literal source/target) -- excluding the already-known source/target from that credit was necessary to avoid re-triggering on the trivial always-present start node, and explicit "connect A to B" bridge queries are excluded so an unresolved named endpoint still stays a hard discard. `_select_gated_candidate_paths` gained a small, bounded rescue (`mechanism_diversity_limit`, default 2) for a category-matched entity's retrieval-safe (tier A or B) fact that still ranks just outside the top-20 cut even after the scoring fix -- checking `retrieval_safe` rather than `claim_safe` alone matters here, since a specific miRNA's evidence quote often doesn't verbatim-align with the extracted relation closely enough for tier A, landing it at tier B ("RETRIEVAL-ONLY"), exactly the epistemic status Layer 2's association/speculative-inference rules are designed for.
  - Verified live end-to-end with the exact reproduction: Chat's answer now cites `miR-155 —[promotes]→ neuroinflammation` directly in Layer 1 and builds a concrete, correctly-hedged Layer 3 causal hypothesis naming it specifically (confidence correctly capped at 0.40 given the single-study, tier-B evidence). Added a synthetic regression test (`test_category_expanded_entity_not_silently_dropped_by_generic_hub_edges`, `tests/test_semantic_prompt.py`) reproducing the dilution pattern with 30 noise edges.

## [1.5.18] - 2026-09-18

### Fixed & Hardened

- **Entity-Listing Chat Answers Overclaimed Completeness**: `_build_entity_listing_response` (`netmedex/chat.py`), used for questions like "list all miRNAs linked to X," compiles its answer purely from surviving graph nodes and told the user this was "a complete list" regardless of how the graph was built. With `edge_method` `semantic` or `relation` (see v1.5.17), an entity mentioned in the abstracts but never assigned an extracted relationship is removed as an isolated node during the build itself, so the claim was often inaccurate. The response now checks `graph.graph["edge_method"]` and, for `semantic`/`relation` graphs, replaces the completeness claim with a caveat that entities without an extracted relationship may be missing from the list; `co-occurrence` graphs (which connect every mentioned entity pair, so no such gap exists) keep the original wording.
- **Hardened Sub-Network PMID Selection Against Malformed Elements**: The Cytoscape-selection-to-PMID-filter logic in `webapp/callbacks/chat_callbacks.py` (used when a user manually selects a sub-network before chatting) now guards every edge/node dict access with `isinstance` checks and tolerates `None`/non-list `pmids` values, instead of assuming every selected element is always a well-formed dict.

## [1.5.17] - 2026-09-18

### Fixed & Hardened

- **Query-Relevant Entities Missing Entirely When Built with Semantic Analysis (LLM)**: Reported live: "Resveratrol how does it regulate Neuroinflammation via microRNA to protect against Alzheimer's Disease" produced a graph with **zero** miRNA nodes, even though PubTator3's own annotations correctly tagged 12 distinct miRNAs (mir-155, mir-214, mir-134, etc.) across the retrieved articles. Root cause, confirmed by rebuilding this exact query end-to-end: "Semantic Analysis (LLM)" (the app's default edge method) has the LLM extract only a handful of the relationships it judges most meaningful per article (measured: 12 and 2 relationships from 24 and 28 mentioned entities, respectively) rather than an edge for every mentioned entity. Any entity the LLM doesn't pick -- miRNAs here, but this affects any entity type -- ends up with zero edges and is stripped as an isolated node **during the build itself** (`PubTatorGraphBuilder.build`), before the graph is even saved; this is a different failure mode from the v1.5.16 rendering-cap fix, which only helps entities that already have a (low-weight) edge. Added `PubTatorGraphBuilder._add_anchor_cooccurrence_fallback_edges` (`netmedex/graph.py`): after semantic edges are added, any query-anchor entity (via the existing `find_query_anchor_nodes`) still at degree 0 gets a plain co-mention edge to another anchor entity that shares a source article with it, so it survives the isolated-node cleanup. These fallback edges are tagged `type="node"` (the existing dashed/undirected style) specifically so they render as "co-mentioned" rather than being confused with a real LLM-extracted directional claim. `add_collection` gained an optional `query` parameter (threaded through from `webapp/callbacks/pipeline.py`) to make the original search query available at build time. Verified live: re-running the exact reproduction with the fix applied, all 9 previously-isolated miRNA nodes gained a fallback edge (degree 0 -> 1) and the 2 nodes the LLM did connect were untouched.
- **Anchor Protection Generalized to SNPs / Genomic Variants**: `find_query_anchor_nodes` now also expands generic query terms ("SNP", "polymorphism", "變異位點", etc.) to every `rs`-prefixed variant/mutation-type node (`is_snp_node`, `netmedex/utils.py`), and matches on node aliases in addition to the primary name -- mirroring the existing miRNA category expansion for the same class of dilution problem.

## [1.5.16] - 2026-09-18

### Fixed & Hardened

- **Low-Frequency Query Entities (e.g. specific miRNAs) No Longer Silently Pruned from the Visualized Graph**: Reported live: a query containing "microRNA" built a graph where a dominant chemical/disease pair (e.g. resveratrol / Alzheimer's, co-occurring in all 50 retrieved articles) crowded out `miR-124`, which co-occurred in only 1-2 articles and had edge weight 1. Root cause: `_remove_edges_by_rank` (`netmedex/graph.py`), which caps rendering at `MAX_INTERACTIVE_EDGES = 3000` edges to keep the browser responsive, ranked purely by global edge weight with no notion of relevance to the original search query -- so miR-124's single low-weight edge was cut, and the now-degree-0 node was then swept by `_remove_isolated_nodes`. Added `PubTatorGraphBuilder.find_query_anchor_nodes` (exact name match against the original build query, `graph.graph["query"]`, plus category expansion for generic terms like "microRNA" via the shared `is_mirna_node` helper) and threaded it through both automatic safety caps in `webapp/callbacks/graph_utils.py`'s `rebuild_graph` -- `_remove_edges_by_rank`'s edge budget and the `MAX_INTERACTIVE_NODES = 1500` node cap -- so query-relevant nodes/edges get first claim on the budget, ranked among themselves by weight/degree, with the remainder filled by global rank as before. The total kept edges/nodes never exceeds the existing caps, so the browser-safety guarantee they exist for still holds; a warning is logged if anchor-protected edges alone would exceed the budget. Deliberately does **not** exempt anchors from the user-adjustable weight-cutoff / node-degree sliders further down the same function, so those controls keep behaving exactly as before. Verified live with a synthetic reproduction (50-article-strength chemical/disease edge, 3500 filler edges, one weight-1 miR-124 edge): without the fix miR-124 is pruned to degree 0; with the fix it survives.
- **Same miRNA-Dilution Problem, RAG/Chat Side**: `is_mirna_node` (`netmedex/utils.py`) generalizes the previous name-prefix-only `_is_mirna_name` check (`netmedex/chat.py`) to also match on node type and aliases, and no longer requires `type == "Gene"` -- some miRNA nodes aren't tagged as Gene, so they were previously invisible to Chat's "what miRNAs are linked to X" listing queries. `GraphRetriever.find_relevant_nodes` / `_expand_mechanism_family` (`netmedex/graph_rag.py`) gained the same category-expansion step already used for the graph-render fix above (a query mentioning "microRNA" now pulls in every miR-*/let-7* node as a RAG retrieval anchor, not just ones matched by literal substring), plus broader trigger-word/listing-phrase recognition (Traditional Chinese variants, "find all", "列表", "找出", "顯示", "包含哪些").

## [1.5.15] - 2026-09-18

### Changed

- **Chat Model Override / Verifier Provider Model Dropdowns Now Default to the Main Model**: With "Same as main provider" selected (Verifier Provider's default, since relation-direction verification is on by default), the Model dropdown showed a bare "Custom..." placeholder until the user manually clicked Refresh -- even though the underlying resolution (`_resolve_chat_llm_client` in `chat_callbacks.py`, and the verifier branch of `pipeline.py`) already silently reuses the main LLM Configuration's model in this case. Purely a UI-clarity gap, not a functional bug. Added `sync_chat_override_model_default` / `sync_relation_verifier_model_default` (`llm_callbacks.py`), triggered only by that section's own Provider dropdown (`Input`) with all main-provider model/custom-model fields as `State` -- so background edits elsewhere, or a model the user deliberately picked while staying on the same provider, are never clobbered; it only re-mirrors main when the user actually (re)selects "Same as main provider".

## [1.5.14] - 2026-09-18

### Added

- **"Show Communities" Silent No-Op Now Surfaced to the User**: `_set_network_communities` (`netmedex/graph.py`) has always silently returned without modifying the graph when Louvain finds at most one community for the current network -- no error, no visual change, making the toggle look broken with zero indication of why (reported live: "on/off both produce no visible change", confirmed the community-detection mechanism itself works correctly on a representative query, 4 communities / 57 of 61 nodes grouped -- so this is specifically the ≤1-community case). Added `show_community_toggle_feedback` (`webapp/callbacks/graph_update.py`) plus a `community-toggle-status` status line under the toggle (`webapp/components/sidebar.py`). Deliberately a separate, observation-only callback (`Input("cy", "elements")` + `State("cy-params", "value")`, both already-existing) rather than a new `Output` on `update_graph` itself -- that callback already has 11 Outputs and 6 return paths and is the highest-blast-radius callback in the app (drives every graph render), so this can only ever affect the new status line, never graph rendering.

### Fixed & Hardened

- **Duplicate `CYTO_STYLESHEET` Definition Silently Discarded Edge Styling**: `webapp/utils.py` defined `CYTO_STYLESHEET` twice (found while investigating the community-toggle report); Python keeps only the last assignment, so the second (incomplete) copy was the one actually imported by `webapp/components/graph.py`, missing three rules present only in the abandoned first copy: green (`#28a745`) edge coloring for activating/inducing/etc. relations, red (`#dc3545`) coloring for inhibiting/suppressing/etc. relations, and dashed-line styling for `edge_type='node'` edges. Dead code since a March 2026 refactor (`dc2503f5`). Merged into a single definition retaining all rules.

## [1.5.13] - 2026-09-18

### Fixed & Hardened

- **"Same as Main Provider" Fetch Ignored .env-Configured Keys**: `_resolve_effective_provider_key_url` (`llm_callbacks.py`), used by both the Chat Model Override and Verifier Provider "Refresh available models" buttons, only reused whichever key was typed into the matching provider's Advanced Settings form field (`main_keys`). Anyone relying on a server-side `.env` credential (e.g. `OPENAI_API_KEY`) without ever typing it into the browser got an empty key and a "No models found" error, even though that exact provider works fine at Submit time. Now falls back to `get_provider_api_key(effective_provider, None)` -- the same per-provider env var resolution Submit-time initialization already uses -- and, for `local`, to `LOCAL_LLM_BASE_URL` when no base URL was entered either. This resolution is intentionally independent of `llm_client`'s currently-loaded provider, since it must work correctly even before the user has ever clicked Submit/Verify Connection. Moved to module level (out of the `callbacks(app)` closure) so it's directly unit-testable; added 3 regression tests (`tests/test_model_selection.py`) covering the env-var fallback, explicit-override precedence, and Local Ollama's base-URL fallback.

## [1.5.12] - 2026-09-18

### Changed

- **Local-Model Semantic Analysis Default Concurrency: 1 → 2**: `PubTatorGraphBuilder.add_collection` (`graph.py`) hardcoded `max_workers=1` for `provider == "local"`, reasoning that on-prem models commonly expose only one real generation slot. Live-measured on a single-GPU Ollama endpoint (`gpt-oss:120b`, 8 articles) to validate before changing the default: `workers=1` took 734.8s; `workers=2` took 599.0s with 0/8 timeouts -- a real ~19% speedup, well short of the ~2x a genuinely parallel backend would give, confirming most requests were still queuing for the same compute rather than running concurrently. Still a net win with no observed downside, so the default moves to 2; going higher would mostly lengthen that queue without more real parallelism on typical single-GPU setups. `NETMEDEX_SEMANTIC_WORKERS` remains available to raise further for operators with genuine concurrent capacity (batched vLLM/SGLang, multi-GPU).

## [1.5.11] - 2026-09-17

### Fixed & Hardened

- **Active LLM Banner Ignored Unsubmitted Model Changes**: `show_active_llm_banner` (`llm_callbacks.py`) only compared the selected *provider* against `llm_client.provider` to decide whether to show the "🟡 pending" state; it never looked at the model dropdowns. Changing the model (e.g. `openai-model-selector`, or its paired `openai-custom-model-input`) without clicking Submit/Verify Connection left the banner claiming the *previous* model was still active, with no visual cue that anything was unsaved. Added `_selected_model_for_provider` (resolves each provider's "custom" dropdown sentinel to its paired free-text field, mirroring `initialize_llm_client_from_settings`) and wired all six providers' model/custom-model inputs (plus Local Ollama's `llm-model-input`) into the callback so a model change is detected exactly like a provider change already was.

## [1.5.10] - 2026-09-17

### Added

- **Bottom Close Button for Advanced Settings**: The panel previously had only one close button, at the top (`close-advanced-settings-btn`). After the recent additions (Chat Model Override, expanded Verifier Provider), the panel is long enough that closing it required scrolling back up. Added `close-advanced-settings-btn-bottom` at the end of the settings list, wired into the existing `open_advanced_options` callback (`webapp/callbacks/advanced_settings.py`) alongside the original close button -- either one closes the panel.

## [1.5.9] - 2026-09-17

### Added

- **Unified "Same as Main Provider" Pattern for Verifier Provider and Chat Model Override**: Both sections now share one lightweight design: a provider dropdown (default "Same as main provider") + a model dropdown (fetched via a shared "🔄 Refresh available models" button, with a "Custom..." fallback text input). An API key field is only revealed when the selected provider genuinely differs from the main provider; a Base URL field is only revealed for Local Ollama. New shared helpers in `llm_callbacks.py` (`_resolve_effective_provider_key_url`, `_fetch_models_for_provider`) back both sections' fetch buttons (`fetch_chat_override_models`, new `fetch_relation_verifier_models`), and new progressive-disclosure toggle callbacks in `semantic_callbacks.py` (`toggle_chat_override_extra_fields`, `toggle_relation_verifier_extra_fields`) show/hide the API key and Base URL rows by comparing the section's provider dropdown against the main `llm-provider-selector`.

### Fixed & Hardened

- **Verifier Provider Silently Depended on Server-Side Environment Variables**: `pipeline.py`'s relation-verification logic called `initialize_llm_client_from_settings(candidate_verifier, provider=verifier_provider)` with no API key at all -- for a provider different from the main one, this only worked if that provider's key happened to already be set as a server-side `.env` variable, not whatever the user typed into the browser UI. Choosing a different verifier provider without that env var silently fell back to the main client, logged only server-side. Verifier Provider now has its own dedicated API key/model/base-URL fields (reusing the main client's already-resolved credentials when left at "Same as main provider", exactly like the Chat Model Override).

## [1.5.8] - 2026-09-17

### Added

- **Chat Model Override: Fetch Real Available Models**: `chat-override-model` (Advanced Settings) changed from a plain `dbc.Input` text box to a `dcc.Dropdown` populated by a new shared `fetch_chat_override_models` callback (`llm_callbacks.py`), triggered by a new "🔄 Refresh available models" button. Dispatches to the currently-selected `chat-override-provider` and reuses the exact model-listing methods the main LLM config already relies on (`LLMClient.get_openai_models`/`get_gemini_models`/`get_groq_models`/`get_anthropic_models`/`get_openrouter_models`, plus inlined NVIDIA NIM and Local Ollama HTTP calls matching `fetch_nvidia_models`/`fetch_local_models`). A "Custom..." option (backed by a new `chat-override-custom-model` text input, shown/hidden by `toggle_chat_override_custom_model_input`) still allows typing an arbitrary model name. `_resolve_chat_llm_client` (`chat_callbacks.py`) now resolves the "custom" sentinel to the typed value itself, rather than relying on `initialize_llm_client_from_settings`'s per-provider `*_custom_model` kwargs (google/nvidia/local don't support that indirection, and this dropdown is shared across all providers).

## [1.5.7] - 2026-09-17

### Fixed & Hardened

- **Removed Silent 50-Abstract Cap on Chat's RAG Corpus**: `auto_initialize_chat` (`chat_callbacks.py`, both branches without a manually-selected sub-network) called `_abstract_documents_from_graph(G, limit=50)`, indexing only the top 50 abstracts by citation weight into `AbstractRAG` regardless of how many articles the network was built from. Every subsequent question in that conversation could only ever retrieve from those 50 -- undocumented, uncontrollable, and easy to mistake for retrieval being "stuck" on whatever was most relevant when the session started. Verified `ChatSession.send_message` already re-runs `self.rag.get_context(search_query, ...)` fresh per turn using that turn's own message text (not the first question's) against `self.rag.documents` -- so the fix is purely removing the indexing-time cap (`_abstract_documents_from_graph(G)`, no `limit`), matching `_rebuild_chat_session_from_graph`'s existing uncapped behavior, not a change to retrieval logic itself.

## [1.5.6] - 2026-09-17

### Added

- **Chat Model Override in the Web UI**: `webapp/components/advanced_settings.py` gains a "Chat Model Override (optional)" section (`chat-model-override-toggle` + `chat-override-provider`/`chat-override-api-key`/`chat-override-model`/`chat-override-base-url`), shown/hidden via a new `toggle_chat_override_fields` callback in `semantic_callbacks.py`. `chat_callbacks.py` gains `_resolve_chat_llm_client()`, which returns the shared build-time `llm_client` singleton unchanged when the toggle is off (identical behavior to before), or constructs a brand-new independent `LLMClient()` from the override fields when on -- avoiding re-mutating the shared singleton, which would otherwise clobber its build-time configuration. Wired into all three call sites that construct a `ChatSession` (`auto_initialize_chat`'s two branches, `initialize_chat`, `send_message`/`_rebuild_chat_session_from_graph`), each gaining 5 new `State()` entries. This is a deliberately compact design (plain provider dropdown + 3 text inputs, not a full per-provider UI block mirroring the main LLM config's model-fetching dropdowns) to avoid roughly doubling the already-large `run_pubtator3_api`/chat callbacks' State counts. Verified: `collect_callbacks()` registers all 72 callbacks without conflict and all 6 new component IDs resolve in the rendered layout. Brings the FastAPI bridge's v1.5.5 model-split capability to the main web app.

## [1.5.5] - 2026-09-17

### Added

- **Separate LLM Client for Graph Building vs. Chat Generation**: `BridgeConfig` (`chat_bridge.py`) and `SessionConfigModel` (`fastapi_bridge.py`) gain optional `chat_provider`/`chat_api_key`/`chat_model`/`chat_base_url` fields. `NetMedExChatBridge` now builds a second `chat_llm_client` via `_init_chat_llm_client`, used only by `ChatSession` for Layer 1-5 generation; `PubTatorGraphBuilder`'s semantic edge extraction keeps using the original `llm_client`. Left unset (the default), `chat_llm_client is llm_client` -- identical behavior to before this change. Rationale: extraction is called once per article on a narrow task (classify the relation between two given entities in one abstract); Chat synthesis is called once per question and must read/reason across many abstracts at once. A live-tested comparison (imatinib/BCR-ABL, same 8 PMIDs) found these have different cost/quality tradeoffs -- after the v1.5.4 evidence-field fix, `gpt-4o-mini`'s extraction claim-safety pass rate (68.4%) was within single digits of pricier models (`gpt-4o` 72.7%, `gpt-5.6-luna` 76.2%), while Chat-time causal-mechanism depth is where model tier differences are large. This lets a session build cheaply per-article and still get flagship-quality answers per question.

## [1.5.4] - 2026-09-17

### Fixed & Hardened

- **Semantic Extraction: Missing `evidence` Field in Compact-Retry Fallback**: `_build_compact_retry_prompt` (`semantic_re.py`) -- used when the first extraction pass returns zero parsable relations -- omitted `evidence` from its output schema entirely. Any relation recovered only via this fallback therefore could never carry a supporting quote, which unconditionally fails `_select_edge_support`'s claim-safety gate (`graph_rag.py`) regardless of the relation's actual correctness. Live-tested comparison of `gpt-4o-mini` vs. `gpt-5.6-luna`/`gpt-5.6-sol` as the extraction model (same 8 PMIDs, same query) initially suggested `gpt-5.6` had far worse extraction quality (0-16% of directional edges reaching Tier A vs. 81-83% for `gpt-4o-mini`); tracing the raw LLM responses showed `gpt-5.6` simply triggers this evidence-less fallback path more often (more first-pass refusals/format complaints), not that its underlying extraction is worse. `evidence` is now a required field (with explicit "REQUIRED, do not omit" wording) in all three extraction prompts (initial, coverage, and compact-retry). Verified live: the same `gpt-5.6-luna` session that previously abandoned Layer 3 entirely ("insufficient evidence to form a causal mechanism hypothesis") now produces a complete, correctly-cited 3-step causal chain for the same question.

## [1.5.3] - 2026-09-17

### Fixed & Hardened

- **Single-Hop Directional Edges No Longer Wrongly Discarded**: `_classify_path_gate` in `graph_rag.py` forced `gate_tier="C"` (fully discarded, not even retrieval-safe) whenever a directional edge's recorded `source_id` didn't match the traversal order of the requested path -- including a plain 2-node edge where the query simply anchored on the target end. Live-tested comparison (imatinib/BCR-ABL) showed this discarding a high-confidence (`support_tier="A"`, confidence 0.85, quote-aligned) `targets` edge purely because of anchor direction, forcing Layer 3 into its text-only fallback despite the graph having exactly the evidence it needed. Now only a *multi-hop* chain (3+ nodes) is discarded for a reversed hop, since composing "A causes B causes C" requires each hop to actually flow that way; a single direct edge is still fully valid evidence regardless of which end the traversal started from. `GraphRetriever._format_path` now renders every directional edge in its true recorded direction (swapping the printed node order when needed) rather than blindly following traversal order, so the LLM is never shown a reversed claim (e.g. "BCR-ABL activates imatinib") that the underlying evidence never supported.
- **LLM Provider Switch No Longer Leaves a Stale Model Name**: `LLMClient.initialize_client()` already reset `base_url` to the new provider's default when `provider` changed and no explicit `base_url` was given, but did not do the same for `model`. A client auto-initialized as `local` (`LOCAL_LLM_MODEL=gpt-oss:120b`) that was then switched to `provider="openai"` without an explicit `model` kept the Ollama model tag and sent it to OpenAI's API, 404ing (`model gpt-oss:120b does not exist`) on every call. Found live via the FastAPI bridge while comparing local vs. cloud providers. `initialize_client()` now resets `model` to the new provider's env-configured or hardcoded default under the same "provider changed and no explicit value given" condition already used for `base_url`.
- **Local-Model Semantic-Analysis Time Estimate**: The "this may take 2-3 seconds per article" progress message (`pipeline.py`) was calibrated against small/cloud models; a 120B local Ollama model measured ~90s/article (~12 minutes for 8 articles) in testing -- 30-40x that estimate. The message now widens automatically to a range ("under a minute to 10+ minutes... depending on your hardware") when `llm_provider == "local"`.

## [1.5.2] - 2026-09-15

### Added

- **Cross-Literature Conflict Detection for Layer 3**:
  - `relation_polarity()` in `relation_types.py` maps directional relations to a regulatory sign (`+`/`-`).
  - `GraphRetriever._detect_polarity_conflict` (in `graph_rag.py`) flags edges where two PMIDs report opposite direction for the same edge (e.g. `inhibits` vs `activates`); `_format_path` surfaces this as a `{CONFLICT: PMID:X relation(+) vs PMID:Y relation(-)}` marker instead of silently keeping only the higher-confidence side.
  - Layer 3's prompt (`chat.py`) now requires a **Literature Conflict** callout whenever this marker is present, and caps that hop's Evidence Confidence at "Low".
- **Layer 3 Diagnostic Logging**: `get_subgraph_context_with_paths` logs directional-edge availability (claim-safe path count vs. total candidates) per turn, to distinguish "no directional edges available" (mostly `edge_method=co-occurrence`) from other causes of a thin Layer 3.
- **In-Chat "Switch to Semantic Analysis" Nudge**: `ChatSession.send_message` now returns `suggest_semantic_edge_method`, true only when a turn actually had no directional edges to reason over *and* the network wasn't already built with `edge_method="semantic"` (so switching again wouldn't help). The webapp appends an inline suggestion to the assistant's reply when this fires, skipped for Compact Mode answers in any supported language. Requires `PubTatorGraphBuilder` to stamp `graph.graph["edge_method"]` at build time (previously undiscoverable after the fact).

### Fixed & Hardened

- **Local-Provider Chat Token Budget**: `local` provider chat completions were flat-capped at 2500 max_tokens, which routinely truncated Layer 3's evidence table before its Weakest Link / Testable Prediction / Suggested Validation fields. Raised to 4000 for regular (non-bootstrap) turns.
- **Edge Construction Method Default Changed to `semantic`**: The `edge-method` dropdown default moved from `co-occurrence` to `semantic` so Chat's Layer 3 has directional evidence to reason over by default. `co-occurrence` produces only symmetric edges, causing Layer 3 to mostly skip or fall back to a low-confidence text-only summary. The per-article LLM latency this adds is already surfaced via a live progress bar with an upfront time estimate during network construction (`pipeline.py`), so the cost/latency tradeoff is visible rather than a silent wait. `co-occurrence` remains available and is the right choice before an LLM API key is configured.
- **Early LLM-Configuration Check**: `run_pubtator3_api` (the main "Search & Build Network" callback in `pipeline.py`) previously checked for a configured LLM key only right before graph construction — *after* the full PubTator literature search had already run to completion. Moved this check to immediately after LLM client initialization, before the PubTator fetch, so selecting Semantic Analysis without a configured key fails immediately instead of after wasting the entire search. The graph-file restore path (uploading a `.pkl`) is unaffected — it already returns before this point.

## [1.5.1] - 2026-09-13

### Added & Improved

- **Type-Constrained Biomedical Acronym & MeSH Standardisation**:
  - Integrated `BIOMEDICAL_ACRONYM_MAP` and MeSH CUI lookup into `normalize_knowledge_graph` to expand common medical acronyms (e.g. `RA` in Disease -> `rheumatoid arthritis`, `RA` in Chemical -> `retinoic acid`).
  - Protected Gene, Mutation, and SNP node types from acronym modification to preserve genetic symbol specificity.

### Fixed & Hardened

- **Cytoscape Canvas Height Stability**:
  - Implemented `cy_container_visibility` to enforce container height (`800px`), preventing inline style overrides from collapsing the Cytoscape graph canvas to `0px` during layout transitions.
- **Diskcache WAL Checkpoint Safeguard**:
  - Added SQLite WAL checkpoint (`PRAGMA wal_checkpoint(PASSIVE)`) prior to graph restoration callbacks, preventing SQLite WAL accumulation from blocking progress updates.
- **LLM Error Log Sanitisation**:
  - Applied error message sanitisation before logging LLM exceptions to prevent API key exposure in log outputs.
- **UI Progress Animation**:
  - Enhanced upload and graph restoration progress bars with staged pacing delays for smooth visual progress bar rendering.

## [1.5.0] - 2026-09-09

### Added

- **FastAPI Bridge SessionStore Memory Management & TTL**:
  - Added LRU session eviction with configurable capacity limit (`NETMEDEX_MAX_SESSIONS`, default 50).
  - Added automatic TTL expiration (`NETMEDEX_SESSION_TTL`, default 7200s / 2 hours) to reclaim memory from idle sessions containing NetworkX graphs and NodeRAG vector indices.
  - Hardened Pydantic model type annotations and timezone handling for Python 3.9+ runtime compatibility.
- **Chat Context Window Safety & Dynamic Budgeting**:
  - Added provider-aware context truncation in `_build_messages` (12,000 characters for local models, 45,000 characters for cloud models) to protect smaller LLMs from context window overflows.
  - Added graceful error translation for LLM context-length exceeded exceptions, guiding users to adjust `top_k` or narrow focus nodes instead of raising raw API crashes.

### Fixed & Hardened

- **GraphBuilder Lifecycle State Protection**:
  - Added `_is_built` state tracking in `PubTatorGraphBuilder` to prevent destructive redundant edge pruning if `build()` is called repeatedly without new articles.
  - Added defensive warnings when articles are appended to an already-built graph.
  - Added safe early exit for 0-article graph builds.
- **Semantic Relationship Extractor Dependency Guard**:
  - Added explicit `ImportError` check when `SemanticRelationshipExtractor` is `None` under `edge_method="semantic"`, providing clear installation guidance instead of raw `TypeError: 'NoneType' object is not callable`.
- **NPMI Floating-Point Precision Boundary**:
  - Hardened joint probability equality checking in `normalized_pointwise_mutual_information` with `math.isclose` and $10^{-9}$ numerical tolerance, preventing floating-point precision deviations from bypassing the boundary branch.

## [1.4.0] - 2026-08-18

### Added

- **Three-Tier Multi-Granularity Hybrid RAG**:
  - **Community Detection & Macro-Level GraphRAG (`netmedex/community.py`)**: Integrated Louvain topological modularity clustering to identify functional communities, extracting top biological hubs (genes, diseases, chemicals, phenotypes), key relations, top PMIDs, and automated functional summaries for macro-level context injection.
  - **Macro-Level Context Integration in `GraphRetriever` (`netmedex/graph_rag.py`)**: Added `find_relevant_communities` and `get_macro_community_context` to inject `### Macro-Level Functional Communities` alongside micro-level 2-hop paths.
  - **Upgraded Chat Prompt Framework (`netmedex/chat.py`)**:
    - Layer 1 structured 3-level indented list (Evidence Source, Key Finding, Direct Quote) with standardized `[PMID:xxxxxxxx]` citations.
    - Layer 3 strict 8-column causal mechanism evaluation table with polarity and step-by-step confidence assessment.
    - Multilingual prompt synchronization for English, Traditional Chinese, Japanese, and Korean.
  - **Quantitative Benchmarks in Manuscript (v1.4)**:
    - Formally integrated 50-question / 877-judgment benchmark results into manuscript docx and markdown (Novelty +0.21, Research Value +0.21, 50% blinded first-choice preference, 100% citation traceability, and pre-2015 temporal holdout prospective validation).

- **Relation-Direction Verification (2nd LLM, opt-in)**: `SemanticRelationshipExtractor` and
  `PubTatorGraphBuilder` gained `verify_relations`/`verifier_llm_client` parameters. When enabled,
  every directional semantic edge (e.g. `inhibits`, `upregulates`, `treats`) is checked against its
  supporting evidence quote by a second LLM pass before being added to the graph; an edge that
  fails verification is downgraded to `associated_with` rather than dropped, since the evidence
  likely still supports some relationship, just not confidently in the claimed direction. Exposed
  as a new "Relation-Direction Verification" toggle in Advanced Settings, with an independent
  verifier-provider dropdown (falls back to the main LLM client if no distinct provider is
  configured). Motivated by an internal evaluation audit that found only ~33% of extracted
  directional relations had the correct direction even with the extraction prompt's existing
  Directionality/Passive-Voice rules — verifying a candidate edge against its evidence is a
  smaller, easier task than the original extraction, so an independent second model is more likely
  to catch a direction-reversal error than the same model re-asked.
- **Adaptive Evidence-Gated Hybrid Evaluation**: the formal runner now includes an auditable
  `F_adaptive` profile that routes direct retrieval questions to text-only retrieval, association
  questions to 1-hop graph retrieval, and mechanism/hypothesis questions to evidence-gated 2-hop
  retrieval. Every exposed multi-hop path must carry stored extraction evidence on every hop.
- **Token-Budgeted Multi-model AI Panel**: reproducibly blinded answer worksheets, enriched frozen
  edge evidence, resumable OpenAI/Gemini/Anthropic judges, disagreement-first sampling, dry-run
  token estimates, multi-rater reliability, paired bootstrap comparisons, and checksum manifests
  are available under `evaluation/`.
- **Evidence-Margin Graph Reranking**: adaptive evaluation no longer gives every graph-linked PMID
  an unconditional 1.5x multiplier. A PMID is boosted only when a fully evidenced, query-ranked
  path exceeds its text score by a configured margin, and the two scores are conservatively
  blended. The runner can replay frozen query-specific graph exposures and skip answer generation
  for deterministic, completion-token-free retrieval comparisons.

### Fixed

- **Numeric-Only Node Names**: `PubTatorGraphBuilder._add_nodes` now rejects nodes whose resolved
  display name is purely numeric (e.g. a bare `"0409"`), which can occur when PubTator3's upstream
  NER annotates a truncated identifier or figure as an entity mention. Prevents these artifacts
  from surfacing as graph node/edge endpoints.
- **Graph Confidence Ranking**: `GraphRetriever` now reads the actual nested semantic confidence
  mapping (`{pmid: {relation: score}}`) when ranking paths instead of silently assigning every
  semantic edge the same fallback confidence of `0.5`.
- **Chroma Collection Isolation and Telemetry**: AbstractRAG and NodeRAG use distinct collections
  during formal runs so node IDs cannot replace PMID results; anonymized Chroma telemetry is also
  disabled for both ephemeral and persistent clients.
- **Graph Evidence Prompt Payload**: production Hybrid RAG now passes a deterministic PMID-linked
  evidence quote with each graph edge into the final ChatSession prompt. The system prompt rejects
  graph-derived claims whose hop quote is absent or does not support the stated relation/direction,
  fixing the prior gap where the generator received graph labels and PMIDs without their evidence.

## [1.3.6] - 2026-06-29

### Fixed

- **Deterministic ChromaDB Retrieval**: Stabilized vector retrieval result ordering for reproducible RAG outputs when candidate scores tie.

## [1.3.5] - 2026-06-28

### Fixed

- **Deterministic 2-Hop Traversal**: Stabilized 2-hop path traversal ordering for reproducible graph reasoning results.

## [1.3.4] - 2026-06-22

### Changed

- **Version Alignment**: Corrected remaining version references in `README.md`, `DEPLOYMENT.md`, `DOCKERHUB_OVERVIEW.md`, and the web application sidebar UI to align with release v1.3.4.

## [1.3.3] - 2026-06-22

### Added

- **LLM Provider UI, Session Isolation, and Local Model Support**: Enhanced session isolation on the server side and support for local model configuration dynamically via the web UI.

### Fixed

- **Offline Cache Support**: Configured `TIKTOKEN_CACHE_DIR` in the Dockerfile to pre-download tiktoken BPE cache in the builder stage for offline/air-gapped deployment.
- **Normalization Safeguard**: Disabled the sapBERT normalization toggle button when no active LLM client is configured.
- **Code Quality**: Addressed and resolved several P1–P4 code review issues.

### Changed

- **Webapp Controls & Performance**: Updated webapp UI, callbacks, and startup script to use stable parameters, and added defensive logging/checking.
- **Configuration Redaction**: Redacted internal/development `.env` values, and expanded `.env.example` to provide templates for all 7 supported LLM providers.
- **Data Exclusions**: Excluded Pediatric CNS tumor demo/cache directories from GitHub tracking and the final production Docker image.

## [1.3.2] - 2026-06-02

### Added

- **Search Nodes @Type Syntax**: New `@TypeName` token in the Search Nodes input for selecting nodes by biological type.
  - `@Gene` — highlights all Gene nodes with a purple border (no dimming, no path search).
  - `@Gene:gut` — selects Gene nodes whose name contains "gut" as anchor nodes (orange border, neighbor/path mode).
  - `keyword, @Gene` — combines keyword anchors with the top-20 Gene nodes by literature count (PMID frequency) as anchors for Dijkstra shortest-path search.
  - Multi-type: `dementia, @Gene, @Disease` runs path search across keyword + type-expanded anchors simultaneously.
  - Unmatched keywords are silently skipped; paths are computed from the remaining found anchors.
  - Supported types: Gene · Disease · Chemical · Species · CellLine · DNAMutation · ProteinMutation · SNP.

### Fixed

- **Chat Download History**: Added `full_history` (unbounded) to `ChatSession` so download includes all messages the user sees in the UI, not just the rolling 3-pair LLM context window.

### Changed

- **Search Nodes Tooltip**: Updated info tooltip with `@Type` syntax reference, anchor vs path-node color legend, and silent-skip behaviour note. Tooltip CSS: `max-width: 380px`, `line-height: 1.5` for readability.
- **Chat System Prompt — Mode Selection**: Require explicit `MODE: Full / Compact` declaration inside the `<thinking_english>` block with positive/negative examples, eliminating ambiguous LLM judgment. Added `NOT Compact` boundary cases to prevent incorrect Compact Mode activation for mechanism or evaluation questions.
- **Chat System Prompt — CONSISTENCY DIRECTIVE**: Changed "cite ALL PMIDs in ascending order" to "cite every PMID **directly relevant** to the user's question" — resolves conflict with CRITICAL ANSWER DIRECTIVE where irrelevant PMIDs padded Layer 1 for focused questions.
- **Chat System Prompt — Compact Mode label**: Added `[Direct Answer]` translations for non-English responses: Traditional Chinese `[直接回答]`, Japanese `[直接回答]`, Korean `[직접 답변]`.

## [1.3.1] - 2026-06-01

### Fixed

- **Diskcache WAL Accumulation**: Added `PRAGMA wal_checkpoint(PASSIVE)` at the start of each `initialize_chat()` background callback to prevent SQLite WAL from growing across multiple analysis runs and blocking `set_progress()` calls. Complemented by the existing startup checkpoint in `app.py`.

### Changed

- **Chat Response Format — Adaptive Mode (Direction B)**: Refined the 5-layer system prompt to be context-sensitive rather than rigidly fixed:
  - **Compact Mode**: Simple factual or listing questions (e.g., "Which PMIDs mention X?") now collapse into a `[Direct Answer]` with inline citations, skipping Layers 2–5.
  - **Layer 2 Skip Conditions**: If no graph inference paths are relevant to the specific question, or if Layer 1 already covers all relevant entities, Layer 2 now emits a single explanatory line instead of empty structured blocks.
  - **Adaptive Layer 5**: Initial/broad analyses generate 3 suggested questions; focused follow-up questions generate 1; Compact Mode omits Layer 5 entirely.

## [1.3.0] - 2026-05-30

### Added

- **Anthropic API Integration**: Full native support for Anthropic Claude models (e.g., `claude-3-5-sonnet`, `claude-3-opus`) as a core LLM provider in both the web application (Advanced Settings UI) and CLI/API interfaces.
- **Token Usage & Cost Analysis**: Added complete documentation for cost calculation per pipeline stage (`docs/token_cost.md`), including strategies for cost minimization using lighter models or co-occurrence graphs.
- **Biomedical RAG Platform Comparisons**: Published comparative analysis documentation against MRTKG (`docs/NetMedEx_vs_MRTKG_comparison.md`) describing architectural advantages.

### Changed

- **Advanced LLM Settings & Customization**: Rewrote LLM initialization and configuration parsing (`llm.py` and `advanced_settings.py`) to support multi-provider environments, dynamic testing of connection status for Anthropic/OpenAI/Gemini/Groq/NVIDIA NIM, and direct environment configuration saving to `.env`.
- **CJK / Universal Translation Robustness**: Strict universal language requirements inside prompts for non-English users, enforcing CJK output generation for all headers, labels, and structured segments.

## [1.2.8] - 2026-05-25

### Added
- **Groq API Provider Integration**: Full support for Groq models (Llama 3.3, Llama 3.1, Mixtral, Gemma 2, and Custom) including connection verification, dynamic model fetching in Advanced Settings, and writing config back to server `.env`.
- **Query Auto-Filtering**: Automatically appends publication-type exclusion tags (e.g. `NOT "Editorial"[pt] NOT "Letter"[pt] ...`) to free-text searches to eliminate noisy, non-research PubMed documents.
- **Dynamic Suggested Question IDs**: Automatically appends suffixes to suggested questions in Modal windows, preventing element ID collision bugs.

### Changed
- **Suggested Question Focus**: Enhanced system instructions to strictly citation-bind questions to specific biological concepts in context instead of generic X/Y placeholders.
- **Robust Suggested Question Parser**: Updated the parser in `chat.py` to handle both bracketed `[Q1: ...]` and bare `Q1:` formats.
- **RAG Consistency**: Set對話 `temperature=0` (was 0.3) for more deterministic response consistency.
- **Markdown Tables Spacing**: Enforced a blank line buffer before and after markdown tables in chat cards to resolve markdown rendering bugs.

### Fixed
- **100% Test Coverage Recovery**: Restored all deleted `tests/test_data` PubTator and JSON files, and adjusted mock client argument signatures/PMID extraction regexes in `test_cli.py`, `test_rag_chat.py`, and `test_semantic_prompt.py` to achieve full test success.

## [1.2.7] - 2026-05-21

### Added
- **Graph Rebuild Timing Logs**: Timing logs for server-side graph layout rebuild and Cytoscape JSON serialization to diagnose lag.
- **Graph Loading Spinner**: Added `dcc.Loading` wrapping to the Cytoscape canvas to display a spinner during server rebuilds.
- **Chat Indexing Diagnostic**: Preflight diagnostic checks and logging (selected nodes, edges, PMIDs, abstract match counts) before indexing NodeRAG, and displays configuration summary in the status bar.

### Changed
- **NVIDIA NIM Integration**: Shared LLM initialization helper ensuring NIM is correctly dispatched in Search, auto-Chat, manual Chat, and session-rebuild callbacks.
- **Large Graph preset Layout**: Skipped redundant client-side fCoSE passes on graphs with >700 nodes by falling back to `preset` layout, eliminating visual lag.
- **Non-English Search Gate**: Requires an active LLM for CJK/Korean search queries to translate and log the PubTator query properly.
- **Deduplication and Validation Warnings**: Preserves order while deduplicating PMIDs before annotation fetch; emits warnings in logs when parsed article count is significantly lower than requested PMIDs.
- **Debounced Node-Degree Input**: Fires graph updates only on Enter/blur to prevent per-keystroke rebuild lag.

### Fixed
- **PubTator Search Sort Consistency**: Ensured page-1 queries receive the selected sort parameter, aligning search results with subsequent pages to prevent missing PMIDs.
- **Lazy Session Rebuild**: Send-message callbacks now dynamically rebuild ChatSession from persisted `G.pkl` after server restarts instead of raising "session expired" errors.

## [1.2.6] - 2026-05-14

### Added
- **2-Hop Pathway Diagrams**: In the Chat Panel, 2-hop mechanism inferences are now automatically visualized as interactive Dash pathway cards (replacing Mermaid SVG). Each card shows nodes as styled boxes, edges as arrows with relation labels, and clickable PMID badges linking directly to PubMed. Bridge (mediator) nodes are rendered with a gold border.
- **Chat→Graph Interactive Highlighting**: 2-hop inference results automatically synchronize back to the Graph panel. Bridge nodes glow gold; inferred path edges render as dashed orange lines to distinguish them from direct 1-hop literature evidence.
- **Search Nodes — Dijkstra Shortest Path**: When 2 or more node names are entered in the Graph Panel "Search Nodes" field (comma-separated), the graph now computes the weighted shortest path between them using Dijkstra's algorithm (`cost = 1/weight`, where weight reflects NPMI/co-occurrence strength). Path nodes and edges are highlighted; intermediate nodes receive a teal border. Single-node searches retain the existing neighbour-highlight behaviour.
- **HTML Export — Shortest Path Search**: The standalone exported HTML file now includes the same Dijkstra-based Search Nodes functionality, with identical visual styling and segment-aware label matching.

### Fixed
- **CUI-based Node Deduplication**: Added a MeSH-ID pass to `normalize_knowledge_graph()` that merges nodes sharing the same non-null MeSH CUI regardless of surface name. This fixes cases like `"hcv"` and `"hepatitis c virus"` appearing as separate nodes; the most descriptive name is kept as canonical.
- **Search Nodes False Positives**: Replaced full-strip `includes()` matching with segment-aware prefix matching. Short queries (e.g. `ID1`) no longer incorrectly match nodes whose normalized name contains the query as an accidental substring (e.g. `COVID-19` → `"covid19"` contains `"id1"`). Longer queries (≥ 5 chars) retain full-strip substring fallback for compound identifiers like `SARS-CoV-2`.
- **Pathway Card Regex — Hyphenated Node IDs**: The Mermaid parser in the Chat Panel now accepts node IDs containing hyphens (e.g. `CAR-T`), fixing cases where the first hop of a 2-hop diagram was silently dropped and only 1 edge rendered.
- **Chat→Graph Synchronization — ID Mismatch**: Fixed a critical bug where `twohop_paths` stored Cytoscape stable UUIDs that never matched the raw NetworkX node IDs used by the graph, causing Chat→Graph highlighting to silently do nothing. The JS now matches paths by node **label/name** instead of ID, making the lookup immune to community-suffix mismatches between the pickled and displayed graph.
- **Focus Nodes ID Mismatch**: Fixed a root cause where `core_node_ids` (built from selected edge `source`/`target` UUIDs) failed `graph.has_node()` lookups because the pickled graph uses raw NetworkX hashes. The callback now resolves node IDs via a `label → raw_id` lookup table, ensuring `focus_nodes` contains valid graph IDs and 2-hop path extraction produces non-zero results.
- **2-Hop Path Highlighting Contrast**: Non-path nodes and edges are now dimmed to 15% opacity when a 2-hop highlight is active, and path elements use stronger visual styles (6px gold border + overlay glow for bridge nodes, 5px thick orange edges) to make the inferred route clearly visible against the background graph.
- **AI Search Query Over-constraining**: The `translate_query_to_boolean` prompt now enforces an OR expansion rule (concept synonyms connected by OR rather than a single exact phrase) and a rare entity rule (highly specific organism/gene names alone are sufficient — secondary AND constraints should be omitted to avoid zero-result queries).
- **Semantic RE Directionality**: Prompts in `semantic_re.py` now explicitly enforce that `entity1_id` is the source/effector and `entity2_id` is the target/effectee for directional relation types (e.g., activates, inhibits), preventing reversed edges in the knowledge graph.
- **No-Context Response Language**: When the provided context is insufficient to answer a query, the Chat assistant now responds in the session language instead of always falling back to English.
- **Chat PMID Support Full Names**: The 2-hop PMID support section now uses actual entity names (e.g., **bacteria → covid-19**) instead of placeholder letters A/B/C, and the Mermaid pathway diagram is enforced as mandatory for every 2-hop path.

## [1.2.5] - 2026-05-11

### Added
- **ONNX Pre-bundling**: The ChromaDB ONNX embedding model is now pre-downloaded and bundled within the Docker image, significantly reducing first-run latency and improving air-gapped environment support.

### Fixed
- **Vendor JS Packaging**: Fixed a critical bug in `pyproject.toml` where local Javascript assets (Cytoscape extensions) were not being correctly included in the installed package.
- **Chat UI Bugfixes**: Resolved issues with message ordering and auto-scroll behavior in the Chat panel.
- **CLI Documentation**: Updated help strings and error messages for the `netmedex` CLI.

## [1.2.4] - 2026-05-07

### Added
- **NVIDIA NIM Support**: Integrated NVIDIA NIM (microservices) as a supported LLM provider, enabling high-performance local or cloud-based inference for semantic extraction and RAG.
- **Active LLM Banner**: Added a status indicator in the Chat and Search panels to clearly show which LLM provider and model are currently active.
- **Collapsible UI Panels**: Further optimized the layout with collapsible sections in the Graph and Search panels to maximize screen real estate for visualization.

## [1.2.3] - 2026-04-30

### Added
- **Collapsible Sidebar**: Added a toggle button (☰) in the graph header to collapse and expand the sidebar with a smooth CSS transition. State is persisted to `localStorage` and restored on page reload.
- **Search History**: Recent API text queries are now saved (up to 8) in `localStorage` and shown as clickable chips below the query textarea. Clicking a chip re-populates the input instantly.

## [1.2.2] - 2026-04-30

### Added
- **Graph Empty State**: Added a guidance placeholder ("No network loaded") that appears on the main canvas when no graph has been loaded, replacing the blank screen and improving onboarding clarity.
- **Edge Visual Distinction**: Co-occurrence-only edges (`edge_type='node'`) now render as dashed lines with reduced opacity, visually distinguishing them from LLM-semantically-confirmed edges (solid lines). This maps to the 1-hop direct evidence vs. inferred co-occurrence distinction.

### Changed
- **LLM Settings Persistence**: LLM provider and model settings (`llm-settings-store`) now use `localStorage` instead of `sessionStorage`, so preferences (provider, model, etc.) survive page refreshes. API keys remain server-side only and are never persisted in the browser.

## [1.2.1] - 2026-04-29

### Security
- **HMAC-Signed Session Tokens**: Browser-side session data is now a signed token instead of a raw file path, preventing path traversal attacks.
- **API Key Isolation**: LLM API keys are no longer stored in or read from browser-side `dcc.Store`; keys are resolved exclusively from server environment variables.
- **XSS Prevention**: Added `escapeHtml()` to the standalone Cytoscape HTML export template; all node/edge data rendered into the info panel is now properly escaped.
- **Download Filename Sanitization**: Export filenames are sanitized server-side before being sent as download headers.

### Fixed
- **Rate Limit Retry**: Semantic extraction LLM calls now retry up to 5 times with exponential back-off (15 s → 30 s → 60 s → 120 s) on 429 / quota errors.
- **pmid-title-dict Sync**: Graph update callback now outputs the restored `pmid_title` dictionary on graph rebuild, fixing stale article-title references after re-load.
- **Node Name Normalisation**: Node names are lowercased on graph rebuild for consistent matching across `.pkl` versions.
- **HOST env Propagation**: Resolved `HOST` value is written back to the environment so Werkzeug reloader subprocesses inherit the correct binding address.
- **Docker Workflow**: Updated `build-push-action` v5 → v6 and corrected the DockerHub secret name (`DOCKERHUB_TOKEN` → `DOCKERHUB_PASSWORD`).

## [1.2.0] - 2026-04-28

### Added
- **Smart 2-Hop Graph RAG**: Implemented a sophisticated two-hop retrieval mechanism for deep mechanistic discovery.
- **Hybrid Scoring System**: Integrated NPMI (30%), LLM Confidence (40%), and Semantic Query Relevance (30%) for more accurate path prioritization.
- **Study-Type Labeling**: Added automated detection and labeling of research types (Human clinical data vs. Animal/Cell-line models) to ensure evidence clarity.
- **Ontology-Based Filtering**: Integrated strict node-type filtering (Genes, Diseases, Chemicals) to reduce noise from species or geographic metadata.
- **Bottleneck Scoring**: Implemented "Min-Link" scoring for 2-hop paths to ensure the weakest link determines the overall path strength, reducing false inferences.
- **2-Hop Penalty**: Applied a 0.8x uncertainty penalty to 2-hop connections to distinguish them from direct literature evidence.

## [1.1.0] - 2026-04-10

### Added
- **sapBERT Knowledge Graph Normalization**: Added an automated pipeline to merge semantically equivalent nodes (e.g., case variants and synonyms) using vector embeddings, significantly reducing graph redundancy.
- **Pediatric CNS 10k Dataset Support**: Fully verified and optimized the extraction and normalization pipeline for the 10,000-article pediatric brain tumor dataset.
- **Improved CJK Reasoning**: Enhanced multi-stage intermediary English reasoning for Chinese, Japanese, and Korean queries.

### Changed
- **Version Bump**: Officially transitioned from v0.9.9 to v1.1.0 to reflect the integration of advanced graph normalization and large-scale data support.


## [0.9.9] - 2026-03-29

### Added
- **Semantic Edge Coloring**: Integrated real-time edge coloring based on LLM-extracted relationship types (Green for activation/positive, Red for inhibition/negative).
- **Edge Confidence Threshold Slider**: Added a high-performance clientside filter in the Graph panel to instantly hide/show edges based on LLM confidence scores.
- **10k Article Pipeline Optimization**: Stabilized and verified the semantic extraction pipeline for large-scale pediatric CNS tumor datasets (9,000+ PMIDs).
- **BioC-JSON Metadata Enrichment**: Enhanced BioC-JSON parsing to preserve full author and publication year metadata during direct file loading.

### Changed
- **Version Alignment**: Officially bumped project version to v0.9.9 across technical metadata and UI labels.

## [0.9.7] - 2026-03-19

### Added
- **Citation Count Visibility**: Integrated "Total Citations" in Edge Info and a new "Citations" column in article tables (Nodes/Edges).
- **Automated Chat Summary**: The Chat Panel now automatically generates an initial evidence-based summary (Answers, Hypotheses, Suggested Questions) upon analysis.
- **Search Query Banner**: Added a persistent banner in the Chat Panel to maintain awareness of the original search context.

### Changed
- **Version Alignment**: Updated UI and package metadata to reflect the v0.9.7 release.

## [0.9.6] - 2026-03-19

### Changed
- Realigned release metadata (package version, Docker tags, sidebar badge, and docs) to publish the current set of updates under **v0.9.6**; see the Deployment guide and DockHub overview for the refreshed labels.

## [0.9.5] - 2026-03-18

### Added
- **Semantic Extraction diagnostics**: Added a new UI alert in the Search Panel that provides detailed metrics after semantic analysis, including article success rates, parse failures, coverage expansions, and dropped edges.
- **Improved Local LLM Parsing**: Enhanced the regex-based relaxed parser in `semantic_re.py` to be more robust when handling outputs from Ollama or LocalAI models.
- **Fetch Citation Counts**: New option in the Search Panel to pull real-time citation metrics from OpenCitations for all retrieved articles.

### Changed
- **Chat UX – PMID Reference Refinement**: Standardized PMID link formatting across the chat interface, ensuring consistent hyperlinking to PubTator3 and removing redundant URL displays.
- **Chat UX – Suggested Questions**: Improved parsing for "Suggested Follow-up" questions, making them more robust across different LLM response styles and languages.
- **Simplified Advanced Settings UI**: Standardized on ChromaDB default embeddings. Removed redundant embedding model selection sections for both OpenAI and Gemini providers to reduce UI clutter.
- **LLM Search Panel Alerts**: Migrated to a more professional `dbc.Alert` system for communicating processing status and semantic analysis results.
- **Enhanced Translation Strategy**: Refined the system instructions for query translation to ensure consistent English-only output for PubTator compatibility.
- **Sidebar Styling**: Optimized version tag display and advanced settings icon placement for better alignment.

### Fixed
- **Python 3.9 Compatibility**: Resolved `TypeError` where `zip()` was called with the `strict=True` keyword argument (only supported in Python 3.10+).
- **Search Panel Layout**: Fixed alignment issues between the AI Search toggle row and the query input textarea.
- **Citation Fetcher Stability**: Corrected `aiometer` job scheduling to prevent potential race conditions when fetching large batches of citations.
- **Gemini Coverage Bug**: Fixed a critical error where `pair_count` was undefined in the Gemini coverage prompt, which previously caused crashes during the second round of recall.
- **Model Fetching Robustness**: Improved error handling when local LLM endpoints are unreachable during model list fetching.

## [0.9.4] - 2026-03-09

### Added
- **Chat UX – Chronological Order**: Restored user-preferred message ordering (oldest at top, newest at bottom).
- **Chat UX – Smart Auto-Scroll**: Added a custom `MutationObserver` that automatically scrolls the view to align the **latest question** to the top of the chat window when a response arrives.
- **Chat UX – Reliable Copy Feedback**: Implemented a "pure JS" event delegation system for the copy button, ensuring 100% stable visual feedback (checkmark toggle) that works consistently across multiple clicks and re-renders.
- **LLM Settings – High-Speed Sync**: Re-engineered the LLM configuration logic using Clientside Callbacks. Toggling "AI Search" and "Edge Construction Method" now happens **instantly** in the browser as soon as a valid API key is detected, bypassing server latency.

### Data Export
- **Rich HTML Chat History**: Upgraded the chat history download to a high-fidelity HTML format. Messages now feature a professional "bubble" interface, clear hierarchical section headers (Evidence-Based Answer, Hypotheses, Suggested Questions), and automatic hyperlinking of all PubMed IDs (PMIDs) for direct access to PubMed.

### Fixed
- **Graph Panel – Layout System**: Resolved a critical frontend conflict caused by legacy `cytoscape-fcose.min.js`. The `fCose` layout and its repulsion slider are now fully functional and stable.
- **Callback Stability**: Eliminated duplicate Output definitions in `llm_callbacks.py` that were previously causing Dash to intermittently ignore UI update signals.

## [0.9.3] - 2026-03-07

### Added
- **Search Panel - Translation Enforcer**: All non-English queries (Japanese, Chinese, Korean, etc.) are now mandatorily translated to English via the LLM API (even when AI Search toggle is disabled) before hitting PubTator, significantly improving international literature retrieval.
- **Chat UI Revamp**: The Chat Panel layout now perfectly mimics leading AI assistants (ChatGPT/Gemini). User messages appear on the right side with aligned avatars, and AI responses align left.
- **Graph Panel - Auto-Clear**: Initiating a new search instantly clears the previous Cytoscape elements from memory, preventing buggy visual overlap or internal package crashes during graph rendering diffs.

### Fixed
- **Network Statistics Sync**: Solved the issue where total network node and edge counts failed to synchronize after creating dynamic groups (like "Show Communities"). The panel now accurately counts and updates metrics live directly from the visible display canvas.


## [0.9.1] - 2026-03-07
### Added
- **Graph Panel – Graph File Export**: New **"Graph (.pkl)"** download button exports the complete graph state (NetworkX graph including all node/edge attributes, `pmid_abstract`, and semantic analysis results) as a binary pickle file (`netmedex_graph.pkl`).
- **Search Panel – Graph File Restore**: New **"Graph File (.pkl)"** source option allows uploading a previously exported `.pkl` file. This bypasses the entire PubTator API + graph-building pipeline, restoring the graph session instantly — network visualization and Chat Panel (Analyze Selection) both work fully after restore.

### Changed
- **Advanced Settings – Max Edges**: Default value changed from 30 to **0 (unlimited)** so all edges are shown by default.
- **Search Panel – AI Search Translation**: LLM query translation prompt now explicitly requires the output to be in **English only**, improving PubMed/PubTator API compatibility.
- **Chat Panel – Message Order**: Chat messages are now displayed in **newest-at-top** order (CSS `column-reverse`) with automatic scroll to the latest interaction.

## [0.9.0] - 2026-03-04

### Added
- **Graph Layout – fCose**: Re-introduced the `fCose` (fast Compound Spring Embedder) layout option using the official `cyto.load_extra_layouts()` mechanism from `dash-cytoscape`. This correctly registers the `cytoscape.js-fcose` extension at startup, resolving the crash seen in v0.8.3.
- **Graph Layout – Node Repulsion Slider**: The Node Repulsion slider UI is now active and visible when the `fCose` layout is selected, allowing users to tune node spacing dynamically (range: 10,000 – 100,000).

## [0.8.4] - 2026-03-04

### Added
- **Chat Panel – Language Consistency**: Strengthened the system prompt to strictly follow the user's question language.
- **Chat Panel – Auto-Summary**: Updated the initial research summary prompt to respect the user's preferred language (defaulting to Traditional Chinese).

## [0.8.3] - 2026-03-04

### Fixed
- **Graph Visualization – Invisible Graph**: Resolved an issue where the graph area remained blank due to a crashing `fCose` extension. Reverted default layout to the stable `COSE`.
- **Graph Layout – fCose Removal**: Removed `fCose` from the layout options as it was unstable in some environments.
- **Chat Panel – Analyze Selection TypeError**: Fixed a compatibility error with Python 3.9 where `zip()` was called with a keyword argument (`strict=True`) only supported in Python 3.10+.
- **UI UX**: Fixed broken component imports and removed temporary debug borders from the graph container.

## [0.8.2] - 2026-03-03

### Fixed
- **Chat Panel – Analyze Selection token limit**: Replaced the single `collection.add()` call with a
  dynamic token-aware batching loop.  Documents are now split into batches of ≤ 250,000 tokens
  (using `tiktoken` when installed, with a word-count heuristic as fallback) before being sent to
  the embedding endpoint, preventing the
  `Error code: 400 – max_tokens_per_request (300 000)` error that occurred with ~1 000+ abstracts.
- **Search Panel – Reset button**: Pressing **Reset** now also hides the graph container and clears
  all Cytoscape elements, so the network is properly cleared along with the progress bar.
- **Graph/Chat Panel – Legend position**: The node-type legend is now `position: absolute` and
  draggable; users can click and drag it anywhere inside the graph canvas.

### Added
- `tiktoken` added as a core dependency for accurate token counting in the RAG embedding pipeline.
- **Graph Layout – fCose**: Added `fcose` (Fast COSE) layout as the new default, with a **Node
  Repulsion** slider (10k–100k, default 45k) that appears when fcose is selected.  The `fcose`
  layout plugin is bundled locally (`webapp/assets/cytoscape-fcose.min.js`) to avoid CDN dependency.
- **Graph Performance – Haystack edges**: Switched default edge `curve-style` from `bezier` to
  `haystack` for significantly smoother interaction on large graphs.  Directional edges (semantic
  analysis results) automatically fall back to `bezier` so arrowheads are preserved.

## [0.8.0] - 2026-02-05

### Added
- **UI UX Improvements**: 
    - Added a "Close" button to the **Advanced Settings** panel for easier navigation.
- **Dynamic OpenAI Model Fetching**:
    - Automatic fetching of available models from OpenAI when a valid API key is provided.
    - Dropdown population with fetched models for easier selection.

### Fixed
- **Graph Layout Interaction**: Resolved unintended resets of Network Display settings when changing graph layouts.
- **Chat Panel**: 
    - Fixed "Analyze Selection" button behavior to prevent unexpected switching to the Graph panel.
    - Restored the "Processing" spinner indicator during analysis.
- **Pipeline Stability**: Fixed a variable initialization error (`UnboundLocalError`) in the data processing pipeline.

## [0.7.0] - 2026-02-04

### Added
- **Enhanced Clientside Interactions**:
    - **Chat Auto-Scroll**: Implemented `MutationObserver` to automatically scroll chat window to the newest message.
    - **Dynamic Z-Index Management**: Smart z-index handling for Edge/Node info panels to prevent sidebar overlaps (replacing CSS hacks).
    - **Improved Tooltips**: Better positioning logic for UI tooltips.

### Changed
- **Frontend Logic**: Migrated core clientside callbacks to `clientside_scripts_v7.js` for better performance and maintainability.

## [0.6.0] - 2026-02-02

### Added
- **Hybrid RAG System**:
    - **Dual-Source Analysis**: Combines unstructured text leverage (PubTator abstracts) with structured graph knowledge (network topology) for more robust answers.
    - **Graph Context Retrieval**: 
        - Automatically identifies shortest paths between queried entities.
        - Retrieves neighbors and edge weights for context.
    - **Entity Linking**: Maps natural language entity names to graph node IDs.
- **UI Improvements**:
    - **Range Slider**: New interactive slider for filtering edges by weight (NPMI/Frequency).
    - **Export Info Tooltip**: Added detailed explanation for export formats.
    - **Loading States**: Improved visual feedback during AI processing in modals.

### Changed
- **Chat System**: 
    - Updated system prompts to explicitly distinguish between "Text Evidence" and "Graph Evidence".
    - `ChatSession` now utilizes `GraphRetriever` for context injection.
- **Controls**: 
    - Refined "Reset" and "Stop" button logic for better job management.
    - Optimized layout for control buttons to prevent overflow.

## [0.5.0] - 2026-02-01

### Added
- **Advanced RAG Chat System**:
    - **Interactive Chat Panel**: Context-aware chat with multi-line input and "Thinking" status indicator.
    - **Expandable View**: "Expand Chat" modal for better readability, supporting direct query input and history synchronization.
    - **Smart Citations**: 
        - Citations are clickable links opening PubMed in a new tab.
        - **Intelligent Filtering**: Source list automatically filters to display only the PMIDs actually cited by the AI in its response.
    - **UX Enhancements**: One-click copy button for AI responses.
- **Graph Visualization Enhancements**:
    - Edge labels displaying semantic relationship types (e.g., "inhibits", "activates").
    - Directional arrows for relationships with inherent directionality.
    - Enhanced edge information panel showing confidence scores and specific evidence sentences.
- **Natural Language Search**: Ability to convert plain English queries into optimized PubTator3 boolean queries using an LLM.

### Changed
- Updated `README.md` to reflect new AI-powered features and setup instructions.
- Improved web application UI for better integration of the chat panel.

### Fixed
- Fixed various Dash 3.x compatibility issues.
- Fixed sidebar toggle bug preventing automatic switch to Chat panel.
- Resolved Chat Panel visibility issues by refactoring sidebar navigation to `dbc.Tabs`.
- Updated Network Statistics to correctly count unique PMIDs for selected edges.

### Varied
- **Sidebar UI**:
    - Implemented distinct background colors for different modes (Green for Graph, Indigo for Chat).
    - Improved navigation with a clear tabbed interface (Search / Graph / Chat).
