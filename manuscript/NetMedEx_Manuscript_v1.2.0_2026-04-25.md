
# NetMedEx: Smart Graph-Guided Retrieval-Augmented Mechanism Discovery in Biomedical Literature

**Version 1.2.0 | April 25, 2026**

**Abstract**

Identifying biological concepts relevant to a specific research interest, such as genes, chemicals, and diseases, is essential for a comprehensive understanding of existing knowledge and emerging research trends. However, the relationships among these concepts are often scattered across numerous publications. To simplify the exploration of related publications and integrate relevant biological concepts more effectively, we developed **NetMedEx (v1.2.0)**, an open-source platform that constructs interactive and **semantically normalized** networks of biological concepts extracted from over **30 million PubMed articles** via PubTator3. NetMedEx is optimized for both targeted inquiries and **large-scale knowledge discovery**, supporting a seamless **multilingual search experience** through an advanced intermediary reasoning pipeline.

A key advancement in this version is the implementation of a **Smart 2-hop Hybrid Retrieval-Augmented Generation (Hybrid RAG)** framework. Unlike standard RAG systems, NetMedEx explores connections up to two hops from user-targeted nodes to uncover latent mechanistic paths (e.g., A → B → C). This discovery process is governed by a **calibrated scoring system (Hybrid Scoring 2.0)** that integrates Normalized Pointwise Mutual Information (NPMI), LLM-extracted confidence, and query-aware semantic relevance. To ensure scientific rigor and prevent false inferences, the system implements **bottleneck scoring** for multi-hop paths and **automated species-aware study-type differentiation**, explicitly distinguishing animal/in vitro models from human clinical findings.

As a case study, we applied NetMedEx to investigate the potential therapeutic mechanisms of **herb-based drugs** on **osteoporosis**. The system successfully identified a valid mechanistic hypothesis linking **Icariin** to osteoblast differentiation via a **miR-21/PTEN/PI3K/Akt** axis. NetMedEx facilitates efficient literature exploration and the analysis of complex biological relationships, and is freely available at https://github.com/lsbnb/NetMedEx.

# Introduction

The exponential growth of biomedical literature has created a paradoxical challenge for researchers: while the volume of available knowledge is vast, synthesizing it into coherent, actionable biological insights has become increasingly difficult. PubMed alone indexes over 36 million citations, with thousands of new articles published daily. Traditional methods of literature review are labor-intensive and manual, often limiting the scope of analysis to a narrow set of papers. Conversely, high-throughput text mining approaches can aggregate massive datasets but often strip away the critical semantic context required to understand complex biological mechanisms.

Biological systems are inherently networked. Genes, proteins, metabolites, and diseases do not exist in isolation but interact through intricate pathways. Recognizing this, researchers have increasingly turned to network medicine approaches to model these interactions. However, once a network is visualized, the analytical process often hits a "static wall"—researchers can see connections but lack an efficient way to query the underlying evidence without manually revisiting the source text.

To bridge this gap, we developed **NetMedEx**, a comprehensive computational platform that integrates advanced text mining, network science, and generative artificial intelligence. Current release (v1.2.0) introduces a **Smart 2-hop Hybrid RAG** framework. Unlike standard search tools, this system combines the structured reasoning of graph topology with the unstructured semantic capabilities of LLMs. This allows researchers not only to visualize potential mechanisms but to actively interrogate **latent 2-hop paths**, effectively transforming the literature review process into an interactive dialogue with the global biomedical knowledge base.

# NetMedEx Materials and Methods

## 1. Data Acquisition and Entity Extraction
NetMedEx utilizes the PubTator3 API to retrieve biomedical literature and entity annotations. The system supports direct boolean queries and uses a multi-stage LLM-based query reasoning module to translate queries from multiple languages (Chinese, Japanese, and Korean) into optimized, English-based PubTator3 syntax.

## 2. Network Construction and Analysis
Co-mention networks are constructed where nodes represent biological entities and edges represent their associations.
*   **Semantic Normalization via sapBERT**: Nodes representing semantically equivalent concepts are automatically merged using vector embeddings to ensure a cleaner knowledge graph.
*   **Edge Weighting & Scoring 2.0**: The strength of associations is quantified using **Hybrid Scoring 2.0**, which combines:
    1.  **Topological Evidence (30%)**: Calculated via Normalized Pointwise Mutual Information (NPMI).
    2.  **Semantic Confidence (40%)**: Derived from LLM-based extraction, calibrated by **Mechanistic Boosts** (1.1x for directional relations) and **Evidence Consensus** (+5% boost per supporting PMID).
    3.  **Query Relevance (30%)**: Dynamic weighting based on the semantic proximity of nodes to the user's current research question.
*   **Community Detection**: Functional clusters are identified via the Louvain method.

## 3. Smart 2-hop Hybrid RAG Panel
The Chat Panel (v1.2.0) utilizes a Hybrid RAG architecture enhanced for mechanistic discovery:
*   **Smart 2-hop Extraction**: When a user selects anchor nodes, the system explores neighbors up to two hops away to identify potential mediated pathways.
*   **False Inference Reduction**: To ensure rigorous output, multi-hop paths are scored using a **Bottleneck (Min-Link) strategy** (`min(link1, link2) * 0.8`). This acknowledges that a mechanistic chain is only as strong as its weakest link and penalizes indirect connections unless evidence is overwhelming.
*   **Species-Aware Study-Type Differentiation**: The system automatically scans retrieved abstracts for species-specific metadata. Articles focusing on animal models (e.g., mice, zebrafish) are explicitly labeled as **[Animal Model/In vitro]** in the LLM context, and the system prompt enforces a mandatory distinction between preclinical findings and human clinical facts.
*   **Grounding**: Responses are grounded in cited PubMed IDs (PMIDs), with hyperlinked citations provided for immediate verification.

# Results

## Case Study: Mechanisms of Herb-Mediated Osteoporosis Therapy via miRNAs
We investigated the relationship between **Icariin**, **miRNAs**, and **Osteogenesis**. 

### Latent Mechanism Discovery
The static 1-hop network established a co-occurrence between Icariin and PTEN. However, by activating the **Smart 2-hop RAG**, the system identified a latent mechanistic chain: **Icariin → miR-21 → PTEN → PI3K/Akt**.
*   **Calculated Path Score**: 1.08 (Highly significant).
*   **Generated Insight**: The LLM synthesized evidence stating that Icariin upregulates miR-21, which targets and inhibits PTEN, thereby activating the PI3K/Akt/mTOR pathway to promote osteoblastogenesis.
*   **Rigorous Attribution**: The system explicitly distinguished that while the miR-21/PTEN interaction was confirmed in multiple **[Animal Models]**, the resulting osteogenic boost was consistent with observed **[Human]** clinical trends.

# Discussion and Conclusion

## Discussion
NetMedEx v1.2.0 represents a significant advancement by coupling network science with query-aware mechanism discovery. The implementation of **Hybrid Scoring 2.0** ensures that the most relevant and confirmed biological paths float to the top of the retrieval results. Furthermore, the **Bottleneck Scoring** and **Study-Type Differentiation** address direct user requirements for scientific rigor, minimizing the risk of false inferences from animal studies or weak indirect associations.

## Conclusion
NetMedEx provides a robust, intelligent interface for navigating the complexities of biomedical literature. By democratizing access to 2-hop mechanism discovery and evidence-grounded synthesis, it empowers researchers to move rapidly from raw data to testable biological hypotheses.

# NetMedEx v1.2.0 Highlights
*   **Smart 2-hop Mechanism Discovery**: Uncovers mediated paths between biological entities through calibrated graph traversal.
*   **Hybrid Scoring 2.0**: Integrates NPMI, Semantic Confidence, and Query Relevance for high-precision retrieval.
*   **Rigorous False-Inference Control**: Implements Bottleneck scoring and automated [Animal/Human] study-type differentiation.
*   **Universal Multilingual Search**: Enhanced reasoning pipeline for CJK queries against the English-article corpus.

# Keywords
**Biomedical Text Mining**; **Network Medicine**; **Hybrid RAG**; **Knowledge Discovery**; **Mechanism Discovery**; **Pharmacological Network**; **Large Language Models**
