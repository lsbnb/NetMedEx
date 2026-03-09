# NetMedEx

NetMedEx is an AI-powered knowledge discovery platform that transforms biomedical literature into actionable insights. It leverages **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** to synthesize structured co-mention networks with unstructured text, providing a holistic understanding of biological relationships.

## 🌟 Core Philosophy
In NetMedEx, the **Co-Mention Network** serves as a structural "scaffolding" for discovery. The **AI-driven Semantic Layer** breathes life into these connections by extracting evidence, identifying relationship types, and answering complex natural language queries.

### What's New in 0.9.4
- **Professional Chat Transcript (HTML)**: Download your chat history in a high-fidelity HTML format featuring chat bubbles, clear hierarchical section headers, and clickable PubMed links.
- **Ultra-Stable Copy Feedback**: Re-engineered the clipboard feedback system for 100% stability. Get instant visual confirmation (checkmark toggle) every time you copy a response.
- **Improved Hierarchical Layout**: AI-generated answers now feature better structural clarity with emphasized headers for Evidence, Hypotheses, and Suggested Questions.
## 🚀 Quick Start
Launch the interactive dashboard using Docker and access it at `localhost:8050`:

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

## AI Setup (Optional)
To enable the AI-powered Hybrid RAG chat and natural language search:

1. **Get an API Key**: Obtain one from OpenAI.
2. **Configure the Container**: Pass your API key into the Docker container using an environment variable:
   ```bash
   docker run -p 8050:8050 --rm -e OPENAI_API_KEY='sk-...' lsbnb/netmedex
   ```
   Alternatively, you can enter your API key directly in the "Advanced Settings" tab within the web interface.

## 🔗 Links
- **GitHub Repository**: [lsbnb/NetMedEx](https://github.com/lsbnb/NetMedEx)
- **Documentation**: [Online Docs](https://yehzx.github.io/NetMedEx/)
- **PyPI**: [netmedex](https://pypi.org/project/netmedex/)
