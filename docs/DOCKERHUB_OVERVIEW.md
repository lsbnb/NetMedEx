# NetMedEx v1.3.2: AI-Powered Biomedical Knowledge Discovery 🧬✨

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

## 🆕 What's New in v1.3.2

- **Search Nodes @Type Syntax**: Type `@Gene`, `@Disease`, `@Gene:gut`, or `keyword, @Gene` in the Search Nodes field to highlight, filter, or path-search by biological entity type. Top-20 anchor selection uses PMID literature count as the importance criterion.
- **Chat Download History Fix**: Download now exports the full unbounded message log, matching what the user sees in the UI chat panel.
- **Search Nodes Tooltip**: Improved info tooltip with @Type usage examples, anchor/path-node color legend, and silent-skip behaviour note.

### Previous: v1.3.1

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
