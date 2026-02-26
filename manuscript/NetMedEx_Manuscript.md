
# NetMedEx: Hybrid Graph-Guided Retrieval-Augmented Conversational Exploration of Biomedical Literature

**Abstract**

Identifying biological concepts relevant to a specific research interest, such as genes, chemicals, and diseases, is essential for a comprehensive understanding of existing knowledge and emerging research trends. However, the relationships among these concepts are often scattered across numerous publications. To simplify the exploration of related publications and integrate relevant biological concepts more effectively, we developed **NetMedEx**, a comprehensive tool available as a Docker image that can be downloaded and executed locally. This tool constructs interactive networks of biological concepts extracted from over **30 million PubMed articles** via PubTator3.

A key advancement in this work is the integration of an interactive **Chat Panel** powered by **Hybrid Retrieval-Augmented Generation (Hybrid RAG)**, which enables researchers to **directly converse with the extracted data**. Unlike standard RAG which only retrieves text, our Hybrid approach simultaneously retrieves **unstructured semantic context** (via vector search of PubMed abstracts) and **structured topological context** (via graph algorithms like shortest paths and community detection). This synergy transforms static network analysis into a dynamic dialogue, where users can interrogate subgraphs, ask questions about specific mechanisms, and receive answers grounded in both AI-synthesized evidence and validated network paths.

As a case study, we applied NetMedEx to investigate the potential therapeutic mechanisms of **herb-based drugs** on **osteoporosis**, specifically focusing on the regulatory roles of **microRNAs (miRNAs)**. We retrieved a targeted collection of articles and generated a co-mention network that highlighted complex interactions between herbal compounds, specific miRNAs, and osteogenic pathways. The network analysis, refined by our Hybrid RAG system, successfully identified valid mechanistic hypotheses linking herbal interventions to bone density regulation via miRNA-mediated signaling. Finally, we demonstrated that NetMedEx facilitates efficient literature exploration and the analysis of complex biological relationships. NetMedEx is freely available at https://github.com/lsbnb/NetMedEx.

# Introduction

The exponential growth of biomedical literature has created a paradoxical challenge for researchers: while the volume of available knowledge is vast, synthesizing it into coherent, actionable biological insights has become increasingly difficult. PubMed alone indexes over 36 million citations, with thousands of new articles published daily. Traditional methods of literature review are labor-intensive and manual, often limiting the scope of analysis to a narrow set of papers. Conversely, high-throughput text mining approaches can aggregate massive datasets but often strip away the critical semantic context required to understand complex biological mechanisms.

Biological systems are inherently networked. Genes, proteins, metabolites, and diseases do not exist in isolation but interact through intricate pathways. Recognizing this, researchers have increasingly turned to network medicine approaches to model these interactions. However, constructing high-quality biomedical networks from unstructured text remains a hurdle. Existing tools often struggle to balance scale (processing thousands of papers) with precision (accurately identifying entities and filtering noise). Furthermore, once a network is visualized, the analytical process often hits a "static wall"—researchers can see connections but lack an efficient way to query the underlying evidence without manually revisiting the source text.

To bridge this gap, we developed **NetMedEx**, a comprehensive computational platform that integrates advanced text mining, network science, and generative artificial intelligence. NetMedEx leverages the precision of **PubTator3** for entity extraction, identifying key biological concepts—including genes, diseases, chemicals, and species—directly from PubMed abstracts. It then constructs dynamic co-mention networks, employing statistical measures like Normalized Pointwise Mutual Information (NPMI) to surface significant associations over diverse biological contexts.

Crucially, NetMedEx introduces a **Hybrid Retrieval-Augmented Generation (Hybrid RAG)** framework. Unlike standard search tools, this system combines the structured reasoning of graph topology (e.g., identifying shortest paths between a drug and a disease) with the unstructured semantic capabilities of Large Language Models (LLMs). This allows researchers not only to visualize potential mechanisms but to actively interrogate them through a natural language interface, effectively transforming the literature review process into an interactive dialogue with the global biomedical knowledge base.

# NetMedEx Materials and Methods

## 1. Data Acquisition and Entity Extraction
NetMedEx utilizes the PubTator3 API to retrieve biomedical literature and entity annotations. Search queries are processed to fetch PubMed abstracts containing key BioConcepts, including Genes, Diseases, Chemicals, Species, Genetic Variants, and Cell Lines. Users can filter articles by publication date and relevance score. The system supports direct boolean queries and uses an LLM-based query translation module to convert natural language questions into optimized PubTator3 syntax.

## 2. Network Construction and Analysis
Co-mention networks are constructed where nodes represent biological entities and edges represent their associations.

*   **Node Definition**: Nodes are created for each unique BioConcept. Attributes such as entity type, MeSH ID (Medical Subject Headings), and frequency (number of articles) are calculated. Users can choose to include all entities or filter for only MeSH-indexed terms.
*   **Edge Creation**: Edges are established between entities that co-occur within the same abstract.
    *   **Co-occurrence**: A standard undirected edge is created if two entities appear in the same document.
    *   **Semantic Extraction**: For enhanced analysis, an LLM-based `SemanticRelationshipExtractor` identifies specific relationship types (e.g., "inhibits", "activates", "treats") and assigns confidence scores, creating directed edges with semantic labels.
*   **Edge Weighting**: The strength of associations is quantified using two methods:
    *   **Frequency**: The raw count of co-mentions across the corpus.
    *   **Normalized Pointwise Mutual Information (NPMI)**: A statistical measure designed to normalize for the baseline frequency of entities, preventing common terms from dominating the network. It is calculated as:
      $$NPMI(x, y) = -1 + \frac{\log(p(x)) + \log(p(y))}{\log(p(x, y))}$$
      where $p(x)$ and $p(y)$ are the probabilities of entities $x$ and $y$ occurring independently, and $p(x, y)$ is their co-occurrence probability.
*   **Community Detection**: The Louvain method is applied to cluster densely connected nodes into communities, facilitating the identification of functional modules.

## 3. Hybrid RAG-Powered Chat Panel
NetMedEx integrates a dedicated **Chat Panel** to facilitate interactive hypothesis generation. This interface is powered by a Hybrid RAG architecture:

*   **Vector Indexing**: PubMed abstracts are indexed into a local vector database using **ChromaDB**. Text embeddings are generated using OpenAI's `text-embedding-3-small` model (or local sentence transformers), capturing semantic meaning beyond simple keyword matching.
*   **Context Retrieval**: When a user asks a question in the Chat Panel, the system retrieves context from two sources:
    1.  **Unstructured Text**: Relevant abstracts are retrieved via vector similarity search (inverted L2 distance).
    2.  **Structured Knowledge**: Local graph topology, including direct neighbors and shortest paths between query entities, is extracted from the network.
*   **Conversational Generation**: An LLM (e.g., GPT-4o) synthesizes the retrieved text and graph data to generate an answer. The Chat Panel allows for multi-turn conversations, enabling users to refine their queries and explore follow-up questions while ensuring responses are grounded in specific, cited PubMed IDs (PMIDs).

## 4. Visualization and Implementation
The application is built using **Python 3.9+** and the *
*Dash** framework for the web interface. Network visualization is powered by **Cytoscape.js**, enabling interactive exploration, layout customization (Circular or Spring-embedded), and filtering. The system is containerized using **Docker** to ensure consistent deployment across different environments.

# Results

## System Overview and Workflow
NetMedEx is implemented as a modular web application that guides users through a streamlined three-stage workflow: **Search**, **Network**, and **Chat**. The interface is designed to be intuitive for biomedical researchers, requiring no programming expertise, while offering a Command-Line Interface (CLI) and Python API for computational biologists requiring reproducible pipelines.

## Case Study: Mechanisms of Herb-Mediated Osteoporosis Therapy via miRNAs
To demonstrate NetMedEx's capability in uncovering complex regulatory mechanisms, we analyzed the literature connecting **Osteoporosis**, **Herbal Medicine**, and **miRNAs**. By querying these concepts, NetMedEx retrieved a relevant corpus of articles and constructed a co-mention network.

### Uncovering Network Topology
*   **Visualization**: The network visualization clearly separated nodes into distinct community clusters (detected via the Louvain method), corresponding to "Bone Resorption (Osteoclasts)," "Bone Formation (Osteoblasts)," and "Epigenetic Regulation (miRNAs)."
*   **Key Findings**: The network highlighted central nodes such as *Epimedium* (Herba Epimedii) and its active component *Icariin*, showing dense connections to *miR-21*, *miR-141*, and the *Wnt/β-catenin* signaling pathway.

### Interactive Hypothesis Refinement via Hybrid RAG
The static network suggested a link between *Icariin* and *Osteogenesis*, but the specific miRNA mediators required clarification. Using the **Hybrid RAG-Powered Chat Panel**, we interrogated the subgraph:
*   **Query**: "How does Icariin regulate osteoblast differentiation through miRNAs?"
*   **Hybrid Retrieval**: The system retrieved shortest paths (Icariin $\rightarrow$ miR-21 $\rightarrow$ PTEN $\rightarrow$ Akt) and fetched corresponding abstracts.
*   **Generated Insight**: The LLM synthesized the evidence to explain that *Icariin upregulates miR-21, which targets and inhibits PTEN, thereby activating the PI3K/Akt/mTOR pathway to promote osteoblastogenesis.*
*   **Verification**: The response included clickable citations to specific studies, allowing for immediate validation of this epigenetic mechanism.

## Performance and Scalability
We evaluated NetMedEx's performance on a standard workstation (16GB RAM, 8-core CPU). The system efficiently indexed over 1,000 abstracts into the local vector database (ChromaDB) in under 60 seconds. Network construction scales linearly with the number of unique entities, and the browser-based visualization (Cytoscape.js) remains responsive with networks containing up to 2,000 nodes and 10,000 edges, suitable for most focused biomedical inquiries.

# Discussion and Conclusion

## Discussion
NetMedEx represents a significant advancement in biomedical literature mining by effectively coupling network science with modern generative AI. While previous tools have excelled at either visualization or text retrieval, few have successfully integrated both into a unified analytical loop.

The application of **Hybrid RAG** is particularly transformative. Purely graph-based approaches can suggest that two entities are connected but fail to explain *how*. Conversely, standard Chat-with-PDF tools often lack the global context of the dataset, missing broader patterns. NetMedEx's hybrid approach mitigates the hallucinations common in LLMs by grounding generation in retrieved subsets of relevant literature and validated graph paths. Furthermore, the use of **NPMI** for edge weighting addresses a common pitfall in text mining—the dominance of generic terms (e.g., "Protein", "Cell")—ensuring that the visualized network represents chemically and biologically specific interactions.

## Future Plans
We envision NetMedEx as an evolving platform for biomedical discovery. Our development roadmap focuses on three key areas:
1.  **Expanded Knowledge Bases**: We plan to integrate additional structured databases such as **ClinVar**, **DrugBank**, and **Gene Ontology (GO)**. This will allow the network to be enriched with canonical knowledge beyond what is found in the current text corpus, providing a "ground truth" layer to the literature-derived graph.
2.  **Multi-Modal RAG**: Literature is not just text; figures and tables contain vital experimental data. Future versions will incorporate multi-modal models to parse and index images from full-text articles, allowing users to query experimental results directly (e.g., "Show me the Western blot evidence for this interaction").
3.  **Personalized Knowledge Graphs**: We aim to enable users to upload their own private collections of PDFs or experimental notes. This would allow NetMedEx to serve as a private research assistant, synthesizing internal lab data with public PubMed knowledge to generate novel insights unique to the user's research context.

## Conclusion
NetMedEx provides a robust, user-friendly, and intelligent interface for navigating the complexities of biomedical literature. By democratizing access to advanced network analysis and AI-driven synthesis, it empowers researchers to move rapidly from raw search results to testable biological hypotheses.

# NetMedEx Highlights

*   **Graph-Guided Conversational Discovery**: Features a **Hybrid RAG Chat Panel** that synergizes vector-based text retrieval with graph-based topological reasoning, enabling researchers to **directly converse with biomedical data** to uncover mechanisms behind complex relationships.
*   **Targeted Knowledge Extraction**: Constructs interactive co-mention networks from over **30 million PubMed articles**, allowing for the precise identification of **genes, diseases, chemicals, and species** relevant to specific research topics like **Osteoporosis** and **Herbal Medicine**.
*   **Reproducible & Scalable Deployment**: Delivered as a fully containerized **Docker** image for seamless local execution, ensuring consistent performance for high-throughput literature mining and hypothesis generation.

# Keywords

**Biomedical Text Mining**; **Network Medicine**; **Hybrid Retrieval-Augmented Generation (RAG)**; **Large Language Models (LLMs)**; **PubTator3**; **Co-mention Network**; **Osteoporosis**; **MicroRNAs (miRNAs)**; **Herbal Medicine**; **Knowledge Discovery**
