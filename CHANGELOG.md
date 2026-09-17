# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
