# NetMedEx v1.5.3: AI-Powered Biomedical Knowledge Discovery 🧬✨

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

## 🆕 What's New in v1.5.3

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
