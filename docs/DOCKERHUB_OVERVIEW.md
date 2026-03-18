# NetMedEx: AI-Powered Biomedical Knowledge Discovery 🧬✨

NetMedEx is a premium, AI-driven platform that transforms millions of biomedical abstracts from **PubTator3** into interactive, actionable knowledge graphs. It bridge the gap between structured networks and unstructured text using our proprietary **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** engine.

---

## 🌟 Why NetMedEx?
While other tools simply list entities, NetMedEx **interprets the links**. It provides the "scaffolding" for discovery, allowing researchers to navigate the complex landscape of genes, diseases, chemicals, and species with AI as their co-pilot.

### 🚀 Core Capabilities
- **🧠 Hybrid RAG Engine**: Combines graph topology (paths, neighbors) with deep text analysis (abstracts) for high-fidelity discovery.
- **🕸️ Interactive Visualization**: Explore co-mention and semantic networks with real-time layout adjustments, community detection, and sub-network selection.
- **⚡ Semantic Extraction**: Automatically identifies relationship types (e.g., *inhibits*, *treats*, *activates*) with confidence scores and direct evidence sentences.
- **🌐 Universal Translation**: Search and chat in English, Traditional Chinese, Japanese, or Korean. AI handles the translation to optimized PubTator syntax.
- **💾 Full Session Portability**: Export your entire research state as a **Graph File (.pkl)** and restore it instantly later — no re-analysis required.

---

## 🆕 What's New in V0.9.5
- **🔍 Semantic Diagnostics**: Gain full transparency with real-time metrics on parsing success, recall expansion, and edge filtering.
- **🤖 Robust Local AI**: Optimized regex-based parsing for stable results when using local models (Llama 3, Mistral) via Ollama.
- **🎨 Streamlined UI**: A cleaner Advanced Settings experience, standardizing on ChromaDB for zero-config vector storage.
- **📍 Precise Citations**: Enhanced HTML exports with clickable PubMed links and hierarchically structured AI answers.

---

## 🛠️ Quick Start
Launch the interactive dashboard instantly on `localhost:8050`:

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

### 🔓 Unlock Full AI Power
To enable Semantic Analysis and Hybrid RAG Chat, simply pass your API key:

```bash
docker run -p 8050:8050 --rm -e OPENAI_API_KEY='sk-...' lsbnb/netmedex
```
*Note: You can also configure OpenAI, Gemini, or Local LLM endpoints directly within the "Advanced Settings" tab in the app.*

---

## 🔗 Connect With Us
- **GitHub**: [lsbnb/NetMedEx](https://github.com/lsbnb/NetMedEx)
- **Documentation**: [Official Docs](https://yehzx.github.io/NetMedEx/)
- **PyPI**: [netmedex](https://pypi.org/project/netmedex/)

---
© 2026 LSBNB Lab @ IIS, Academia Sinica, TAIWAN.
