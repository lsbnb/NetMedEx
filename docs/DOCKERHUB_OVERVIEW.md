# NetMedEx

NetMedEx is an AI-powered knowledge discovery platform that transforms biomedical literature into actionable insights. It leverages **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** to synthesize structured co-mention networks with unstructured text, providing a holistic understanding of biological relationships.

## 🌟 Core Philosophy
In NetMedEx, the **Co-Mention Network** serves as a structural "scaffolding" for discovery. The **AI-driven Semantic Layer** breathes life into these connections by extracting evidence, identifying relationship types, and answering complex natural language queries.

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
