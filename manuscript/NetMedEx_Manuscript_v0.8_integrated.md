# NetMedEx: A Graph-Guided Retrieval-Augmented Platform for Conversational Exploration of Biomedical Literature

---

## Abstract

Identifying biological concepts relevant to a specific research interest—such as genes, chemicals, and diseases—is essential for achieving a comprehensive understanding of existing knowledge and emerging research trends. However, the relationships among these concepts are often scattered across numerous publications. To simplify the exploration of related publications and integrate relevant biological concepts more effectively, we developed **NetMedEx**, a comprehensive dual-mode platform available as a Docker image that can be downloaded and executed locally. At its baseline, NetMedEx generates interactive co-mention networks of biological concepts extracted from over **30 million PubMed articles** via PubTator3 using co-occurrence statistics. This foundational mode allows users to rapidly visualize and explore structural connections without relying on external language models.

For deeper interrogation, NetMedEx offers an advanced mode featuring an interactive **Chat Panel** driven by a hybrid **text-based and graph-based Retrieval-Augmented Generation (RAG)** architecture with Large Language Model (LLM) assistance. This system elevates basic co-mention associations into deep, semantic relationship analysis. Rather than applying conversational models to an untargeted corpus, NetMedEx constrains retrieval through the intermediate Graph Panel. Users first select nodes and edges of interest; the RAG system extracts the specific abstracts associated with those targeted PubMed identifiers (PMIDs). The LLM then performs rigorous semantic analysis on this focused evidence base to generate integrated, evidence-grounded answers with explicit PMID citations. Crucially, in both the baseline co-mention mode and the advanced LLM-assisted mode, the Graph Panel serves as the central interface for dissecting complex literature networks.

As a case study, we applied NetMedEx to investigate the potential therapeutic mechanisms of **herb-based drugs** on **osteoporosis**, focusing on the regulatory roles of **microRNAs (miRNAs)**. We retrieved a targeted collection of articles and mapped the foundational co-mention structure. From this scaffolding, the advanced hybrid RAG system performed semantic analysis on user-selected pathways, synthesizing detailed mechanistic hypotheses linking herbal interventions to bone density regulation via miRNA-mediated signaling. These results demonstrate that NetMedEx provides a flexible, dual-mode paradigm—ranging from rapid structural visualization to deep, LLM-assisted semantic integration—to efficiently explore complex biological relationships. NetMedEx is freely available at https://github.com/lsbnb/NetMedEx.

---

## Introduction

The exponential growth of biomedical literature has created a paradoxical challenge for researchers: while the volume of available knowledge is vast, synthesizing it into coherent, actionable biological insights has become increasingly difficult. PubMed alone indexes over 36 million citations, with thousands of new articles published daily. Traditional methods of literature review are labor-intensive and often limit the scope of analysis to a narrow set of papers. Conversely, high-throughput text mining approaches can aggregate massive datasets but often strip away the critical semantic context required to understand complex biological mechanisms.

Biological systems are inherently networked. Genes, proteins, metabolites, and diseases do not exist in isolation but interact through intricate pathways. Researchers have increasingly turned to network medicine approaches to model these interactions (PMID: 21164525). However, reconstructing high-quality biomedical networks from unstructured text remains a hurdle. Existing tools often struggle to balance scale (processing thousands of papers) with precision (accurately extracting entities and filtering noise). Furthermore, once a network is visualized, the analytical process often hits a "static wall"—researchers can see connections but lack an efficient way to query the underlying evidence without manually revisiting the source text.

Recently, the advent of Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG) (DOI: 10.48550/arXiv.2005.11401) has transformed how researchers interact with large text corpora by enabling conversational querying. However, applying standard RAG to biomedical literature presents challenges, including the risk of hallucinated mechanisms and the difficulty of navigating overarching biological systems rather than isolated facts. While established knowledge platforms (such as STRING (PMID: 36370105) or traditional text-mining databases) provide structured, macroscopic overviews, they typically lack conversational interfaces for deep-diving into specific literature evidence. Conversely, general-purpose LLM assistants lack the structured network perspective necessary to discover indirect relationships or prioritize relevant context. Therefore, there is a pressing need for a hybrid approach that combines the systemic view of network biology with the granular precision of evidence-grounded conversational AI.

To bridge this gap, we developed **NetMedEx**, a Python-based platform that offers two complementary modes for literature discovery: a rapid **co-mention analysis mode** (without LLM dependency) and an advanced **LLM-assisted semantic analysis mode**. NetMedEx leverages the precision of **PubTator3** (Wei et al., 2024) to extract key biological concepts—including genes, diseases, chemicals, and species—from over 30 million PubMed articles. In its baseline mode, it utilizes statistical measures like Normalized Pointwise Mutual Information (NPMI) and Louvain community clustering to generate interactive **co-mention networks**. This allows researchers to quickly map overarching structural proximities and extract key functional modules using only local keyword statistics.

When researchers require deeper mechanistic insights, they can activate NetMedEx's advanced analytical capabilities: an interactive **Chat Panel** driven by a hybrid **text-based and graph-based Retrieval-Augmented Generation (RAG)** framework. This system leverages an LLM to transition from visualizing structural proximities to interpreting deep semantic relationships. In contrast to standalone LLM tools that struggle with vast, unstructured contexts, NetMedEx uses the initial network scaffolding to deliberately constrain conversational retrieval. Users actively select nodes and edges, defining a precisely scoped subgraph. The system extracts the source abstracts tied to these specific PMIDs and provides them to the LLM. The LLM then performs targeted semantic analysis and integration across this curated document set, preventing hallucinations by grounding coherent narrative responses solely in user-selected, evidence-supported literature. Importantly, regardless of whether a user is operating in the baseline co-mention mode or the advanced LLM-assisted mode, the central Graph Panel remains the primary interface for resolving and navigating the complex network of literature data. NetMedEx is freely available as a Docker image and supports a command-line interface (CLI) and Python API for use in reproducible computational pipelines.

---

## Methods

### 1. Data Retrieval

NetMedEx leverages the PubTator3 API (Wei et al., 2024) to retrieve over 30 million PubMed abstracts and over 6 million full-text articles annotated with biomedical concepts. To facilitate intuitive user interactions, NetMedEx integrates a Large Language Model (LLM) to assist users in formulating search queries using natural language. The LLM processes the user's natural language input to automatically extract relevant biological keywords and correct potential typographical errors, ensuring high-quality query construction before literature retrieval. Alternatively, users can directly input a text query of biological terms or provide one or more PubMed reference numbers (PMID). The retrieved articles are processed through a pipeline consisting of text normalization, co-occurrence matrix calculation, and network construction (Figure 1).

### 2. Text Normalization

NetMedEx extracts only the biological concept annotations from a PubTator file generated by PubTator3 and discards all other text. A biological concept annotation includes the original text, the entity type (e.g., Gene, Chemical, Disease, Species), and a Medical Subject Headings (MeSH) identifier when available.

The original text of each annotation is normalized to avoid synonyms that refer to the same biological concepts. If an annotation has a known MeSH term, the original text is replaced with the standardized MeSH term. If no MeSH term is available, a conservative plural stemmer is applied (Harman, 1991), and the text is converted to lowercase to maintain consistency across terms.

### 3. Co-Occurrence Matrix Calculation

Duplicate annotations within the same article are removed, leaving a unique set of terms for each article. A co-occurrence matrix is then constructed by counting the number of times any two normalized terms co-appear within the same article. Only non-zero counts are stored to conserve memory. The document frequency of each term is also calculated for use in later weighting adjustments.

### 4. Network Construction and Edge Weighting

A co-occurrence network is built by representing each unique term as a node and co-occurrence counts as edge weights. NetMedEx provides two options for calculating edge weights:

- **Frequency-based method**: The scaled edge weight is proportional to the raw co-occurrence count, normalized to the range [0, 1].
- **Normalized Pointwise Mutual Information (NPMI)-based method**: NPMI adjusts for the marginal frequency of individual terms, preventing common terms from dominating the network. It is calculated as:

$$NPMI(x, y) = \frac{\log p(x,y) - \log p(x) - \log p(y)}{-\log p(x,y)}$$

where $p(x)$ and $p(y)$ are the marginal probabilities of entities $x$ and $y$, and $p(x,y)$ is their co-occurrence probability. The NPMI-based edge weight ranges from −1 to 1.

Edges with weights below a user-defined threshold are pruned to simplify the network. Isolated nodes that result from pruning are also removed.

### 5. Community Detection

To identify clusters of related terms, NetMedEx applies the Louvain method (Blondel et al., 2008), which optimizes network modularity to detect non-overlapping communities. Edges between communities are collapsed into a single representative edge. The node with the highest degree in each community is selected as the hub term for that cluster. This clustering simplifies the network structure while preserving key relationships among highly connected terms.

### 6. Semantic Relationship Extraction (LLM-Assisted Advanced Mode)

For researchers operating in the advanced semantic mode, NetMedEx supports an LLM-based **Semantic Relationship Extractor** that looks beyond statistical co-occurrence. This module analyzes the retrieved abstracts to identify specific, directional relationship types (e.g., "inhibits," "activates," "treats") between entities and assigns confidence scores. This enables directed edges with explicit semantic labels to be added to the Graph Panel. Users can configure a confidence threshold to filter low-certainty predictions, and all relationship calls are conditioned on explicitly stated evidence sentences extracted from the source abstracts.

### 7. Hybrid Text-Based and Graph-Based Retrieval-Augmented Generation (RAG)

NetMedEx integrates graph-based structural filtering with text-based retrieval-augmented generation (RAG) to enable evidence-grounded, LLM-driven semantic analysis of biomedical literature. Rather than applying conversational models directly to an untargeted corpus, NetMedEx constrains retrieval and generation through the intermediate semantic network, using the co-mention graph as a foundational scaffolding for deeper inquiry.

#### 7.1 Edge-Guided Literature Selection

Following network construction, users interactively select one or more edges of interest within the graph visualization. Each edge represents a relationship between two biomedical entities and is associated with one or more PubMed identifiers (PMIDs) corresponding to source articles. The selected edges define a focused subgraph, from which the union of associated PMIDs is extracted.

This edge-guided selection step serves as an explicit user-driven filter that narrows the literature scope prior to conversational analysis, ensuring that subsequent retrieval is limited to conceptually relevant documents.

#### 7.2 Abstract Retrieval and Preprocessing

For each selected PMID, the corresponding abstract text is retrieved from a locally cached corpus or via standardized bibliographic sources. Abstracts are deduplicated and normalized, and metadata such as publication year and entity mentions are retained for downstream reference and citation.

Only abstracts explicitly linked to user-selected edges are included in the conversational knowledge base, preventing the inclusion of unrelated documents.

#### 7.3 Vector Index Construction

The retrieved abstracts are embedded into a vector representation using configurable embedding models (remote OpenAI `text-embedding-3-small`, or local sentence transformers), allowing users to balance performance, cost, and privacy. The resulting embeddings are stored in a local **ChromaDB** vector database, enabling efficient similarity-based retrieval. This vector index is constructed dynamically based on the selected subgraph, ensuring that the conversational context remains tightly coupled to the user's graph exploration.

#### 7.4 LLM-Assisted Semantic Analysis and Answer Generation

When a user submits a natural language query in the Chat Panel, the system performs similarity-based retrieval (inverted L2 distance) over the vector index to identify the most relevant abstracts from the structurally filtered subset. These retrieved documents are then supplied to a Large Language Model (e.g., GPT-4o). The LLM's primary role is to perform rigorous semantic analysis across the abstracts, synthesizing the explicit relationships and mechanisms that the initial co-mention scaffolding could only suggest. The Chat Panel supports multi-turn conversations, allowing users to refine queries and deep-dive into the nuanced biological context.

All generated responses are conditioned exclusively on the retrieved abstracts and are required to include explicit PMID citations. The system refrains from generating answers in the absence of retrieved evidence, enforcing grounding in the source literature.

#### 7.5 Provenance Tracking and Citation

Each conversational response includes clickable citations to PMIDs corresponding to the abstracts used during retrieval. This provenance information enables users to trace statements back to their original sources and supports manual verification of all generated content.

### 8. Conversational AI Safety and Grounding

NetMedEx is designed to support exploratory analysis while minimizing risks associated with ungrounded language model outputs. The conversational component operates under strict grounding constraints:

1. **Graph-scoped retrieval**: Conversational retrieval is limited to abstracts associated with user-selected graph edges, preventing the inclusion of irrelevant documents.
2. **RAG-only generation**: Language model outputs are conditioned solely on retrieved abstracts. If no relevant documents are retrieved, the system refrains from generating an answer.
3. **Mandatory citations**: All responses include explicit PMID citations, enabling users to verify statements against the original literature.
4. **Exploratory intent**: NetMedEx is intended for research exploration and hypothesis generation, not clinical decision-making. The system does not produce diagnostic recommendations or treatment guidance.

NetMedEx is implemented in Python (≥ 3.9) and provides a command-line interface (CLI) and web interface built with the **Dash** framework. Reflecting the dual-mode architecture, network visualization is powered by **Cytoscape.js**, serving as the central analytical hub for both modes. It enables interactive exploration, layout customization (Circular or Spring-embedded), and edge-weight filtering via an interactive range slider for base co-mention networks, while also serving as the interactive springboard for LLM-assisted semantic queries. The system is containerized using **Docker** for consistent deployment across environments. Users can also export networks as interactive HTML files or XGMML files for import into Cytoscape (Figure 2).

---

## Results

### System Overview and Workflow

NetMedEx is implemented as a modular web application that guides users through a streamlined three-stage workflow: **Search → Graph → Chat**. The interface is designed to be intuitive for biomedical researchers, requiring no programming expertise, while the CLI and Python API support reproducible computational pipelines. The web interface allows users to search for biomedical terms, construct the foundational co-mention network, and utilize the LLM-assisted Chat Panel to perform deep semantic analysis on targeted subnetworks. Users can download article abstracts, annotations, and generated networks for further analysis.

**Key interface features:**
1. Networks can be generated end-to-end from either article searches or manually uploaded PubTator files.
2. Users can enter text queries to retrieve relevant articles or specify PMIDs directly.
3. Networks can be filtered by node type (e.g., MeSH terms only or high-confidence relations) and weighting method (frequency or NPMI).
4. All graph elements are draggable; communities are enclosed in colored boxes with hub nodes highlighted.
5. Supporting evidence can be viewed by clicking on any graph element.
6. Networks can be exported as interactive HTML files or XGMML files compatible with Cytoscape.
7. Graph layout, edge weight cutoffs, and minimum node degree can be adjusted after network generation.

### Case Study 1: Summarizing Literature on Chuan Mu Tong

We tested NetMedEx's capability to summarize over 100 articles using "Chuan Mu Tong" as a query (Figure 3A). The results show that *Clematis armandii*, the scientific name for Chuan Mu Tong, is linked to "lignans," highlighting studies on the roles of lignans in Chuan Mu Tong (Pan et al., 2017). Lignans are also connected to "inflammation," with related studies suggesting an anti-neuroinflammatory effect (Xiong et al., 2014). This demonstrates how NetMedEx helps users quickly identify relevant articles, greatly reducing the time and effort needed to review a corpus.

### Case Study 2: Uncovering Cross-Topic Connections in Osteoporosis Research

Expanding our investigation, we queried "Osteoporosis AND Lignans" and obtained approximately 1,000 articles. The resulting network (Figure 3B) revealed frequent co-mentions of lignans and flavonoids in osteoporosis-related studies. A review of these articles identified research on active compounds treating osteoclast-mediated bone-destructive diseases (An et al., 2016; Xu et al., 2022; Zhang et al., 2016). Furthermore, studies discussing the estrogenic effects of lignans and flavonoids in reducing osteoporosis risk were also identified (Gorzkiewicz et al., 2021; Rietjens et al., 2017; Zhao et al., 2017). Thus, NetMedEx facilitates uncovering connections between diverse topics that have yet to be fully explored together.

### Case Study 3: Graph-Guided Conversational Discovery of Herb–miRNA–Osteoporosis Mechanisms

To demonstrate the Chat Panel's capability in uncovering complex regulatory mechanisms and to explicitly compare the resolution of baseline co-mention networks versus LLM-assisted semantic analysis, we applied NetMedEx to investigate the literature connecting **Osteoporosis**, **Herbal Medicine**, and **miRNAs**. After querying these concepts, NetMedEx retrieved a focused corpus and constructed a co-mention network. The network visualization separated nodes into distinct community clusters (Louvain method) corresponding to "Bone Resorption (Osteoclasts)," "Bone Formation (Osteoblasts)," and "Epigenetic Regulation (miRNAs)."

The network highlighted central nodes such as *Epimedium* (Herba Epimedii) and its active component *Icariin*, showing dense connections to *miR-21*, *miR-141*, and the *Wnt/β-catenin* signaling pathway. In the **baseline co-mention mode**, the static network simply displayed undirected edges between these entities based on statistical co-occurrence (e.g., between *Icariin* and *PTEN*). While this established a general statistical association, it lacked mechanistic clarity—failing to specify whether *Icariin* upregulates, downregulates, or acts independently of *PTEN* in the context of osteoporosis. The low-resolution structural network suggested a macro-level link to osteogenesis, but the specific directional and functional mediators required clarification.

By transitioning to the **LLM-assisted semantic analysis mode**, NetMedEx dramatically increased the analytical resolution. We interrogated the selected subgraph using the **Hybrid RAG Chat Panel**:

> **Query**: "How does Icariin regulate osteoblast differentiation through miRNAs?"

The system extracted the specific PMIDs associated with the selected edges, embedding their abstracts for text-based retrieval. The LLM processed this focused evidence base and transformed the ambiguous co-mentions into a precise, directional mechanistic insight: *"Icariin upregulates miR-21, which targets and inhibits PTEN, thereby activating the PI3K/Akt/mTOR pathway to promote osteoblastogenesis."* 

This direct comparison underscores a core advantage of introducing the LLM: it elevates the analysis from a low-resolution, undirected statistical association (co-occurrence) to a high-resolution, biologically meaningful mechanism (directional regulation and functional cascade). Furthermore, the response included clickable PMID citations to specific studies, enabling immediate validation of this LLM-synthesized mechanistic hypothesis.

---

## Limitations and Ethical Considerations

### Limitations

**First**, the semantic relationship extraction relies on large language models, which may occasionally produce incomplete or inconsistent outputs due to variability in model responses or ambiguous language in abstracts. To mitigate this risk, NetMedEx restricts analysis to explicitly stated relationships, requires supporting evidence sentences, and applies user-defined confidence thresholds to filter low-certainty predictions.

**Second**, semantic analysis is performed at the abstract level and does not incorporate full-text articles, supplementary materials, or figures. As a result, some relationships described outside abstracts may not be captured.

**Third**, confidence scores assigned by the LLM represent model-estimated certainty rather than calibrated probabilities and should be interpreted comparatively rather than as absolute measures.

**Finally**, while semantic extraction improves precision over co-occurrence–based methods, it does not replace expert curation. Curated resources such as BioREx (Lai et al., 2023) remain essential for high-confidence knowledge integration.

### Ethical Considerations

NetMedEx does not generate novel biomedical claims or clinical recommendations. All extracted relationships are directly grounded in published literature, and evidence sentences are preserved to enable human verification. The system is intended for exploratory literature analysis and hypothesis generation rather than clinical decision-making.

When using external LLM services, users are responsible for complying with relevant data usage and privacy policies. NetMedEx processes only publicly available bibliographic text and does not require the input of personal or sensitive patient data.

---

## Future Directions

NetMedEx has advanced beyond baseline co-mention networks by integrating Large Language Models (LLMs) to provide precise, semantic relationship extraction and natural language interfaces. While the current hybrid Text-Based and Graph-Based Retrieval-Augmented Generation (RAG) architecture already enables deep, mechanistic exploration of targeted subgraphs, there are several avenues for future enhancement:

1. **Expanded Knowledge Bases**: While current semantic extraction relies on biomedical text, integrating structured databases such as ClinVar, DrugBank, and Gene Ontology (GO) would enrich the network with canonical, curated knowledge, providing a more comprehensive evidence base.
2. **Multi-Modal RAG**: The current retrieval focuses on abstract text. Incorporating multi-modal models to parse and index images, figures, and tables from full-text articles would allow users to query and extract insights directly from experimental results.
3. **Personalized Knowledge Graphs**: Future iterations could empower users to upload private PDF collections or internal experimental notes. This would allow NetMedEx to serve as a secure, private research assistant capable of synthesizing proprietary lab data with public PubMed knowledge.
4. **Automated Subgraph Exploration**: Currently, the hybrid RAG system relies on user-driven edge selection. Developing predictive algorithms that automatically highlight the most biologically actionable or statistically anomalous subgraphs for LLM analysis could further accelerate hypothesis generation.

---

## References

An, J., Hao, D., Zhang, Q., Chen, B., Zhang, R., Wang, Y., & Yang, H. (2016). Natural products for treatment of bone erosive diseases: The effects and mechanisms on inhibiting osteoclastogenesis and bone resorption. *International immunopharmacology*, 36, 118–131.

Blondel, V. D., Guillaume, J. L., Lambiotte, R., & Lefebvre, E. (2008). Fast unfolding of communities in large networks. *Journal of Statistical Mechanics-Theory and Experiment*, Article P10008. https://doi.org/10.1088/1742-5468/2008/10/p10008

Gorzkiewicz, J., Bartosz, G., & Sadowska-Bartosz, I. (2021). The potential effects of phytoestrogens: The role in neuroprotection. *Molecules*, 26(10), 2954.

Harman, D. (1991). How effective is suffixing? *Journal of the American Society for Information Science*, 42(1), 7–15. https://doi.org/10.1002/(sici)1097-4571(199101)42:1

Lai, P. T., Wei, C. H., Luo, L., Chen, Q. Y., & Lu, Z. Y. (2023). BioREx: Improving biomedical relation extraction by leveraging heterogeneous datasets. *Journal of Biomedical Informatics*, 146, Article 104487. https://doi.org/10.1016/j.jbi.2023.104487

Milosevic, N., & Thielemann, W. (2023). Comparison of biomedical relationship extraction methods and models for knowledge graph creation. *Journal of Web Semantics*, 75, Article 100756. https://doi.org/10.1016/j.websem.2022.100756

Pan, L.-L., Wang, X.-L., Luo, X.-L., Liu, S.-Y., Xu, P., Hu, J.-F., & Liu, X.-H. (2017). Boehmenan, a lignan from the Chinese medicinal plant *Clematis armandii*, inhibits A431 cell growth via blocking p70S6/S6 kinase pathway. *Integrative Cancer Therapies*, 16(3), 351–359.

Phan, L. N., Anibal, J. T., Tran, H., Chanana, S., Bahadroglu, E., Peltekian, A., & Altan-Bonnet, G. (2021). Scifive: a text-to-text transformer model for biomedical literature. arXiv preprint arXiv:2106.03598.

Rietjens, I. M., Louisse, J., & Beekmann, K. (2017). The potential health effects of dietary phytoestrogens. *British journal of pharmacology*, 174(11), 1263–1280.

Wei, C. H., Allot, A., Lai, P. T., Leaman, R., Tian, S. B., Luo, L., Jin, Q., Wang, Z. Z., Chen, Q. Y., & Lu, Z. Y. (2024). PubTator 3.0: an AI-powered literature resource for unlocking biomedical knowledge. *Nucleic Acids Research*, 52(W1), W540–W546. https://doi.org/10.1093/nar/gkae235

Wei, C. H., Allot, A., Leaman, R., & Lu, Z. Y. (2019). PubTator central: automated concept annotation for biomedical full text articles. *Nucleic Acids Research*, 47(W1), W587–W593. https://doi.org/10.1093/nar/gkz389

Xiong, J., Bui, V.-B., Liu, X.-H., Hong, Z.-L., Yang, G.-X., & Hu, J.-F. (2014). Lignans from the stems of *Clematis armandii* ("Chuan-Mu-Tong") and their anti-neuroinflammatory activities. *Journal of ethnopharmacology*, 153(3), 737–743.

Xu, Q., Cao, Z., Xu, J., Dai, M., Zhang, B., Lai, Q., & Liu, X. (2022). Effects and mechanisms of natural plant active compounds for the treatment of osteoclast-mediated bone destructive diseases. *Journal of Drug Targeting*, 30(4), 394–412.

Zhang, N.-D., Han, T., Huang, B.-K., Rahman, K., Jiang, Y.-P., Xu, H.-T., Qin, L.-P., Xin, H.-L., Zhang, Q.-Y., & Li, Y.-m. (2016). Traditional Chinese medicine formulas for the treatment of osteoporosis: implication for antiosteoporotic drug discovery. *Journal of ethnopharmacology*, 189, 61–80.

Zhao, Y., Zheng, H.-X., Xu, Y., & Lin, N. (2017). Research progress in phytoestrogens of traditional Chinese medicine. *Zhongguo Zhong yao za zhi*, 42(18), 3474–3487.

---

- **Dual-Mode Discovery Paradigm**: Offers both a rapid, non-LLM **co-mention analysis mode** for broad structural visualization, and an advanced **LLM-assisted semantic analysis mode** for deep, mechanistic discovery.
- **Central Graph-Guided Exploration**: Regardless of the active mode, the interactive **Graph Panel** serves as the primary interface to dissect literature data, filter noise, and target specific relationships.
- **Hybrid Conversational RAG**: Features a **Hybrid Text-Based and Graph-Based RAG Chat Panel** that leverages the LLM to perform rigorous semantic analysis exclusively on abstracts associated with user-selected subgraph edges.
- **Targeted Knowledge Extraction**: Constructs foundational networks from over **30 million PubMed articles**, allowing precise identification of genes, diseases, chemicals, and species via PubTator3.
- **Evidence-Grounded AI Safety**: All advanced semantic responses are conditioned exclusively on explicitly retrieved abstracts, with mandatory PMID citations—preventing hallucination and ensuring verifiability.
- **Reproducible & Scalable Deployment**: Delivered as a fully containerized **Docker** image for seamless local execution, with support for CLI and Python API for high-throughput analysis pipelines.

---

## Keywords

Biomedical Text Mining; Network Medicine; Graph-Guided Retrieval-Augmented Generation (RAG); Large Language Models (LLMs); PubTator3; Co-mention Network; Osteoporosis; MicroRNAs (miRNAs); Herbal Medicine; Knowledge Discovery

---

## Figure and Table Suggestions

### Existing Figures (from docx v0.8)

**Figure 1 — Workflow of NetMedEx for generating co-mention networks for biomedical concepts.**
*Suggestion*: Consider adding a "Chat" stage at the end of the workflow diagram (after "Network Construction") to make the three-stage Search → Graph → Chat pipeline immediately visible. Annotate the Chat stage with "Graph-Guided RAG" to clarify the connection from network to conversational AI.

**Figure 2 — NetMedEx web interface.**
*Suggestion*: The current screenshot likely reflects the pre-Chat Panel UI. Update to show the three-tab interface (Search / Graph / Chat) in the sidebar. Ensure the advanced settings panel (with API key input and model selector) is visible or referenced in the legend. Expand the legend to 8 items by adding:
- (7) Interactive edge weight slider for NPMI/Frequency filtering
- (8) Chat Panel with Hybrid RAG interface and citation list

**Figure 3 — Co-mention networks generated by NetMedEx.**
*Caption update (A)*: "Chuan Mu Tong" (105 PubMed abstracts). *(B)*: "Osteoporosis AND Lignans" (most recent 1,000 of 1,084 PubMed abstracts).
*Suggestion*: The two panels are sufficient for demonstrating network construction. Consider adding node/edge statistics (total nodes, edges, communities) to each sub-caption for completeness.

### Proposed New Figure

**Figure 4 — Graph-guided conversational exploration of herb–miRNA–osteoporosis mechanisms (Case Study 3).**
This figure should consist of two or three panels:
- **(A) Focused subgraph**: Show selected edges between *Epimedium*/*Icariin* and miRNA nodes (miR-21, miR-141) and the Wnt/β-catenin pathway with Louvain community coloring. Highlight the user-selected edges in a distinct color to illustrate the edge-guided selection mechanism.
- **(B) Chat Panel interaction**: A screenshot of the Chat Panel showing the user query ("How does Icariin regulate osteoblast differentiation through miRNAs?"), the AI-generated mechanistic answer, and the clickable PMID citation list.
- **(C, optional) Mechanistic diagram**: A simplified pathway schematic showing the proposed Icariin → miR-21 → PTEN → PI3K/Akt/mTOR → Osteoblast differentiation axis, generated based on the retrieved evidence.

*Caption*: "Figure 4. Graph-guided conversational exploration of herb-mediated osteoporosis therapy via miRNAs. (A) Co-mention subgraph of Epimedium-related compounds and miRNA nodes identified in the Osteoporosis–Herbal Medicine–miRNA corpus, with user-selected edges highlighted. (B) Chat Panel screenshot showing a natural language query and the evidence-grounded response with PMID citations. (C) Proposed mechanistic pathway of Icariin-mediated osteoblast differentiation through miR-21–PTEN–PI3K/Akt/mTOR signaling, as suggested by the retrieved literature."
