# NetMedEx v1.8.1: AI-Powered Biomedical Knowledge Discovery 🧬✨

NetMedEx is an AI-driven platform that transforms biomedical abstracts from **PubTator3** into interactive, actionable knowledge graphs. It bridges the gap between structured networks and unstructured text using a **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** engine powered by graph traversal and semantic vector search.

---

## 🌟 Why NetMedEx?

While other tools simply list entities, NetMedEx **interprets the links**. It provides the scaffolding for discovery, allowing researchers to navigate the complex landscape of genes, diseases, chemicals, and species with AI as their co-pilot.

### 🚀 Core Capabilities

- **🧠 Smart 2-Hop Graph RAG**: Discovers latent mechanistic chains (A → B → C) scored by Hybrid Scoring 2.0 — combining topological NPMI, semantic confidence, and query relevance.
- **🕸️ Interactive Visualization**: Explore co-mention and semantic networks with real-time layout adjustments, community detection, and sub-network selection.
- **⚡ Semantic Extraction**: Automatically identifies relationship types (e.g., *inhibits*, *treats*, *activates*) with calibrated confidence scores and direct evidence sentences.
- **🌐 Universal Translation**: Search and chat in English, Traditional Chinese, Japanese, or Korean. AI handles the translation to optimized PubTator syntax.
- **🐭 Species Differentiation**: Clearly distinguishes human clinical findings from animal/cell-line model results in every AI response.
- **💾 Full Session Portability**: Export your entire research state as a **Graph File (.pkl)** and restore it instantly — no re-analysis required.

---

## 🆕 What's New in v1.8.1

- **Suggested Questions Work Reliably**: Clicking a suggested question could reload the page and drop you back on the Search panel when the model wrote the question in a numbered, non-English format. It now fills the chat box as intended.

### Previous: v1.8.0

- **Explore Large Knowledge Graphs**: Open a graph built from tens of thousands of articles directly from the server, start from its core entities, and grow the view step by step — connect any entity you search to the core entities through its best few-hop paths, or expand a node's strongest neighbours (with Undo).
- **More Reliable Chat**: Fixed "Graph session data not found" when starting a chat, and a crash on graphs with more than ~5,400 nodes.
- **Richer Relation Extraction on OpenAI Models**: The first extraction pass now returns all relations per article instead of just one (about 13 per article instead of 7, at lower cost).

### Previous: v1.7.3

- **Follow-ups Better Remember What You Were Just Discussing**: A follow-up question already re-searches the full index fresh each time — it now also gives a ranking boost to the papers your previous reply cited, so a still-relevant one can resurface instead of relying only on the model's memory of the conversation text.
- **Better Article-Fetch Defaults**: "Max Articles" and "Sort" defaulted to 30 articles / Recency, which could cap a broad search to only the 30 newest matches — sometimes missing the specific mechanism a question asked about entirely. Now defaults to 50 articles / Relevance.

### Previous: v1.7.2

- **More Reliable Recovery After a Server Restart**: If the server restarted while a chat was open, reopening it could sometimes fail with "Session expired" even though the underlying data was fine — two near-simultaneous requests to rebuild the same session could corrupt each other. Only one rebuild runs at a time now.

### Previous: v1.7.1

- **Silent Translation Failures Are Now Visible**: Asking a question in Chinese, Japanese, or Korean translates it to English before retrieval runs. If that translation step failed, search used to quietly fall back to the original-language text with no visible sign anything was wrong — measured impact: retrieval quality roughly halves when this happens. The answer now carries a caveat when it does.

### Previous: v1.7.0

- **Hybrid Sparse + Dense Retrieval**: Asking about one specific symbol (`miR-155`, `EGFR C797S`) used to fail — the embedding knows a text is "about microRNAs" but not *which* one. Chat now fuses BM25 exact-term matching with vector search, and recognises entity name variants (`miR-155` / `miRNA-155` / `microRNA-155`). Measured on a real 200-abstract corpus: precision@8 rose from 0.19 to 0.84, recall@8 from 0.11 to 0.64.
- **Named Entities Resolve by Alias**: A node's display name is whichever form the source paper used, so the standard form you type often existed only as an alias and matched nothing. Aliases are now indexed.
- **A Named miRNA Is No Longer Read as the Whole Family**: Asking about "miRNA-155" returned every miRNA in the network (~120 of them); it now returns the one you asked about, while genuinely generic questions still expand as before.

### Previous: v1.6.0

- **Strict Citation Grounding for Follow-ups (optional)**: A new toggle makes follow-up questions try to answer using only the PMIDs your previous reply already cited first, only widening to the full index when that's genuinely insufficient — and explicitly discloses any newly-cited PMID when it does. Off by default.

### Previous: v1.5.22

- **"Which Entities Are Related to X" Now Triggers the Full List**: A natural phrasing like "which miRNAs are related to X" (or its Chinese equivalent) previously fell through to the normal reasoning path instead of the deterministic full-list response, surfacing only a handful of entities instead of every one in the graph.

### Previous: v1.5.21

- **Query Translation Protects More Named Biological Families**: Beyond miRNA/lncRNA, AI Search now also keeps interleukin/cytokine, chemokine, circRNA, and similar narrow biological families from being silently dropped as "generic" during query simplification.

### Previous: v1.5.20

- **lncRNA Entities Get the Same Fix as miRNA**: The v1.5.19 category-matching fix now also covers long non-coding RNAs (LINC*, SNHG*, -AS antisense genes, plus well-known named lncRNAs like MALAT1/H19/HOTAIR). Live-verified: Chat's answer now names specific lncRNAs with real citations instead of omitting them.

### Previous: v1.5.19

- **Specific miRNAs (and Other Category-Matched Entities) No Longer Silently Dropped from Chat's Answer**: A query naming a generic category ("microRNA") only resolves to a specific graph entity through category expansion, not literal name match -- so that entity's real, evidenced edges were getting outranked by generic hub-to-hub edges before ever reaching the answer, even when the graph itself had exactly the evidence needed. Live-verified: Chat's answer now cites the specific miRNA directly instead of a vague, unsupported guess.

### Previous: v1.5.18

- **Entity-Listing Chat Answers No Longer Overclaim Completeness**: Asking Chat to "list all miRNAs linked to X" used to always say the result was "a complete list." For networks built with Semantic Analysis or Relation-Only edges, entities that were never assigned an extracted relationship are removed as isolated nodes, so the list could genuinely be incomplete — Chat now says so in that case, while co-occurrence-built networks (which have no such gap) keep the original wording.

### Previous: v1.5.17

- **Query Entities No Longer Missing When Built with Semantic Analysis**: A specific miRNA (or other entity you searched for) could be entirely absent from a network built with Semantic Analysis (LLM), because that mode only extracts a handful of "headline" relationships per article rather than an edge for every mentioned entity. Query-relevant entities left without any edge now get a fallback co-mention link so they still appear, shown with a distinct dashed style.

### Previous: v1.5.16

- **Low-Frequency Query Entities No Longer Vanish from the Graph**: A specific miRNA (or any other entity you searched for) mentioned in only 1-2 articles could get silently dropped from a large network, crowded out by dominant nodes appearing in dozens of articles. The graph's automatic rendering safety caps now give query-relevant nodes/edges first claim on the display budget, so they survive even at low frequency.

### Previous: v1.5.15

- **Model Dropdowns Now Mirror Your Main LLM by Default**: Chat Model Override and Verifier Provider now show your main LLM's actual model instead of a bare "Custom..." placeholder when left at "Same as main provider" -- no more clicking Refresh just to see what will actually be used.

### Previous: v1.5.14

- **"Show Communities" Toggle Explains Itself**: When your current network only has one detectable community, the toggle now tells you instead of silently doing nothing.
- **Restored Missing Edge Colors**: Fixed a duplicate stylesheet definition that had been silently discarding green/red edge coloring (activating vs. inhibiting relations) and dashed node-type edges since a past refactor.

### Previous: v1.5.13

- **Fixed "Same as Main Provider" Model Fetch for .env-Configured Keys**: Refreshing available models for Chat Model Override / Verifier Provider now correctly finds your key even if it's set via a server environment variable rather than typed into the browser.

### Previous: v1.5.12

- **Faster Local-Model Network Building**: Raised the default concurrency for local (Ollama) semantic analysis from 1 to 2 -- a live-measured ~19% speedup with no downside on typical single-GPU setups.

### Previous: v1.5.11

- **Active LLM Banner Now Catches Unsaved Model Changes Too**: Previously only a provider change triggered the "🟡 pending — click Submit" warning; picking a different model without submitting looked identical to it already being active. Fixed.

### Previous: v1.5.10

- **Close Button at the Bottom of Advanced Settings**: No more scrolling back to the top to close the panel after configuring settings further down.

### Previous: v1.5.9

- **Simpler, More Reliable Provider Overrides**: Verifier Provider and Chat Model Override now share one lightweight design — pick a model with one click, and only enter a new API key if you actually chose a different provider. Also fixes Verifier Provider silently failing when a different provider's key wasn't already set as a server environment variable.

### Previous: v1.5.8

- **Chat Model Override Dropdown**: The Chat Model Override field now fetches and lists real available models from your chosen provider via a "🔄 Refresh available models" button, instead of requiring you to type an exact model name.

### Previous: v1.5.7

- **Chat Now Sees Your Whole Network, Not Just the Top 50 Abstracts**: Removed a silent cap that indexed only the top 50 (by citation weight) of your built network's abstracts into Chat's RAG when no sub-network was manually selected — the rest were unreachable for the entire conversation. Chat now indexes everything you built.

### Previous: v1.5.6

- **Chat Model Override, Now in the Web UI Too**: Advanced Settings gains an optional "Chat Model Override" — build your network with your regular provider, then answer questions with a different, stronger model. Off by default; existing behavior is unchanged.

### Previous: v1.5.5

- **Split Model for Graph Building vs. Chat**: The FastAPI bridge now accepts an optional separate model for Chat generation (`chat_provider`/`chat_model`/etc.), distinct from the model used to build the network. Build cheaply per-article, then get flagship-quality answers per question — without changing anything if you don't set these.

### Previous: v1.5.4

- **Fixed a Silent Extraction Gap Affecting Newer/Reasoning Models**: A fallback prompt used when semantic extraction's first pass comes back empty was missing its "evidence" field, so relations recovered through it could never be cited as claim-safe. Models that trigger this fallback more often (found with `gpt-5.6`) were unfairly penalized. Live-verified fix: a session that previously abandoned causal-mechanism reasoning entirely now produces a complete, correctly-cited answer for the same question.

### Previous: v1.5.3

- **Better Layer 3 Evidence Recovery**: High-confidence directional edges were being discarded purely because the query happened to anchor on the "wrong" end of the edge. Single-hop edges are now correctly kept and stated in their true direction.
- **Provider-Switch Model Bug Fixed**: Switching LLM providers without explicitly specifying a model no longer risks sending the previous provider's model name to the new one.
- **Realistic Local-Model Time Estimates**: The semantic-analysis progress message now gives a much wider, honest time estimate for large local models.

### Previous: v1.5.2

- **Cross-Literature Conflict Detection**: When two PMIDs report opposite regulatory direction for the same edge (e.g. one says "inhibits", another "activates"), Chat's Layer 3 now surfaces both sides as an explicit, unresolved **Literature Conflict** instead of silently picking one.
- **Sharper Layer 3 Causal-Mechanism Reasoning**: Raised the local-model (Ollama) chat token budget so Layer 3's evidence table, Weakest Link, Testable Prediction, and Suggested Validation fields are no longer truncated mid-response.
- **In-Chat Rebuild Nudge**: When a turn has no directional edges to reason over and the network wasn't already built with Semantic Analysis, Chat now suggests rebuilding with that edge method directly in its reply.
- **Faster Failure When No LLM Is Configured**: Selecting Semantic Analysis without a configured LLM key now fails immediately instead of after the full literature search completes.
- **Semantic Analysis Is Now the Default Edge Method**: New networks are built with `Semantic Analysis (LLM)` by default instead of `Co-occurrence`, so Layer 3's causal-mechanism reasoning has directional evidence to work with out of the box. `Co-occurrence` is still available (and the right pick before an API key is configured) — its symmetric-only edges leave Layer 3 with nothing to reason over.

### Previous: v1.5.1

- **Type-Constrained Biomedical Acronym & MeSH Standardisation**: Integrated `BIOMEDICAL_ACRONYM_MAP` and MeSH CUI lookup into `normalize_knowledge_graph` to expand common medical acronyms (e.g., `RA` in Disease ➔ `rheumatoid arthritis`, `RA` in Chemical ➔ `retinoic acid`) while protecting Gene, Mutation, and SNP nodes.
- **Cytoscape Canvas Height Stability**: Implemented `cy_container_visibility` to enforce container height (`800px`), preventing inline style overrides from collapsing the Cytoscape graph canvas to `0px` during layout transitions.
- **Diskcache WAL Checkpoint Safeguard**: Added SQLite WAL checkpoint (`PRAGMA wal_checkpoint(PASSIVE)`) prior to graph restoration callbacks, preventing SQLite WAL accumulation from blocking progress updates.
- **LLM Error Log Sanitisation & UI Animations**: Applied error message sanitisation before logging LLM exceptions to prevent API key exposure in log outputs, and enhanced progress bars with staged pacing delays.

### Previous: v1.5.0

- **FastAPI Bridge Memory Reclamation & TTL**: Added automated LRU session eviction and time-based expiration (default 2 hours) to `_SessionStore`, preventing memory accumulation during programmatic API and batch search runs.
- **GraphBuilder Lifecycle State Protection**: Locked graph builder mutation states (`_is_built`) to prevent destructive re-pruning on duplicate `build()` calls and guard against weight corruption from post-build additions.
- **Dependency & Environment Hardening**: Added explicit dependency verification for optional semantic extractors, graceful context-length exceeded error translation in Chat, and $10^{-9}$ floating-point tolerance in NPMI calculations.

### Previous: v1.4.0

- **Relation-Direction Verification (optional 2nd LLM)**: New opt-in toggle in Advanced Settings runs a second verification pass over directional semantic edges (e.g. *inhibits*, *upregulates*), checking each against its supporting evidence quote and downgrading unconfirmed directions to a neutral *associated_with* instead of dropping them. Choose a verifier provider independent from your main LLM for the best odds of catching an extraction error.
- **Numeric-Artifact Node Filter**: Defensively rejects graph nodes whose display name is purely numeric (an occasional PubTator3 upstream annotation artifact).

### Previous: v1.3.6

- **Deterministic ChromaDB Retrieval**: Stabilized vector retrieval result ordering for reproducible RAG outputs when candidate scores tie.

### Previous: v1.3.5

- **Deterministic 2-Hop Traversal**: Stabilized 2-hop path traversal ordering for reproducible graph reasoning results.

### Previous: v1.3.4

- **Version Alignment**: Corrected remaining version strings across `README.md`, `DEPLOYMENT.md`, `DOCKERHUB_OVERVIEW.md`, and the web application sidebar UI to align with release `v1.3.4`.

### Previous: v1.3.3

- **LLM Provider UI & Local Models**: Support for local model configuration and provider UI improvements with session isolation.
- **Offline Cache Support**: Pre-downloads tiktoken BPE cache in the builder stage to support air-gapped container environments.
- **Defensive Safeguards**: Normalization toggle is automatically disabled when no LLM is configured.
- **Config & Data Cleanups**: Redacted internal development variables, expanded `.env.example` to templates for all 7 providers, and excluded Pediatric CNS data from GitHub and Docker builds.

### Previous: v1.3.2

- **Search Nodes @Type Syntax**: Type `@Gene`, `@Disease`, `@Gene:gut`, or `keyword, @Gene` in the Search Nodes field to highlight, filter, or path-search by biological entity type. Top-20 anchor selection uses PMID literature count as the importance criterion.
- **Chat Download History Fix**: Download now exports the full unbounded message log, matching what the user sees in the UI chat panel.
- **Search Nodes Tooltip**: Improved info tooltip with @Type usage examples, anchor/path-node color legend, and silent-skip behaviour note.

- **WAL Hang Fix**: Resolves Chat panel permanently stuck at "Preparing abstracts..." — diskcache SQLite WAL is now checkpointed before each analysis run, preventing write-blocking from accumulated background callback writes.
- **Adaptive Chat Response Modes**: The 5-layer system prompt now selects response format based on question type: Compact Mode for simple factual queries, Layer 2 skip conditions to avoid empty structured blocks, and adaptive Layer 5 question count (3 for broad analyses, 1 for focused follow-ups, none for Compact Mode).

### Previous: v1.3.0

- **Anthropic API Integration**: Full native support for Anthropic Claude models (e.g., `claude-3-5-sonnet`, `claude-3-opus`) as a core LLM provider in both the web application (Advanced Settings UI) and CLI/API interfaces.
- **Advanced LLM Settings & Customization**: Rewrote LLM initialization and configuration parsing (`llm.py` and `advanced_settings.py`) to support multi-provider environments, dynamic testing of connection status for Anthropic/OpenAI/Gemini/Groq/NVIDIA NIM, and direct environment configuration saving to `.env`.
- **CJK / Universal Translation Robustness**: Strict universal language requirements inside prompts for non-English users, enforcing CJK output generation for all headers, labels, and structured segments.
- **Token Usage & Cost Analysis**: Added complete documentation for cost calculation per pipeline stage (`docs/token_cost.md`), including strategies for cost minimization using lighter models or co-occurrence graphs.
- **Biomedical RAG Platform Comparisons**: Published comparative analysis documentation against MRTKG (`docs/NetMedEx_vs_MRTKG_comparison.md`) describing architectural advantages.

---

## 🛠️ Quick Start

Launch the interactive dashboard on `localhost:8050`:

### Method A: Docker Desktop (GUI)

1. Search for **`lsbnb/netmedex`** in the top search bar of Docker Desktop and click **Pull**.
2. Go to the **Images** tab, locate `lsbnb/netmedex:latest`, and click **Run**.
3. Expand **Optional settings**:
   - Set **Host port** to **`8050`** (maps host port 8050 to container port `8050/tcp`).
   - *(Optional)* Set Container name to `NetMedEx`.
4. Click **Run**, then open **[http://localhost:8050](http://localhost:8050)** in your browser.

<p align="center">
  <img src="https://raw.githubusercontent.com/lsbnb/NetMedEx/main/docs/img/netmedex_docker_desktop.png" width="500" alt="Docker Desktop Container Setup">
  <br>
  <i>Configuring Host port (8050) in Docker Desktop Optional Settings.</i>
</p>

### Method B: Terminal Command Line

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

### 🔓 Unlock Full AI Power

Pass your LLM API key to enable Semantic Analysis and Hybrid RAG Chat:

```bash
# OpenAI
docker run -p 8050:8050 --rm \
  -e OPENAI_API_KEY='sk-...' \
  lsbnb/netmedex

# Google Gemini
docker run -p 8050:8050 --rm \
  -e LLM_PROVIDER=google \
  -e GEMINI_API_KEY='AIza...' \
  lsbnb/netmedex

# Local LLM (Ollama)
docker run -p 8050:8050 --rm \
  -e LLM_PROVIDER=local \
  -e LOCAL_LLM_BASE_URL='http://host.docker.internal:11434/v1' \
  -e LOCAL_LLM_MODEL='llama3' \
  lsbnb/netmedex

# NVIDIA NIM (Cloud)
docker run -p 8050:8050 --rm \
  -e LLM_PROVIDER=nvidia \
  -e NVIDIA_API_KEY='nvapi-...' \
  -e NVIDIA_NIM_MODEL='meta/llama-3.1-70b-instruct' \
  lsbnb/netmedex
```

### 📂 Persist Session Data

Mount a local directory to keep your graph sessions across container restarts:

```bash
docker run -p 8050:8050 --rm \
  -e OPENAI_API_KEY='sk-...' \
  -v $(pwd)/netmedex-data:/app/data \
  lsbnb/netmedex
```

---

## 🔗 Connect With Us

- **GitHub**: [lsbnb/NetMedEx](https://github.com/lsbnb/NetMedEx)
- **Documentation**: [Official Docs](https://yehzx.github.io/NetMedEx/)
- **PyPI**: [netmedex](https://pypi.org/project/netmedex/)

---
© 2026 Lab of Systems Biology and Network Biology (LSBNB) @ Institute of Information Science, Academia Sinica, TAIWAN.
