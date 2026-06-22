# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
