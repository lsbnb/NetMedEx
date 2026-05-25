# NetMedEx v1.2.8: AI-Powered Biomedical Knowledge Discovery 🧬✨

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

## 🆕 What's New in v1.2.8

- **Groq API Provider**: Integration of Groq for semantic relationship extraction and Hybrid RAG chat (supports preset models like Llama 3.3 and Mixtral, custom models, and dynamic model list fetching).
- **Search Query Filtering**: Automatically appends publication-type filters (e.g. `NOT "Editorial"[pt] NOT "News"[pt]`) to free-text queries, removing non-research literature noise.
- **Suggested Questions Format**: Implemented structured prompts to cite specific biological concepts instead of abstract placeholders. Handles both bracketed `[Q1: ...]` and bare `Q1:` formats.
- **Modal Collision Fix**: Added dynamic ID suffixing for suggested question components when rendering in Modal dialogs to prevent ID collisions.
- **100% Test Coverage**: Restored missing test datasets from history and resolved legacy test mock and assertion errors.

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
