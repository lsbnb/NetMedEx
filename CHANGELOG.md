# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
