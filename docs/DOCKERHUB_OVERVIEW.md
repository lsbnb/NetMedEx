# NetMedEx: AI-Powered Biomedical Knowledge Discovery 🧬✨

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

## 🆕 What's New in v1.2.0
- **Smart 2-Hop Mechanism Discovery**: Automatically surfaces latent A → B → C mechanistic hypotheses from the knowledge graph, ranked by a multi-factor confidence score.
- **Hybrid Scoring 2.0**: Each graph path is scored by three components — Topological NPMI (30%), Semantic Extraction Confidence (40%), and Query Relevance (30%) — with directional relation boosts and evidence-frequency calibration.
- **Confidence Calibration**: Relation strength and supporting PMID count now modulate edge confidence, reducing false-positive mechanistic inferences.
- **Species Differentiation**: AI responses now explicitly flag animal model vs. human clinical evidence for every claim.
- **Mandatory 2-Hop Hypothesis Section**: Every chat response now always includes a dedicated hypothesis section when latent graph paths are found, with per-link PMID citations.

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
