# NetMedEx: Interactive BioConcept Network Extraction & AI Analysis

NetMedEx is a powerful tool designed to extract BioConcept entities (genes, diseases, chemicals, and species) from PubMed via PubTator3 and generate interactive co-mention networks. It transforms static literature searches into dynamic, AI-powered knowledge engines.

## Quick Start (via Docker)

To launch the NetMedEx web application, simply run:

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

Then open [http://localhost:8050](http://localhost:8050) in your browser.

## Key Features

- **Interactive Network Visualization**: explore co-mention relationships between biological entities directly in your browser.
- **Hybrid RAG Chat**: Analyze your selected network using advanced Retrieval-Augmented Generation that understands both **unstructured text** (abstracts) and **structured graph knowledge** (paths and neighbors).
- **Natural Language search**: Convert plain English queries into optimized PubTator3 boolean search syntax.
- **Semantic Evidence**: View relationship types, confidence scores, and specific evidence sentences extracted from scientific literature.
- **Multiple Exports**: Export your interactive networks as standalone HTML files for sharing or XGMML for advanced analysis in Cytoscape.

## AI Setup (Optional)

To enable the AI-powered Hybrid RAG chat and natural language search:

1. **Get an API Key**: Obtain one from [OpenAI](https://platform.openai.com/).
2. **Configure the Container**: Pass your API key into the Docker container using an environment variable:

```bash
docker run -p 8050:8050 --rm -e OPENAI_API_KEY='sk-...' lsbnb/netmedex
```

*Alternatively, you can enter your API key directly in the "Advanced Settings" tab within the web interface.*

## Resources

- **GitHub Repository**: [lsbnb/NetMedEx](https://github.com/lsbnb/NetMedEx)
- **Official Documentation**: [yehzx.github.io/NetMedEx/](https://yehzx.github.io/NetMedEx/)
- **PyPI Package**: [netmedex](https://pypi.org/project/netmedex/)
