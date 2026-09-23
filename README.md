# NetMedEx v1.7.3

[![Python package](https://img.shields.io/pypi/v/netmedex)](https://pypi.org/project/netmedex/)
[![GitHub](https://img.shields.io/badge/GitHub-latest-blue)](https://github.com/lsbnb/NetMedEx)
[![Doc](https://img.shields.io/badge/Doc-online)](https://yehzx.github.io/NetMedEx/)

**NetMedEx** is an AI-powered biomedical knowledge discovery platform. It searches over **30 million PubMed articles** via PubTator3, builds interactive co-mention networks of biological concepts (genes, diseases, chemicals, etc.), and lets you interrogate those networks through a **Hybrid RAG Chat** powered by large language models.

## What NetMedEx Can Do

NetMedEx follows a three-step discovery workflow — each step corresponds to a dedicated panel in the web interface:

1. **Search & Build Networks** — Query 30M+ PubMed articles by keyword, gene list, disease, or chemical. NetMedEx extracts co-mentioned biological entities and constructs a weighted, interactive knowledge graph. Supports multilingual input (CJK auto-translated to PubTator3 syntax).
2. **Explore the Graph** — Visualize entity relationships, detect communities (Louvain algorithm), adjust layout (fCose with node repulsion control), filter by entity type (`@Gene`, `@Disease`, …), and find the strongest-evidence path between nodes (Dijkstra weighted shortest path).
3. **Chat & Discover Mechanisms** — Select any sub-network and ask natural-language questions. The **5-Layer Hybrid RAG** uncovers latent 2-hop pathways (A → B → C) and structures responses from direct PMID-grounded evidence through speculative inference, causal mechanism, integrated summary, to suggested follow-up questions — with every claim labelled `[Human]` or `[Animal/In vitro]`.

**Supporting capabilities:**

- **Flexible LLM providers** — OpenAI, Anthropic Claude, Google Gemini, Groq, NVIDIA NIM, and local Ollama; configurable from the web UI without restarting.
- **Semantic entity normalization** — sapBERT + MeSH CUI deduplication merges abbreviations with full names (e.g. `"hcv"` ↔ `"hepatitis c virus"`) for a cleaner graph.
- **Rich export formats** — HTML (interactive), XGMML (Cytoscape), PubTator/BioC-JSON, RIS (EndNote), Chat History, and full Graph state (`.pkl`) for session restore.
- **Batch processing** — All search and network-building steps are also available via CLI for automated, high-throughput workflows.

---

<details>
<summary><h2>🆕 Recent Updates</h2></summary>

### v1.7.3 — 2026-09-22

- **Follow-up Questions Now Boost, Not Just Recall, the Previous Reply's Citations**: Each Chat turn already re-searches the full index fresh (never restricted to a prior turn's results, outside the separate opt-in Strict Citation Grounding mode) -- but a follow-up's own retrieval had no way to bring a still-relevant PMID from the previous reply back into this turn's ranking; only the LLM's own memory of the conversation text carried it forward. The previous reply's cited PMIDs are now folded into this turn's ranking boost alongside whatever this turn's own graph traversal finds, so a still-relevant prior citation can resurface -- without narrowing the search scope, and without changing anything for a turn that doesn't need it (a PMID that's no longer relevant simply gets no boost, exactly as before).
- **More Useful Article-Fetch Defaults**: "Max Articles" defaulted to 30 and "Sort" defaulted to Recency, together capping AI Search / Analyze Selection to the 30 *newest* matching articles regardless of how many actually matched. Diagnosed live: a real query matched 2,492 articles, but with these defaults only the 30 most recent were fetched, and by chance none of the recency-sorted batch mentioned the specific mechanism (a named microRNA) the question asked about -- not a retrieval or graph bug, just too narrow and too recency-biased a sample. Defaults changed to 50 articles / Relevance sort (matching the REST API's existing `sort` default, which was already "score").

### v1.7.2 — 2026-09-22

- **Chat Session Could Fail to Recover After a Server Restart**: If the server restarted while a chat session was open (or during any deploy), the next message correctly rebuilt that session from the saved graph file — but two near-simultaneous requests for the same session (e.g. the main chat panel and the expanded chat modal both firing) could each try to rebuild it at once, corrupting both attempts and surfacing "Session expired and the chat context could not be rebuilt." A single rebuild now runs at a time; a second concurrent request waits for it and reuses the result instead of racing it.

### v1.7.1 — 2026-09-22

- **Query Translation Failure Is No Longer Invisible**: The pre-retrieval "translate to English" step for CJK/non-English questions previously fell back to the untranslated query on failure with no visible sign anything had gone wrong — measured impact when it fires: retrieval nDCG@10 roughly halves (0.393 → 0.230 on real Chinese test questions). It's now surfaced as an inline caveat in the answer, not just a log line.
- **Preferred-PMID Boost (1.5x) Re-Verified on a More Realistic Corpus**: The earlier "the boost barely matters" finding was measured on per-question corpora almost entirely composed of relevant abstracts, which gives any ranking rule little room to differ. Re-ran the same calibration against all 50 questions pooled into one ~518-abstract corpus (so each question's relevant abstracts sit among ~500 distractors) — the boost still barely matters (best-vs-current difference 0.0002 nDCG@10, 95% CI includes zero), just now confirmed on a corpus that actually could have shown otherwise. No change to the shipped constant.

### v1.7.0 — 2026-09-19

- **Hybrid Sparse + Dense Retrieval (BM25 + RRF)**: Chat's text retrieval was pure dense vector search, which cannot separate biomedical symbols that differ by a digit. Measured on a real 200-abstract corpus, a `miR-155` question retrieved 1 of the 7 abstracts discussing it (a miR-122 review ranked 2nd); a `miR-34a` question retrieved none. Added a BM25 arm with a biomedical tokenizer that canonicalises entity surface forms (`miR-155` / `miRNA-155` / `microRNA-155` share one token), fused with the dense arm by Reciprocal Rank Fusion, and weighted toward the sparse arm only when the query actually names a specific identifier — so conceptual questions keep the dense behaviour they need. Measured across 4 entity questions: precision@8 0.188 → 0.844, recall@8 0.106 → 0.637, with the original failing case going from 1 hit to all 7 relevant abstracts. `NETMEDEX_DISABLE_BM25=1` restores dense-only for A/B comparison.
- **Entity Aliases Are Now Indexed**: `GraphRetriever._build_node_index` indexed only each node's display name, which is whichever surface form the source paper happened to use — so a node displayed as `mirna-155` was unreachable by the standard `miR-155`, even though that string was already sitting in its alias set. Aliases (≥3 chars, never overriding another node's primary name) are now indexed too, matching what the anchor-scoring path already did.
- **A Named miRNA No Longer Expands to the Whole Family**: The category-expansion trigger was a plain substring test, so "miRNA-155" matched "mirna" and returned every miR-* node in the network (~120), burying the one entity asked about. Generic family mentions still expand; a mention followed by an identifying number no longer does.

### v1.6.0 — 2026-09-19

- **Strict Citation Grounding for Follow-up Questions (optional)**: New Advanced Settings toggle implementing a two-tier "Hybrid Knowledge Hierarchy" retrieval policy for follow-ups. Tier 1 (core evidence circle): the question is first answered using ONLY the text chunks and graph subgraph tied to the PMIDs your previous reply already cited — the graph side is a strict attribute filter (never hops onto a neighbor introduced only through a different PMID's edge). Tier 2 (index-wide circle): only entered when tier 1's evidence is empty or the model itself determines it's insufficient; widens to the full indexed corpus/graph and the reply explicitly names any newly-cited PMID via a code-generated (not LLM-trusted) disclosure sentence. If even the full index has nothing, a fixed refusal is returned directly, bypassing the LLM so the wording is guaranteed. Off by default (existing follow-up behavior is unchanged); has no effect on a session's first question. Live-verified across a 3-turn conversation: a follow-up answerable from the prior turn's own citations stayed within them, while a follow-up needing a different, previously-uncited miRNA correctly widened the search and disclosed the new PMID.

- **"Which Entities Are Related to X" Now Recognized as a Listing Request**: `_detect_entity_listing_request` (`chat.py`) required "list"/"which are"/"有哪些" etc. immediately adjacent to the trigger word, so a very natural phrasing like "哪一些miRNA與HCV引發的肝癌有關" (or its English equivalent, "Which miRNAs are associated with HCV-induced liver cancer?") fell through to the normal LLM reasoning path instead of the deterministic full-list response — live-found while verifying the v1.5.19-21 fixes end-to-end on a real HCV/liver-cancer query with 109 real miRNA nodes in the graph: only 8 surfaced via the normal path's top-k retrieval, versus all 109 (with PMIDs, plus the v1.5.18 completeness caveat) via the intended listing path. Added "哪些"/"哪一些" as direct triggers and a `which...are` regex for English phrasing where the entity noun sits between the two trigger words.

- **Query Translation No Longer Drops Other Named Biological Families**: The AI Search query translator's "keep miRNA/lncRNA explicit" rule only covered non-coding RNAs — a query mentioning a different narrow, well-known family (interleukin/cytokine, chemokine, circRNA, Toll-like receptor, matrix metalloproteinase, monoclonal antibody, kinase inhibitor, statin) risked having that term silently dropped by the same "keep only 2-3 specific entities" simplification rule that (correctly) drops truly generic words like "signaling" or "pathway" — losing the term before the PubMed search even runs, a layer earlier than the miRNA/lncRNA graph-retrieval issues fixed in v1.5.19/20. Generalized the rule to cover these families explicitly. Live-verified: "via an interleukin", "via a chemokine", and "via circRNA" all now survive translation as explicit OR-expanded search terms.

- **Same Category-Matching Fix Extended to lncRNA**: The v1.5.19 fix (category-matched query entities getting neither score nor gate credit unless literally named) applied equally to long non-coding RNAs — "lncRNA" has no reliable naming convention the way "microRNA" does (`MALAT1`, `GAS5`, `H19` look like ordinary gene symbols), so it needed its own detection: a curated list of well-known lncRNAs plus the `LINC*`/`SNHG*` prefixes and `-AS<n>` antisense suffix, wired into the same `find_relevant_nodes`/`_extract_query_anchors`/`find_query_anchor_nodes` category-expansion points already used for miRNA/SNP. Live-verified on a different real topic (curcumin/apoptosis/breast cancer): Chat's answer now names two specific lncRNAs (`LINC00691`, `H19`) with real PMID citations instead of omitting them.

### v1.5.19 — 2026-09-18

- **Category-Matched Query Entities (e.g. a Specific miRNA) No Longer Silently Dropped from Chat's Answer**: Live-reproduced: "Resveratrol ... via microRNA ... Neuroinflammation ... Alzheimer's Disease" built a graph with real, evidenced miRNA edges, yet Chat's answer never mentioned any specific miRNA. Root cause: a query naming a generic category ("microRNA") only resolves to a specific node (e.g. `miR-155`) through category expansion, not literal name match, so that node's edges got neither the query-anchor score boost nor endpoint-alignment gate credit anywhere in path retrieval — leaving them systematically outranked by the many edges of literally-query-matching hub entities (Resveratrol, Alzheimer's disease) with far more corroborating literature. Fixed across the three places this mattered: `_score_path_anchors` and `_classify_path_gate` (`graph_rag.py`) now credit a "novel" category-expanded match the same way a literal one is credited, and `_select_gated_candidate_paths` gained a small, bounded rescue for a category-matched entity's fact that still ranks just outside the top-20 cut. Verified live end-to-end: Chat's answer now cites `miR-155 —[promotes]→ neuroinflammation` (PMID:35008513) directly in Layer 1 and builds a concrete, correctly-hedged Layer 3 hypothesis naming it specifically.

- **Fixed: Entity-Listing Chat Answers Overclaimed Completeness**: Asking Chat "list all miRNAs linked to X" always claimed the result was "a complete list," compiled purely from surviving graph nodes. For networks built with Semantic Analysis or Relation-Only edges, an entity mentioned in the abstracts but never assigned an extracted relationship is removed as an isolated node during the build (see v1.5.17), so that claim was often inaccurate. The response now checks how the network was built and adds a caveat for Semantic Analysis / Relation-Only graphs; co-occurrence-built graphs (which connect every mentioned entity pair, so no such gap exists) keep the original wording.

### v1.5.17 — 2026-09-18

- **Fixed: Query Entities Missing Entirely When Built with Semantic Analysis (LLM)**: Reported live — a query mentioning "microRNA" produced a graph with zero miRNA nodes, even though PubTator3 correctly tagged 12 distinct miRNAs across the retrieved articles. Root cause, confirmed by rebuilding the exact query end-to-end: "Semantic Analysis (LLM)" (the default edge method) has the LLM extract only a handful of the relationships it judges most meaningful per article rather than an edge for every mentioned entity — any entity the LLM doesn't pick ends up with zero edges and is stripped as an isolated node during the build itself, before the graph is even saved (a different, earlier failure point than the v1.5.16 rendering-cap fix below, which only helps entities that already have an edge). Query-relevant entities left isolated by semantic extraction now get a fallback "co-mentioned" edge to another query-relevant entity from the same article, rendered with a distinct dashed style so it's never confused with a real LLM-extracted claim. Verified live: all 9 previously-isolated miRNA nodes in the reproduction gained a fallback edge and now survive.
- **Anchor Protection Generalized to SNPs / Genomic Variants**: The same query-relevance matching used above now also recognizes generic terms like "SNP" or "polymorphism" and expands them to every `rs`-prefixed variant node, and matches on node aliases too.

### v1.5.16 — 2026-09-18

- **Fixed: Low-Frequency Query Entities Silently Pruned from the Visualized Graph**: Reported live — a query mentioning "microRNA" built a network where a dominant chemical/disease pair (co-occurring in all 50 retrieved articles) crowded out `miR-124`, which co-occurred in only 1-2 articles and had edge weight 1. Root cause: the automatic rendering safety caps (`MAX_INTERACTIVE_EDGES = 3000`, `MAX_INTERACTIVE_NODES = 1500`, both exist purely to keep the browser responsive on large networks) ranked purely by global edge weight/degree with no notion of relevance to the original search query, so a rare-but-searched-for entity like miR-124 was cut, and the resulting degree-0 node then disappeared entirely. Query-relevant nodes/edges (matched by name, or by category for generic terms like "microRNA" expanding to every miR-*/let-7* node) now get first claim on both caps' budgets, with the remainder still filled by global rank as before — the total rendered edges/nodes never exceeds the existing caps, so the original browser-safety guarantee is unchanged. Does not affect the user-adjustable weight-cutoff / node-degree sliders, which still work exactly as before.

### v1.5.15 — 2026-09-18

- **Chat Model Override / Verifier Provider Now Default to the Main Model**: With "Same as main provider" selected (Verifier Provider's default state), the Model dropdown showed a bare "Custom..." placeholder until you manually clicked Refresh — even though the underlying resolution already silently reused the main LLM Configuration's model in that case. It now shows that model up front. Only reacts to the section's own Provider dropdown, so a model you deliberately pick while staying on the same provider is never overwritten by background changes elsewhere.

### v1.5.14 — 2026-09-18

- **"Show Communities" Toggle Now Explains When There's Nothing to Show**: Community detection (Louvain) silently did nothing when it found at most one community for the current network — no error, no visual change, so the toggle looked broken with zero indication of why. A small status line now appears under the toggle in that case ("Only one community detected in this network — nothing to group"), added as a fully separate, observation-only callback that cannot affect graph rendering itself.
- **Fixed: Duplicate `CYTO_STYLESHEET` Definition Silently Discarded Edge Styling**: `webapp/utils.py` defined `CYTO_STYLESHEET` twice; Python kept only the second, which was missing the green/red edge coloring for activating vs. inhibiting relations and the dashed-line styling for node-type edges — dead code since a March 2026 refactor. Merged back into a single definition with all rules restored.

### v1.5.13 — 2026-09-18

- **Fixed: "Same as Main Provider" Failed to Find Models for .env-Configured Keys**: The "Refresh available models" button in Chat Model Override / Verifier Provider only reused whichever key was typed into the matching provider's field in the Advanced Settings form -- if you never typed a key there because you rely on a server-side `.env` variable (e.g. `OPENAI_API_KEY`) instead, "Same as main provider" silently had no key to use and reported "No models found." It now falls back to the same per-provider environment variable resolution Submit-time initialization already uses, so it works regardless of how that provider's credential is configured.

### v1.5.12 — 2026-09-18

- **Local-Model Semantic Analysis: Default Concurrency Raised from 1 to 2**: Live-measured on a single-GPU Ollama endpoint (gpt-oss:120b, 8 articles): `workers=1` took 734.8s, `workers=2` took 599.0s with 0 timeouts -- a real but modest ~19% speedup (not ~2x, since most single-GPU local setups don't have genuine parallel generation capacity). A safe, no-downside default bump; `NETMEDEX_SEMANTIC_WORKERS` remains available for operators with a batched vLLM/SGLang backend who have real concurrent capacity to spend.

### v1.5.11 — 2026-09-17

- **Fixed: Active LLM Banner Didn't Reflect an Unsaved Model Change**: The "🟢 Active: Provider / Model" banner at the top of Advanced Settings only checked whether the selected *provider* differed from the one actually loaded, not the *model*. Picking a different model in the dropdown (without clicking Submit or Verify Connection) still showed the old model as "Active" with no indication anything had changed. The banner now also detects a model mismatch and switches to the same "🟡 ... selected — click Submit or Verify Connection to activate" pending state used for provider changes.

### v1.5.10 — 2026-09-17

- **Close Button at the Bottom of Advanced Settings**: The panel has grown a lot recently (Chat Model Override, expanded Verifier Provider) and only had a close button at the top. Added a second "Close" button at the bottom so you don't have to scroll back up after configuring settings further down the panel.

### v1.5.9 — 2026-09-17

- **Simplified & Fixed: Verifier Provider and Chat Model Override**: Both sections now share the same lightweight pattern — a provider dropdown defaulting to "Same as main provider" plus a model dropdown (with a "🔄 Refresh available models" button and a "Custom..." fallback). An API key field only appears when you actually pick a provider different from your main one; a Base URL field only appears for Local Ollama. Also fixes a real gap in the Verifier Provider: it previously only worked if a different provider's key happened to already be set as a server-side environment variable, silently falling back to the main provider otherwise with no on-screen indication. Both sections now correctly reuse your already-entered main-provider key when left at "Same as main provider", and accept a dedicated key when you pick a genuinely different provider.

### v1.5.8 — 2026-09-17

- **Chat Model Override Now Fetches Real Available Models**: The "Chat Model Override" model field was a plain text box. It's now a dropdown with a "🔄 Refresh available models" button that queries the selected provider's actual API (reusing the same `get_openai_models`/`get_gemini_models`/`get_groq_models`/`get_anthropic_models`/`get_openrouter_models` methods, and the NVIDIA/Local Ollama HTTP calls, that the main LLM config already uses) and lists real model IDs to pick from. A "Custom..." option is still available for typing an arbitrary model name.

### v1.5.7 — 2026-09-17

- **Chat No Longer Silently Caps the RAG Corpus at 50 Abstracts**: When Chat auto-initializes without a manually-selected sub-network, it indexed only the top 50 abstracts (by citation weight) into Hybrid RAG, regardless of how many articles the network was actually built from (e.g. 200). Every question for the rest of that conversation could only ever retrieve from those 50 -- the rest were permanently unreachable, not just under-prioritized. Retrieval itself already re-runs a fresh vector search per question (`ChatSession.send_message` uses the current message's own text, not the first question's), so this was purely an indexing-time cap, not a "stuck on the first question" issue. Removed -- Chat now indexes every abstract in the built network, matching `_rebuild_chat_session_from_graph`'s existing (uncapped) behavior.

### v1.5.6 — 2026-09-17

- **Chat Model Override in the Web UI**: Advanced Settings gains a "Chat Model Override (optional)" section — a checkbox toggle plus provider/API key/model/base-URL fields. Left off (the default), Chat generation continues to reuse the same model/settings used to build the network, exactly as before. Enable it to answer questions with a different, usually stronger model while keeping network construction on your regular (e.g. cheaper or local) provider. Brings the FastAPI bridge's v1.5.5 `chat_provider`/`chat_model` split to the main web app.

### v1.5.5 — 2026-09-17

- **Separate Model for Graph Building vs. Chat Generation**: `BridgeConfig`/`SessionConfigModel` (FastAPI bridge and `chat_bridge.py`) now accept optional `chat_provider`/`chat_api_key`/`chat_model`/`chat_base_url` fields. Left unset, Chat generation reuses the same model used for graph-building semantic edge extraction (unchanged default behavior). Set them to use a different, more capable model only for the less-frequent, synthesis-heavy Chat step, while keeping the per-article extraction step on a cheaper model — live-tested extraction-quality comparisons showed this split is safe: once the v1.5.4 evidence-field bug was fixed, a cheap extraction model (`gpt-4o-mini`) scored within ~4-8 percentage points of pricier models on claim-safety pass rate, while Chat-time synthesis depth is where model tier actually matters most.

### v1.5.4 — 2026-09-17

- **Semantic Extraction: Missing Evidence Field Fixed**: `_build_compact_retry_prompt` in `semantic_re.py` — the fallback prompt used when the first extraction pass returns no parsable relations — omitted the `evidence` field from its output schema entirely, so any relation recovered only through this path could never carry a supporting quote, guaranteeing it would fail `graph_rag.py`'s claim-safety gate regardless of extraction accuracy. Found live: `gpt-5.6` models triggered this fallback far more often than `gpt-4o-mini` in the same test (more first-pass refusals/malformed responses), so their extracted relations disproportionately lacked evidence. `evidence` is now required and explicitly emphasized in all three extraction prompts (initial, coverage, compact-retry). Verified live: the same `gpt-5.6-luna` session that previously skipped Layer 3 entirely ("insufficient evidence") now produces a full, correctly-cited 3-step causal chain.

### v1.5.3 — 2026-09-17

- **Single-Hop Directional Edges No Longer Wrongly Discarded**: Found via a live local-vs-cloud Layer 3 comparison — a direct edge traversed "backwards" relative to its recorded source/target (e.g. the query anchored on the target node) was being discarded outright, even with high-confidence, quote-aligned evidence. `GraphRetriever._format_path` now states such edges in their true recorded direction instead of the traversal order, and the gate no longer disqualifies a single hop for this reason (multi-hop chains still require direction-consistent hops, since composing "A causes B causes C" only makes sense if each hop actually flows that way).
- **LLM-Configuration Fix: Provider Switch No Longer Leaves a Stale Model Name**: `LLMClient.initialize_client()` reset the API base URL when switching providers but not the model — so a client that auto-initialized as `local` (e.g. `LOCAL_LLM_MODEL=gpt-oss:120b`) and was then asked to use `openai` without an explicit model kept sending the Ollama model tag to OpenAI's API, 404ing every request. Found live via the FastAPI bridge. Model now resets to the new provider's default under the same conditions as the base URL.
- **Local-Model Time Estimate**: The "this may take 2-3 seconds per article" message during semantic network construction was calibrated for small/cloud models; a 120B local model measured ~90s/article in testing. The estimate now widens automatically for the `local` provider.

- **Layer 3 Diagnostic Logging**: `GraphRetriever` now logs whether each chat turn actually has a directional (mechanistic) edge to reason over, so a thin/duplicate-feeling Layer 3 can be attributed to its real cause (usually a `co-occurrence`-only graph) instead of guesswork.
- **In-Chat "Switch to Semantic Analysis" Nudge**: When a turn has no directional edges to reason over and the network wasn't already built with Semantic Analysis, Chat now appends an inline suggestion to rebuild with that edge method — instead of relying on the user to notice Layer 3's own in-text skip message.
- **Faster Failure When No LLM Is Configured**: Selecting Semantic Analysis without a configured LLM key used to fail only *after* the full PubTator literature search completed. The check now runs immediately, before the search starts.
- **Cross-Literature Conflict Detection**: When two PMIDs report opposite regulatory direction for the same edge (e.g. one says "inhibits", another "activates"), the graph context now carries an explicit `{CONFLICT: ...}` marker and Layer 3 must report both sides as an unresolved **Literature Conflict** instead of silently picking one.
- **Local-Provider Chat Token Budget**: Raised the local-model (Ollama) chat completion budget from a flat 2500 tokens to 4000 for regular turns — the old cap frequently truncated Layer 3's evidence table before its Weakest Link / Testable Prediction / Suggested Validation fields, making it read like a rehash of Layer 2.
- **Edge Construction Method Default Changed to Semantic Analysis**: The Edge Construction Method dropdown now defaults to `Semantic Analysis (LLM)` instead of `Co-occurrence`, so Chat's Layer 3 (Causal Biomedical Mechanism) has directional evidence to reason over out of the box. This was previously left as `Co-occurrence` to avoid surprising users with the extra per-article LLM latency, but that's already surfaced via a live per-article progress bar (with an upfront "~2-3 seconds per article" estimate) during network construction, so the tradeoff is visible rather than a silent wait. `Co-occurrence` remains available and is still the right choice before an LLM API key is configured (semantic analysis fails fast with a clear "configure your API key" message if selected without one).

### v1.5.1 — 2026-09-13

- **Type-Constrained Biomedical Acronym & MeSH Standardisation**: Integrated `BIOMEDICAL_ACRONYM_MAP` and MeSH CUI lookup into `normalize_knowledge_graph` to expand common medical acronyms (e.g., `RA` in Disease ➔ `rheumatoid arthritis`, `RA` in Chemical ➔ `retinoic acid`) while protecting Gene, Mutation, and SNP nodes.
- **Cytoscape Canvas Height Stability**: Implemented `cy_container_visibility` to enforce container height (`800px`), preventing inline style overrides from collapsing the Cytoscape graph canvas to `0px` during layout transitions.
- **Diskcache WAL Checkpoint Safeguard**: Added SQLite WAL checkpoint (`PRAGMA wal_checkpoint(PASSIVE)`) prior to graph restoration callbacks, preventing SQLite WAL accumulation from blocking progress updates.
- **LLM Error Log Sanitisation & UI Animations**: Applied error message sanitisation before logging LLM exceptions to prevent API key exposure in log outputs, and enhanced progress bars with staged pacing delays.

### v1.5.0 — 2026-09-09

- **FastAPI Bridge Memory Reclamation & TTL**: Added automated LRU eviction and time-based expiration (default 2 hours) to `_SessionStore`, preventing unbounded RAM consumption during high-throughput or programmatic API runs.
- **GraphBuilder Lifecycle State Protection**: Locked graph builder mutation states (`_is_built`) to prevent destructive re-pruning on duplicate `build()` calls and guard against weight corruption from post-build additions.
- **Dependency & Environment Hardening**: Added explicit dependency verification for optional semantic extractors, graceful context-length exceeded error translation in Chat, and $10^{-9}$ floating-point tolerance in NPMI calculations.

### v1.4.0 — 2026-07-31

- **Relation-Direction Verification (optional 2nd LLM)**: New opt-in Advanced Settings toggle adds a second verification pass over directional semantic edges (e.g. `inhibits`, `upregulates`), checking each against its supporting evidence quote and downgrading unconfirmed directions to a neutral `associated_with` rather than dropping them. Pick a verifier provider independent from your main LLM for the best error-catching odds.
- **Numeric-Artifact Node Filter**: Defensively rejects graph nodes whose resolved display name is purely numeric (an occasional PubTator3 upstream NER artifact), preventing garbage entities from surfacing as node/edge endpoints.

### v1.3.6 — 2026-06-29

- **Deterministic ChromaDB Retrieval**: Stabilized vector retrieval result ordering for reproducible RAG outputs when candidate scores tie.

### v1.3.5 — 2026-06-28

- **Deterministic 2-Hop Traversal**: Stabilized 2-hop path traversal ordering for reproducible graph reasoning results.

### v1.3.4 — 2026-06-22

- **Version Alignment**: Corrected remaining version strings in `README.md`, `DEPLOYMENT.md`, `DOCKERHUB_OVERVIEW.md`, and the sidebar UI to align with release `v1.3.4`.

### v1.3.3 — 2026-06-22

- **LLM Provider UI & Local Models**: Support for local model configuration and provider UI improvements with session isolation.
- **Offline Cache Support**: Pre-downloads tiktoken BPE cache in the builder stage to support air-gapped container environments.
- **Defensive Safeguards**: Normalization toggle is automatically disabled when no LLM is configured.
- **Config & Data Cleanups**: Redacted internal development variables, expanded `.env.example` to templates for all 7 providers, and excluded Pediatric CNS data from GitHub and Docker builds.

### v1.3.2 — 2026-06-01

- **Search Nodes @Type Syntax**: Type `@Gene`, `@Disease`, `@Gene:gut`, or `keyword, @Gene` in Search Nodes to highlight, filter, or path-search by biological entity type. Top-N anchor selection uses PMID literature count. Unmatched keywords are silently skipped.
- **Chat Download History Fix**: Download now exports the full unbounded message log, matching what the user sees in the UI chat panel.
- **Search Nodes Tooltip**: Improved info tooltip with @Type usage guide, anchor/path-node color legend, and silent-skip behaviour note.

### v1.3.1 — 2026-06-01

- **WAL Hang Fix**: Checkpoint diskcache SQLite WAL before each `initialize_chat()` run, preventing accumulated writes from blocking `set_progress()` and causing the Chat panel to appear permanently stuck.
- **Adaptive Chat Response Modes**: System prompt now selects response format based on question type — Compact Mode for simple factual queries, Layer 2 skip conditions to avoid empty structured blocks, and adaptive Layer 5 question count (3 for broad analyses, 1 for focused follow-ups, none for Compact Mode).

### v1.3.0 — 2026-05-30

- **Anthropic API Integration**: Full native support for Anthropic Claude models (e.g., `claude-3-5-sonnet`, `claude-3-opus`) as a core LLM provider in both the web application (Advanced Settings UI) and CLI/API interfaces.
- **Advanced LLM Settings & Customization**: Rewrote LLM initialization and configuration parsing (`llm.py` and `advanced_settings.py`) to support multi-provider environments, dynamic testing of connection status for Anthropic/OpenAI/Gemini/Groq/NVIDIA NIM, and direct environment configuration saving to `.env`.
- **CJK / Universal Translation Robustness**: Strict universal language requirements inside prompts for non-English users, enforcing CJK output generation for all headers, labels, and structured segments.
- **Token Usage & Cost Analysis**: Added complete documentation for cost calculation per pipeline stage (`docs/token_cost.md`), including strategies for cost minimization using lighter models or co-occurrence graphs.
- **Biomedical RAG Platform Comparisons**: Published comparative analysis documentation against MRTKG (`docs/NetMedEx_vs_MRTKG_comparison.md`) describing architectural advantages.

### v1.2.8 — 2026-05-25

- **Groq API Provider**: Dynamic model list fetching, connection testing, and server-side `.env` saving for Groq models (preset Llama 3.3, Llama 3.1, Mixtral, Gemma 2, and Custom).
- **Query Filtering**: Automatically appends publication-type exclusion tags (e.g., `NOT "Editorial"[pt]`) to free-text queries, filtering out non-research articles.
- **Suggested Questions**: Refined the format to use specific concepts from context rather than placeholders (X/Y), and expanded parser to handle bare `Q1:` formats.
- **Modal ID Suffixing**: Prevents ID conflicts when rendering chat components in Modal dialogs.
- **Test Suite Pass**: Restored all historical test data files and corrected LLM mock signatures to restore a 100% success rate (49/49 passed).

### v1.2.7 — 2026-05-21

- **Graph Lag Fix**: Server-side rebuild timing logs added; large graphs (>700 visible nodes) now use Cytoscape `preset` layout to skip a redundant client-side fCoSE pass after server-side layout.
- **Graph Loading Spinner**: A `dcc.Loading` overlay appears while the server-side graph rebuild callback runs, eliminating the blank-graph gap after Search completes.
- **NVIDIA NIM in All Callbacks**: Shared LLM initialisation helper ensures NVIDIA NIM is correctly wired into Search pipeline, auto-Chat, manual Chat, and session-rebuild paths (previously fell through to Local Ollama).
- **Non-English Search Gate**: Non-English queries now require an active LLM client to proceed; the final translated PubTator query is logged. Previously, CJK/Korean queries could reach PubTator untranslated when no LLM was configured.
- **PubTator Sort Consistency**: Page-1 search now passes the selected sort parameter, matching subsequent pages and eliminating duplicate/missing PMIDs across pagination.
- **PMID Deduplication**: PMIDs are deduplicated (order-preserving) before annotation fetch; a warning is emitted when parsed article count is significantly below `max_articles`.
- **Lazy Session Rebuild**: After a server restart, the Chat send-message callback reconstructs `ChatSession` from the persisted `G.pkl` instead of showing "session expired".
- **Chat Indexing Diagnostic**: Preflight log reports `selected_nodes`, `selected_edges`, `pmids`, and `abstracts_matched/total` before indexing. Indexing summary (`📊 N abstracts · M nodes (mode)`) displayed in status bar.
- **Semantic RE Timeout**: LLM timeout reduced 180 s → 90 s; per-article hard timeout of 300 s added; rate-limit retry progress reported in UI.
- **Node-Degree Debounce**: Number input fires graph rebuild only on Enter/blur, preventing per-keystroke rebuilds.

### v1.2.6 — 2026-05-15

- **5-Layer Evidence Reasoning Framework**: Chat responses are now structured into five layers — (1) Evidence-Based Answer with direct PMID citations per claim and `[Human]`/`[Animal/In vitro]` labelling; (2) Association / Speculative Inference with structured hypothesis blocks (graph path, per-edge PMIDs, path confidence, why speculative); (3) Causal Biomedical Mechanism with directional causal chain, polarity, evidence table, weakest link, and testable prediction (only when directional edges exist); (4) Final Integrated Summary with inline PMIDs; (5) Suggested Follow-up Questions.
- **Anti-Hallucination Core Principles**: 8 hard rules enforced at prompt level — never hallucinate PMIDs, never convert co-occurrence into regulation, edge-level citation required, strict layer separation, causal language (`inhibits`/`activates`/`drives`) restricted to Layer 3, speculative language mandate for Layers 2–3, species distinction mandatory, no external knowledge.
- **Per-message Language Detection**: Response language now follows each individual user message (English fallback for unrecognized scripts). Removes session-level language lock that forced non-English replies even for English questions.
- **Rolling History with Memory Compression**: Conversation history uses a sliding window (`max_history=3 pairs`). Aged-out turns are compressed into a structured memory buffer (stripped of tables, mermaid, layer headers, bold sub-labels) and re-injected as a system message each turn, preserving long-term context without token bloat.
- **Chat→Graph Highlighting**: 2-hop paths sync to Graph panel — bridge nodes glow gold, inferred edges render as dashed orange.
- **Dijkstra Shortest Path in Search Nodes**: Enter 2+ node names (comma-separated) to highlight the strongest-evidence path between them. Works in both the webapp and exported HTML.
- **CUI-based Node Deduplication**: Nodes sharing the same MeSH ID (e.g. `"hcv"` and `"hepatitis c virus"`) are now merged in the normalization step.
- **Search Nodes False-Positive Fix**: Segment-aware matching prevents short queries (e.g. `ID1`) from matching unrelated nodes (e.g. `COVID-19`).

### v1.2.4 — 2026-04-30

- **NVIDIA NIM Support**: Added NVIDIA NIM as a fifth LLM provider (alongside OpenAI, Google Gemini, OpenRouter, Local Ollama). Supports both cloud NIM (`integrate.api.nvidia.com`) and on-premises deployments with preset model catalogue and endpoint fetch.
- **Active LLM Banner**: Advanced Settings now displays the currently loaded server-side LLM provider and model on page load, eliminating ambiguity about which AI engine is active.
- **Collapsible UI Panels**: Search Panel reorganized into three zones — always-visible core fields, collapsible *Search Options* (Sort, PubTator Parameters), and collapsible *Advanced Network Options* (Node Filter, Edge Method, Weighting, Semantic Threshold). Graph tab gains a collapsible *Display Filters* section (Edge Confidence, Visible Node Types, Minimal Degree). Collapse states persist across sessions.
- **AI Search Simplified**: Replaced heavy Alert-box wrapper with a compact inline toggle row, reducing vertical space by ~40 px.
- **Chat Tab Accent**: Chat tab rendered in teal (`#0d9488`) when active for clearer panel differentiation.
- **HOST Environment Fix**: Resolved Conda build-triplet variable conflict that prevented `HOST=0.0.0.0` from loading via `.env`; `dotenv override=True` now uses an explicit absolute path.

### v1.2.3 — 2026-04-29

- **Collapsible Sidebar**: Toggle button collapses/expands the entire left sidebar; state persists via `localStorage`.
- **Search History**: Query history chips appear below the search box for one-click re-execution of recent queries (up to 8 entries, stored locally).

### v1.2.2 — 2026-04-28

- **Co-occurrence Edge Styling**: Dashed lines visually distinguish co-occurrence edges from solid semantic edges.
- **LLM Settings Persistence**: Advanced Settings values (provider, model selection) survive page reload via `localStorage`.
- **Save to .env**: Button to write LLM configuration back to the server `.env` file (requires `NETMEDEX_ALLOW_WEB_ENV_WRITE=true`).
- **Graph Empty State**: Friendly placeholder shown in the Graph Panel before any search is run.

### v1.2.1 — 2026-04-27

- Security hardening: HMAC-signed session tokens, path traversal prevention.
- Rate-limit retry with exponential back-off for PubTator3 API calls.
- Bug fixes: HTML export multi-node search, topological layout node overlap, CJK query translation pipeline.

</details>

---

## 🚀 Getting Started

| Method                                                   | Best for                           | Install                                                                              |
| -------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------ |
| [🐳 Docker](#-web-application-via-docker) *(Recommended)* | Quickest setup — no Python needed | `docker run`                                                                       |
| [💻 Local Install](#-web-application-local)                 | Web UI + development               | `git clone` + `pip install -e .`                                                 |
| [🛠️ CLI](#-command-line-interface-cli)                    | Batch processing & automation      | `pip install git+https://github.com/lsbnb/NetMedEx.git` *(no repo clone needed)* |

---

## 🐳 Web Application (via Docker)

The easiest way to start. No Python installation required.

### Method A: Docker Desktop (Graphical User Interface)

1. Search for **`lsbnb/netmedex`** in the top search bar of Docker Desktop and click **Pull**.
2. Navigate to the **Images** tab, locate `lsbnb/netmedex:latest`, and click **Run**.
3. Expand **Optional settings**:
   - **Host port**: Enter **`8050`** (maps host port 8050 to container port `8050/tcp`).
   - **Container name**: *(Optional)* Enter `NetMedEx`.
4. Click **Run**.

<p align="center">
  <img src="./docs/img/netmedex_docker_desktop.png" width="500" alt="Docker Desktop Container Setup">
  <br>
  <i>Configuring Host port (8050) in Docker Desktop Optional Settings.</i>
</p>

### Method B: Terminal Command Line

```bash
docker run -d -p 8050:8050 --rm lsbnb/netmedex
```

> [!IMPORTANT]
> Open **[http://localhost:8050](http://localhost:8050)** in your browser.

---

## 💻 Web Application (Local)

Requires **Python ≥ 3.11**.

> [!WARNING]
> The PyPI release (`pip install netmedex`) is outdated (≤ v0.3.0). Use the steps below to get the latest version.

### 1. Clone and install

```bash
git clone https://github.com/lsbnb/NetMedEx.git
cd NetMedEx

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
```

### 2. Start the webapp

**Linux / macOS:**

```bash
pip install gunicorn
bash start_webapp.sh
```

**Windows:**

`start_webapp.sh` requires bash and gunicorn, which are not natively supported on Windows. Choose one of the following:

- **Recommended — WSL (Windows Subsystem for Linux):** Install [WSL 2](https://learn.microsoft.com/windows/wsl/install), then follow the Linux steps above inside the WSL terminal.
- **Alternative — `waitress` (runs natively on Windows):**

  ```powershell
  pip install waitress
  $env:NETMEDEX_SESSION_SECRET = python -c "import secrets; print(secrets.token_hex(32))"
  waitress-serve --host=0.0.0.0 --port=8050 webapp.wsgi:application
  ```

> [!NOTE]
> If you encounter encoding errors with non-ASCII content (e.g. Chinese terms) on Windows, ensure your terminal is set to UTF-8: `chcp 65001`.

Open **[http://localhost:8050](http://localhost:8050)** in your browser.

> [!TIP]
> No API key is needed to start. Once the app is running, go to **Advanced Settings** in the sidebar to enter your LLM provider key (OpenAI, Anthropic, Gemini, Groq, etc.). You can also save it permanently to `.env` from within the UI.

---

## 🤖 Hybrid RAG-Powered Discovery

NetMedEx features an interactive **Chat Panel** driven by **Hybrid RAG**, which combines the power of large language models (LLMs) with specialized bio-medical knowledge graphs.

<p align="center">
  <img src="./docs/img/netmedex_architecture_v2.jpg" width="600" alt="NetMedEx Architecture">
  <br>
  <i>Figure 1: NetMedEx Hybrid RAG Architecture combining Text and Graph RAG for chatting with biomedical knowledge.</i>
</p>

### Key Capabilities

- **Full-Text BioC-JSON Ingestion**: Retrieve and analyze the entire article (Methods, Results, Discussion) via PubTator3 API integration.
- **PMID-Based De-duplication**: Automatically consolidates multiple mentions of entities and relations within the same paper to ensure accurate NPMI calculation and knowledge graph stability.
- **Hybrid RAG Chat**: Synthesizes **unstructured text** (abstracts + full-text) and **structured graph knowledge** (paths and neighbors).
- **🧠 Smart 2-Hop Graph RAG**: Deep mechanistic discovery using two-hop traversal with hybrid scoring (NPMI + Confidence + Semantic Relevance).
- **🔬 2-Hop Mechanistic Path Reports** *(v1.2.6)*: When 2-hop paths (A → B → C) are identified, the chat response describes each path in Layer 2 (Speculative Inference) and Layer 3 (Causal Mechanism) — including the graph path, per-edge PMID citations, path confidence score, and directionality. The corresponding bridge nodes and path edges are simultaneously highlighted in the Graph Panel.
- **🔗 Chat→Graph Synchronization** *(v1.2.6)*: 2-hop inference paths automatically highlight back in the Graph Panel — bridge nodes glow gold, inferred path edges render as dashed orange.
- **🛤️ Dijkstra Weighted Shortest Path** *(v1.2.6)*: Enter 2+ node names (comma-separated) in **Search Nodes** to find the strongest-evidence route between them, weighted by NPMI. Available in both the webapp and exported HTML.
- **🧬 sapBERT + CUI-based KG Normalization** *(v1.2.6)*: Two-pass normalization — MeSH CUI-based deduplication (merges abbreviations with their full names, e.g., `"hcv"` → `"hepatitis c virus"`) followed by sapBERT embedding similarity.
- **⚖️ Study-Type Labeling**: Automated distinction between Human clinical data and Animal/Cell-line models.
- **Relation Directionality**: High-resolution arrows indicate the direction of semantic influence (e.g., A → activates → B).
- **Edge Confidence Coloring**: Edges are color-coded (gradient heatmap) based on AI-extracted confidence scores.
- **Dynamic Node Repulsion**: Real-time control of node spacing using the **fCose layout** slider.
- **ChatGPT-Style Chat Experience**: Features an intuitive Chat Panel with **Smart Provenance Links**, **Native Markdown Tables**, and **Suggested Questions**.
- **Natural Language & Universal Translation**: Ask in English, Japanese, Chinese, or Korean! Automatic translation to optimized PubTator3 English syntax.

### Setup AI Engine

1. Obtain an API key from your preferred provider or set up a local/on-premises LLM endpoint.
2. Configure via **"Advanced Settings"** in the web interface or via `.env` file.

Supported LLM providers:

| Provider                | Where to get key                                         | Notes                                    |
| ----------------------- | -------------------------------------------------------- | ---------------------------------------- |
| **OpenAI**        | [platform.openai.com](https://platform.openai.com/api-keys) | Recommended:`gpt-4o`                   |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com)          | Recommended:`gemini-2.0-flash`         |
| **OpenRouter**    | [openrouter.ai](https://openrouter.ai/keys)                 | Access 200+ models via single key        |
| **NVIDIA NIM**    | [build.nvidia.com](https://build.nvidia.com)                | Cloud or on-premises NIM (`nvapi-...`) |
| **Local Ollama**  | —                                                       | Self-hosted, no key required             |

> [!TIP]
> **Connecting to Local / On-premises LLMs:**
>
> - **Linux/Docker**: Use your host IP (e.g., `http://192.168.1.100:11434`).
> - **Windows/macOS (Docker)**: Use `http://host.docker.internal:[PORT]`.
> - **NVIDIA NIM (cloud)**: Base URL `https://integrate.api.nvidia.com/v1`, key starts with `nvapi-`.
> - **NVIDIA NIM (on-prem)**: Set Base URL to your internal NIM server, use any non-empty key value.

---

## 🖼️ Interface & Quick Tour

The workspace follows a logical discovery workflow across three main operational panels.

### 1. Search & Configuration (The Entry Point)

The **Search Panel** is where you define your research scope and configure the AI engine.

<p align="center">
  <img src="./docs/img/netmedex_search_panel_v2.jpg" width="300" alt="Search Panel">
  <br>
  <i>Figure 2: The Search Panel for keyword and natural language querying.</i>
</p>

Click the ⚙️ gear icon in the sidebar to open **Advanced Settings** and configure your LLM provider. This is a crucial first step for enabling semantic analysis.

<p align="center">
  <img src="./docs/img/netmedex_advanced_settings_openai.png" width="300" alt="Advanced Settings">
  <br>
  <i>Figure 3: Configuring the AI Engine (OpenAI or Local) in Advanced Settings.</i>
</p>

<p align="center">
  <img src="./docs/img/netmedex_advanced_settings_llm_dropdown.png" width="300" alt="LLM Dropdown Selection">
  <br>
  <i>Figure 4: Selecting a specific model for local AI processing via the dropdown menu.</i>
</p>

Beyond the LLM provider selection, **Advanced Settings** also controls search scale and graph quality. The **Max Articles** slider can be raised up to 3,000 for comprehensive literature coverage, while **KG Normalization** (sapBERT + MeSH CUI) consolidates entity synonyms — merging abbreviations such as `"hcv"` ↔ `"hepatitis c virus"` — for a cleaner, deduplicated graph.

<p align="center">
  <img src="./docs/img/up2_3000lit.png" width="300" alt="Advanced Settings Max Articles">
  <br>
  <i>Figure 5: Advanced Settings — Max Articles scaled to 3,000 for large-scale literature mining. KG Normalization (sapBERT + MeSH CUI) merges entity synonyms; Max Edges limits co-mention edges per article to control graph density.</i>
</p>

NetMedEx also exposes a **FastAPI Bridge** (`netmedex_fastapi_server.py`) that wraps the full Search → Network → Chat pipeline as REST endpoints, allowing external applications to integrate biomedical literature discovery without embedding the full stack.

<p align="center">
  <img src="./docs/img/netmedex_search_api.png" width="300" alt="NetMedEx FastAPI Bridge">
  <br>
  <i>Figure 6: NetMedEx FastAPI Bridge — `POST /sessions` builds the search-to-network-to-chat pipeline from a gene list and returns a session ID; `POST /sessions/{session_id}/ask` performs multi-turn Hybrid RAG queries against the indexed graph. The bridge supports all six LLM providers and both co-occurrence and semantic edge methods.</i>
</p>

Users can also upload previously downloaded PubTator format files for re-analysis, or restore a previously exported **Graph File** (`.pkl`) to skip re-processing entirely.

<p align="center">
  <img src="./docs/img/netmedex_search_Pubtator.png" width="300" alt="PubTator Search">
  <br>
  <i>Figure 7: Uploading PubTator files for re-analysis, or a Graph File (.pkl) to instantly restore a saved session.</i>
</p>

> [!TIP]
> **Graph File Restore**: After a time-consuming Semantic Analysis run, export the result as a **Graph (.pkl)** from the Graph Panel, then reload it later via **Search Panel → Source: Graph File (.pkl)**. The full graph state — including all semantic edges, node metadata, and article abstracts — is restored instantly, allowing you to continue adjusting the network and using the Chat Panel without re-running any analysis.

### 2. Graph & Scaffolding (Structural View)

The **Graph Panel** visualizes the co-mention or semantically analyzed network. Users can explore entity relationships using different layouts and community detection algorithms, then select a sub-network as the context for AI-powered chat in the next step.

<p align="center">
  <img src="./docs/img/Figure%208_Graph_panel_network.png" width="800" alt="Graph Panel Network">
  <br>
  <i>Figure 8: Case study: A disease-gene-chemical co-mention network visualized in NetMedEx, showing semantic-level relationships between genes, diseases, chemicals, and species.</i>
</p>

The sidebar shows **Network Statistics** for the visible graph:

- 📄 **Articles** — unique PubMed articles linked to at least one edge. May be lower than the Chat panel count, which also includes isolated nodes without edges.
- 🔵 **Nodes** — number of biological entity nodes currently displayed.
- 🔗 **Edges** — number of co-occurrence or semantic relationship edges.

Each network element carries structured information:

- **Nodes**: Genes, Diseases, Chemicals, and Species.
- **Edges**: Literature co-occurrence or semantic relations. Thicker edges indicate higher frequency/NPMI; **arrows** indicate directionality in semantic mode.
- **Confidence Heatmap**: Edge colors transition from cool to warm based on the extracted confidence score.
- **fCose Node Repulsion**: Use the slider in Graph Settings to adjust network spacing dynamically (10k–100k units).
- **Clusters**: Use **Community Detection** to group related concepts automatically using the Louvain method.

<p align="center">
  <img src="./docs/img/fCose_topology.png" width="800" alt="fCose Layout Topology">
  <br>
  <i>Figure 9: The fCose force-directed layout with node repulsion control, providing dynamic spacing adjustment for optimal network readability.</i>
</p>

<p align="center">
  <img src="./docs/img/Show%20Communities.png" width="800" alt="Show Communities">
  <br>
  <i>Figure 10: Automated community detection for functional clustering using the Louvain algorithm.</i>
</p>

> [!TIP]
> **Search Nodes — Shortest Path** *(v1.2.6)*: Type two or more node names separated by commas in the **Search Nodes** field (e.g., `Piezo1, neoplasms`) to compute the **Dijkstra weighted shortest path** between them. The strongest-evidence route is highlighted: anchor nodes in orange, bridge nodes in teal, and path edges as thicker orange lines. If no path exists, the panel falls back to standard neighbor highlighting. The same feature is available in exported HTML files.

<p align="center">
  <img src="./docs/img/Search_nodes.png" width="800" alt="Dijkstra Shortest Path in Search Nodes">
  <br>
  <i>Figure 11: Dijkstra weighted shortest-path result in Search Nodes — anchor nodes highlighted in orange, bridge nodes in teal, path edges rendered as thicker orange lines against a dimmed background.</i>
</p>

Hold **Shift** and click to select nodes and edges, isolating a sub-network as the context for Hybrid RAG chat in the next step.

<p align="center">
  <img src="./docs/img/Figure%2010%20Selecting%20a%20sub-network.png" width="800" alt="Selecting a Sub-network">
  <br>
  <i>Figure 12: Selecting a sub-network by holding the Shift key to isolate relevant nodes and edges as the base for Hybrid RAG to chat with.</i>
</p>

The network can be exported in several formats:

| Export Format                  | Description                                                                                                                                                  | Re-importable?                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| **HTML**                 | Interactive visualization for browsers ([example](https://htmlpreview.github.io/?https://github.com/lsbnb/NetMedEx/blob/main/docs/demo_html.html))              | ❌                                         |
| **XGMML**                | Network file for Cytoscape Desktop ([example](docs/demo.xgmml))                                                                                                 | ❌                                         |
| **PubTator / BioC-JSON** | Raw annotation file ([example](docs/demo_pubtator.biocjson))                                                                                                    | ✅ Re-upload in Search Panel               |
| **RIS (EndNote)**        | Full bibliographic metadata for citation management ([example](docs/ENDNOTE_citations.ris))                                                                     | ❌                                         |
| **Chat History**         | Full chat session as a standalone HTML file ([example](https://htmlpreview.github.io/?https://github.com/lsbnb/NetMedEx/blob/main/docs/demo_chat_history.html)) | ❌                                         |
| **Graph (.pkl)**         | **Full graph state** including semantic analysis results and article abstracts                                                                         | ✅ Restore in Search Panel → "Graph File" |

> [!NOTE]
> **Cytoscape XGMML Export**: The topological graph structure, relation edge data, and structural directionality translate natively to Cytoscape Desktop for third-party graph analysis without information loss.

### 3. Chat & Semantic Insights (Interpretation)

The **Chat Panel** lets you interrogate the selected sub-network in natural language, powered by Hybrid RAG combining graph structure and article abstracts.

**Step 1 — Start the analysis.** After selecting nodes and edges in the Graph Panel, press **"Analyze Selection"** to index the sub-network. The status bar shows the number of articles and nodes being indexed.

<p align="center">
  <img src="./docs/img/hybridchat.png" width="800" alt="Chat Panel with Analyze Selection">
  <br>
  <i>Figure 13: Select nodes/edges in the Graph Panel, then press "Analyze Selection" — the Selection Summary shows the articles, nodes, and edges to be indexed.</i>
</p>

<p align="center">
  <img src="./docs/img/fig12B_indexing.png" width="800" alt="Chat Indexing Diagnostic">
  <br>
  <i>Figure 14: Indexing diagnostics in the status bar — showing abstract count, indexed node count, and indexing mode.</i>
</p>

**Step 2 — Ask questions.** Type any natural-language question about the sub-network. Responses follow the **5-Layer Evidence Reasoning Framework**:

- **Layer 1**: Direct evidence — per-claim PMID citations, `[Human]` / `[Animal/In vitro]` labels
- **Layer 2**: Speculative inference — 2-hop paths (A → B → C) with per-edge PMIDs and path confidence
- **Layer 3**: Causal mechanism — directional chain, polarity, weakest-link evidence, testable prediction
- **Layer 4**: Integrated summary with inline PMIDs
- **Layer 5**: Suggested follow-up questions

<p align="center">
  <img src="./docs/img/Fig11_hybrid_RAG%20CHAT.png" width="800" alt="Hybrid RAG Chat">
  <br>
  <i>Figure 15: Hybrid RAG Chat Panel showing a 5-Layer Evidence Reasoning Framework response with inline PMID citations.</i>
</p>

**Chat→Graph Synchronization** *(v1.2.6)*: When 2-hop paths are identified in a response, the Graph Panel updates automatically — bridge nodes glow gold, endpoint nodes turn blue, and inferred path edges appear as dashed orange lines. Highlights clear when a new **Search Nodes** query is activated.

**Chat History**: All sessions are preserved in the **Chat History** panel (accessible via the **Expand Chat** button). Use the **Download History** button to export the full session as a self-contained HTML file — all 5-Layer responses, inline PMID citations, and Markdown tables are preserved with formatting intact. See a [live demo](https://htmlpreview.github.io/?https://github.com/lsbnb/NetMedEx/blob/main/docs/demo_chat_history.html).

<p align="center">
  <img src="./docs/img/5Layer.png" width="800" alt="5-Layer Evidence Reasoning Framework">
  <br>
  <i>Figure 16: The 5-Layer Evidence Reasoning Framework structure.</i>
</p>

> [!TIP]
> Ask for results as a **Markdown table** — the Chat Panel renders them inline, and they are preserved in the HTML history export.

<p align="center">
  <img src="./docs/img/netmedex_chat_table_mirna.png" width="800" alt="miRNA Relationship Table">
  <br>
  <i>Figure 17: Semantic analysis results rendered as a Markdown table (e.g., miRNA relationships).</i>
</p>

## ⚙️ Batch Processing vs. Interactive Discovery

While the **Web Interface** provides a full "Interactive Discovery" workflow—including dynamic sub-network selection (Shift+Select) and real-time Hybrid RAG chat—the **CLI** and **API** are designed for automated batch processing and static graph construction.

- **Interactive Discovery (Web Only)**: Real-time interaction, dynamic graph filtering, and context-aware chat.
- **Batch Processing (CLI/API)**: Static semantic analysis and high-throughput network generation.

---

<details>
<summary><h2>🛠️ Command-Line Interface (CLI)</h2></summary>

#### Step 1: Search PubMed

```bash
# Search articles by keywords
netmedex search -q '"N-dimethylnitrosamine" AND "Metformin"' --sort score
```

`netmedex search` key options:

- `-q, --query`: Query string.
- `-p, --pmids`: Comma-separated PMID list (alternative to `--query`).
- `-f, --pmid_file`: Load PMIDs from file, one per line (alternative to `--query`).
- `-o, --output`: Output `.pubtator` path.
- `-s, --sort {score,date}`: Sort by relevance (`score`) or newest (`date`, default).
- `--max_articles`: Maximum number of articles to request (default: `1000`).
- `--full_text`: Collect full-text annotations when available.
- `--use_mesh`: Use MeSH vocabulary in output.
- `--ai_search`: Enable LLM-based natural language to PubTator boolean query translation.
- `--llm_provider {openai,google,openrouter,nvidia,local}`: Provider for AI search translation.
- `--llm_api_key`: API key override for selected provider.
- `--llm_model`: Model override for selected provider.
- `--llm_base_url`: Base URL override (primarily for local/OpenAI-compatible endpoints).

Optional: enable AI query translation (`--ai_search`) with the same three providers.

```bash
# OpenAI
netmedex search \
  -q "Find papers about metformin effects in NASH" \
  --ai_search \
  --llm_provider openai \
  --llm_api_key "$OPENAI_API_KEY" \
  --llm_model "gpt-4o-mini"
```

```bash
# Google / Gemini
netmedex search \
  -q "Find papers about metformin effects in NASH" \
  --ai_search \
  --llm_provider google \
  --llm_api_key "$GEMINI_API_KEY" \
  --llm_model "gemini-2.0-flash"
```

```bash
# Local (Ollama / LocalAI / LM Studio OpenAI-compatible endpoint)
netmedex search \
  -q "Find papers about metformin effects in NASH" \
  --ai_search \
  --llm_provider local \
  --llm_base_url "http://localhost:11434/v1" \
  --llm_model "llama3.1"
```

#### Step 2: Build the Network

```bash
# Generate HTML network for browser viewing
netmedex network -i annotations.pubtator -o network.html -w 2 --community

# Generate pickle graph for CLI chat (required for `netmedex chat`)
netmedex network -i annotations.pubtator -o network.pickle -f pickle
```

> [!IMPORTANT]
> The default output format is **HTML**. To use the graph with `netmedex chat`, you **must** specify `-f pickle` explicitly.
> Simply naming the output file `.pkl` is not enough — without `-f pickle`, it will still be written as HTML and `chat` will fail with `invalid load key`.

#### Step 3 (Optional): Semantic Edge Extraction with LLM Providers

Use `--edge_method semantic` to enable semantic relationship extraction.

```bash
# OpenAI
netmedex network \
  -i annotations.pubtator \
  -o semantic_openai.html \
  --edge_method semantic \
  --llm_provider openai \
  --llm_api_key "$OPENAI_API_KEY" \
  --llm_model "gpt-4o-mini"
```

```bash
# Google / Gemini
netmedex network \
  -i annotations.pubtator \
  -o semantic_google.html \
  --edge_method semantic \
  --llm_provider google \
  --llm_api_key "$GEMINI_API_KEY" \
  --llm_model "gemini-2.0-flash"
```

```bash
# Local (Ollama / LocalAI / LM Studio OpenAI-compatible endpoint)
netmedex network \
  -i annotations.pubtator \
  -o semantic_local.html \
  --edge_method semantic \
  --llm_provider local \
  --llm_base_url "http://localhost:11434/v1" \
  --llm_model "llama3.1"
```

You can also omit `--llm_*` flags and configure defaults via `.env` (e.g., `LLM_PROVIDER`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LOCAL_LLM_BASE_URL`, `OPENAI_MODEL`, `GOOGLE_MODEL`, `LOCAL_LLM_MODEL`).

Provider consistency note:

- CLI supports five providers (`openai`, `google`, `openrouter`, `nvidia`, `local`) across `search`, `network`, and `chat`.
- Provider settings are passed by CLI flags or `.env` values; they are not serialized into `.pubtator`/graph outputs automatically.

#### Step 4 (Optional): Hybrid RAG CLI Chat (Search → Network → Chat)

`netmedex chat` uses the pickled graph (`-f pickle`) as Hybrid RAG context and supports the same three providers.

> [!NOTE]
> **First run (pip install only)**: `netmedex chat` uses ChromaDB with the `all-MiniLM-L6-v2` embedding model (~79 MB). This model is downloaded automatically on first use and cached locally — subsequent runs do not require a download. Ensure internet access is available for the initial run.
> The **Docker image** already bundles this model — no download needed.

```bash
# One-shot question
netmedex chat \
  -g network.pickle \
  -q "Summarize key evidence and hypotheses for metformin in NASH." \
  --llm_provider openai \
  --llm_api_key "$OPENAI_API_KEY"
```

```bash
# Interactive mode
netmedex chat \
  -g network.pickle \
  --llm_provider local \
  --llm_base_url "http://localhost:11434/v1" \
  --llm_model "llama3.1"
```

Tips:

- Type `exit` or `quit` to leave interactive mode.
- Use `/clear` to clear chat history.
- Use `/stats` to inspect session statistics.

</details>

---

<details>
<summary><h2>🐍 Package API</h2></summary>

NetMedEx exposes two programmatic interfaces for embedding into Python pipelines or external UIs.

### Embed NetMedEx in Your Own Chat App

If your upstream pipeline finds candidate genes (e.g., top 5 DE genes), you can directly bridge into NetMedEx and keep a conversational session in your own UI.

See example:

- `examples/netmedex_chat_bridge.py`

Minimal flow:

```python
from netmedex.chat_bridge import BridgeConfig, NetMedExChatBridge

cfg = BridgeConfig(provider="google", model="gemini-2.0-flash", edge_method="semantic")
bridge = NetMedExChatBridge(cfg)

bridge.build_context_from_genes(
    genes=["SOST", "LRP5", "TNFRSF11B", "RUNX2", "ALPL"],
    disease="osteoporosis",
)
answer = bridge.ask("What are the strongest evidence links and possible mechanisms?")
print(answer["message"])
```

### FastAPI Bridge (for external chat UIs)

Install API extras and run:

```bash
pip install -e ".[api]"
python examples/netmedex_fastapi_server.py
```

Endpoints:

- `GET /health`: service health check. Never requires an API key.
- `GET /sessions`: list active session metadata.
- `POST /sessions`: build Search -> Network -> Chat context and create a chat session.
- `POST /sessions/{session_id}/ask`: send a question in that session.
- `DELETE /sessions/{session_id}`: release session state.

By default the bridge binds to `0.0.0.0:8000` with no authentication -- fine for a single user
running it on their own machine, but anything else on the same network can also reach it. Set
these environment variables before launching to match your deployment:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NETMEDEX_API_HOST` | `0.0.0.0` | Set to `127.0.0.1` to restrict the bridge to the local machine only. |
| `NETMEDEX_API_PORT` | `8000` | Port to listen on. |
| `NETMEDEX_API_KEY` | unset (no auth) | When set, every route except `/health` requires this value via the `X-API-Key` header or `Authorization: Bearer <key>`. |
| `NETMEDEX_CORS_ORIGINS` | `http://localhost:8050,http://127.0.0.1:8050` | Comma-separated list of browser origins allowed to call the bridge. |
| `NETMEDEX_CORS_ALLOW_CREDENTIALS` | `false` | Whether cookies/credentials are allowed cross-origin. |

For an intranet deployment, set `NETMEDEX_API_KEY` and share it with whoever needs API access.
For a cloud/internet-facing deployment, set `NETMEDEX_API_KEY` **and** put a reverse proxy
(nginx, Caddy, Traefik) in front for TLS -- this application does not terminate HTTPS itself.

Create a session from genes:

```bash
curl -X POST "http://127.0.0.1:8000/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "provider": "google",
      "model": "gemini-2.0-flash",
      "edge_method": "semantic",
      "max_articles": 120
    },
    "genes": ["SOST", "LRP5", "TNFRSF11B", "RUNX2", "ALPL"],
    "disease": "osteoporosis"
  }'
```

Ask in-session:

```bash
curl -X POST "http://127.0.0.1:8000/sessions/<SESSION_ID>/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize strongest evidence and potential mechanisms."}'
```

Framework-agnostic Python client example:

```python
from examples.netmedex_fastapi_client import NetMedExAPIClient

client = NetMedExAPIClient("http://127.0.0.1:8000")
client.create_session(
    config={
        "provider": "google",
        "model": "gemini-2.0-flash",
        "edge_method": "semantic",
        "max_articles": 120,
    },
    genes=["SOST", "LRP5", "TNFRSF11B", "RUNX2", "ALPL"],
    disease="osteoporosis",
)
resp = client.ask("Summarize strongest evidence and potential mechanisms.")
print(resp["message"])
client.close()
```

Reference client file:

- `examples/netmedex_fastapi_client.py`

Integration examples for your own app/chat platform:

```python
# Example A: wrap NetMedEx into your backend service function
from examples.netmedex_fastapi_client import NetMedExAPIClient

def run_gene_chat(genes: list[str], user_question: str) -> str:
    client = NetMedExAPIClient("http://127.0.0.1:8000")
    client.create_session(
        config={
            "provider": "google",
            "model": "gemini-2.0-flash",
            "edge_method": "semantic",
            "max_articles": 120,
        },
        genes=genes,
        disease="osteoporosis",
    )
    try:
        resp = client.ask(user_question)
        return resp.get("message", "")
    finally:
        client.close()
```

```javascript
// Example B: call NetMedEx API from any web frontend (React/Vue/plain JS)
async function askNetMedEx(baseUrl, sessionId, question) {
  const resp = await fetch(`${baseUrl}/sessions/${sessionId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question })
  });
  if (!resp.ok) throw new Error(await resp.text());
  return await resp.json(); // { success, message, sources, ... }
}
```

```text
Example C: recommended lifecycle for multi-turn chat
1) User selects genes/disease in your app.
2) Backend calls POST /sessions once and stores session_id.
3) Each user message calls POST /sessions/{session_id}/ask.
4) On chat end/timeout, call DELETE /sessions/{session_id}.
```

Minimal Web Chat UI (no framework):

```bash
# terminal 1: start FastAPI bridge
python examples/netmedex_fastapi_server.py

# terminal 2: serve static examples folder
python -m http.server 8080 --directory examples
```

Then open:

- `http://127.0.0.1:8080/minimal_chat_ui.html`

Gradio Chat UI:

```bash
# terminal 1: start FastAPI bridge
python examples/netmedex_fastapi_server.py

# terminal 2: launch gradio app
pip install -e ".[ui]"
python examples/gradio_chat_ui.py
```

Then open:

- `http://127.0.0.1:7860`
- In the UI, click `Create Session` first, then ask questions.

</details>

---

## 🛠️ Contribution & Development

NetMedEx is an open-source research initiative. We welcome contributions to our semantic extraction pipeline and UI visualization modules.

### 👥 Authors & Contributors

- **Zheng-Xiang Ye** ([@yehzx](https://github.com/yehzx))
- **Chung-Yen Lin** ([@cylin2022](https://github.com/cylin2022) / [LSBNB](https://github.com/lsbnb))
- **Shu-Hwa Chen** ([@HMSophia](https://github.com/HMSophia))

© 2026 NetMedEx Team. Prepared for submission to GitHub under **cylin2022**.

---

© 2026 LSBNB Lab@ IIS, Academia Sinica, TAIWAN. Refer to [LICENSE](LICENSE) for details.
