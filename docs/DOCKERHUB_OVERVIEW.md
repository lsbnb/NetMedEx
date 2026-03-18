# NetMedEx: AI-Powered Biomedical Knowledge Discovery

NetMedEx is a state-of-the-art platform designed to transform raw biomedical literature into actionable insights. By combining structured co-mention networks with unstructured text analysis, NetMedEx provides a **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** experience that allows researchers to explore complex biological relationships with unprecedented clarity.

## 🌟 Key Features
- **Interactive Co-Mention Networks**: Visualize relationships between genes, diseases, chemicals, and species extracted directly from PubTator3.
- **AI-Powered Semantic Layer**: Beyond simple co-mentions, our LLM integration (OpenAI, Gemini, Local LLMs) identifies specific relationship types (e.g., *inhibits*, *activates*) and extracts supporting evidence.
- **Hybrid RAG Chat**: Chat directly with your literature collection. NetMedEx synthesizes answers using both the network topology and underlying abstract text.
- **Natural Language Search**: Use simple English (or even Traditional Chinese/Japanese) to generate optimized PubTator boolean queries automatically.

## 🚀 What's New in 0.9.5
This version focuses on **reliability and transparency**:
- **Semantic Extraction Diagnostics**: A new real-time alert system shows exactly how many articles were successfully parsed, where recall was expanded, and why certain edges were dropped.
- **Robust Local LLM Support**: Enhanced parsing logic ensures stable extraction even when using local models like Llama 3 or Mistral via Ollama/LocalAI.
- **Simplified Configuration**: We've streamlined the Advanced Settings UI, standardizing on ChromaDB for a zero-config vector database experience.
- **Enhanced Translation Logic**: Improved multi-language support ensuring non-English queries are accurately translated for maximum PubTator recall.

## 🛠️ Quick Start
Run the latest version instantly:
```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```
Access the dashboard at `http://localhost:8050`.

### Using with AI (Recommended)
To unlock the full power of Semantic Analysis and Hybrid RAG, provide an OpenAI or Gemini API key:
```bash
docker run -p 8050:8050 --rm -e OPENAI_API_KEY='your-key-here' lsbnb/netmedex
```
*Note: You can also configure keys and models directly within the "Advanced Settings" tab in the web interface.*

## 🔗 Resources
- **GitHub**: [lsbnb/NetMedEx](https://github.com/lsbnb/NetMedEx)
- **Documentation**: [Full Docs](https://yehzx.github.io/NetMedEx/)
- **PyPI**: [netmedex](https://pypi.org/project/netmedex/)
