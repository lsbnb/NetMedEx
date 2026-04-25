# NetMedEx: A Graph-Guided Retrieval-Augmented Platform for Conversational Exploration of Biomedical Literature

### Abstract
Biomedical knowledge is distributed across tens of millions of publications, making integrative discovery intractable. We present **NetMedEx**, an open-source platform that transforms PubMed literature into interactive biological networks. NetMedEx (v1.2.0) integrates two complementary discovery modes: (i) co-mention network construction from over 30 million PubMed articles via PubTator3, and (ii) a **Smart 2-hop Hybrid Retrieval-Augmented Generation (RAG)** mode. This advanced retrieval logic uses user-selected nodes as anchors to explore latent 2-hop mechanistic paths, prioritized by a **calibrated scoring system** that integrates topological strength (NPMI), LLM-extracted confidence, and query-aware semantic relevance. To ensure scientific rigor, NetMedEx implements **automated species-aware study-type differentiation**, explicitly distinguishing animal/in vitro models from human clinical findings to prevent false inferences. Case studies in osteoporosis demonstrate its utility in identifying a mechanistic Icariin–miR-21–PTEN axis, with each claim traceable to clickable PMID citations. NetMedEx is available as a Docker image and Python package, supporting reproducible discovery via a web interface, CLI, and API.

---

The exponential growth of biomedical literature has created a paradoxical challenge: while the volume of available knowledge is vast, synthesizing it into coherent, actionable biological insights has become increasingly difficult. PubMed alone indexes over 36 million citations, with thousands of new articles published daily. Traditional methods of literature review are labor-intensive and often limit the analytical scope to a narrow set of papers. High-throughput text mining approaches can aggregate massive datasets, but typically strip away the semantic context required to understand complex biological mechanisms.

Biological systems are inherently networked. Genes, proteins, metabolites, and diseases interact through intricate pathways, and network medicine approaches have been developed to model these relationships<sup>1</sup>. Existing co-mention and knowledge graph tools—such as STRING<sup>2</sup>, iTextMine<sup>3</sup>, and PubTator3<sup>4</sup>—provide structured macroscopic overviews by extracting entity associations at scale. However, once a network is visualized, the analytical process often reaches a "static wall": researchers can see connections but lack an efficient, grounded mechanism to query the underlying evidence without manually revisiting source literature.

The emergence of Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG)<sup>5</sup> has enabled conversational interfaces for large corpora. More recently, graph-enhanced RAG frameworks—including Microsoft's GraphRAG<sup>6</sup>—have demonstrated that incorporating community-structured knowledge graphs substantially improves retrieval coherence over flat vector search. However, applying RAG directly to biomedical literature presents distinct challenges, particularly the risk of hallucinated mechanisms and the lack of a principled mechanism for users to scope retrieval to their specific research question.

To bridge this gap, we developed **NetMedEx**, a platform that offers two complementary modes for literature discovery: a rapid **co-mention analysis mode** (without LLM dependency) and an advanced **LLM-assisted semantic analysis mode** uniquely anchored to user-driven subgraph selection. NetMedEx leverages the precision of **PubTator3**<sup>4</sup> to extract biological concepts from over 30 million PubMed articles. In its baseline mode, it utilizes Normalized Pointwise Mutual Information (NPMI) and Louvain community clustering<sup>7</sup> to generate interactive co-mention networks. To ensure operational transparency during AI extraction, NetMedEx provides a **Semantic Diagnostics** suite that reports real-time metrics on article processing success and entity coverage. The resulting network acts as structural **scaffolding**: the AI-driven semantic layer then breathes life into these connections by extracting evidence and answering natural language queries—grounded exclusively in user-targeted subgraphs.

When researchers require deeper mechanistic insights, they can activate NetMedEx's interactive **Chat Panel** driven by a **Smart 2-hop Hybrid RAG** framework (v1.2.0). In contrast to standalone LLM tools or flat RAG systems, NetMedEx explores connections up to two hops from user-targeted nodes to uncover latent mechanisms (e.g., A → B → C). To maintain precision during graph expansion, the system utilizes a **Hybrid Scoring 2.0** formula that weights topological evidence (NPMI), semantic confidence, and query relevance. Crucially, the system implements **Ontology Filtering** to automatically prune non-biomedical noise (e.g., species or location nodes) during traversal, focusing exclusively on core biological entities like genes and diseases.

---

## Results

### System Overview and Comparison with Related Tools
NetMedEx addresses a capability gap not jointly covered by existing tools (**Table 1**). Unlike representative biomedical literature mining platforms, NetMedEx provides bidirectional coupling between the graph layer and the conversational layer: the network structure scopes the RAG retrieval (graph → text), and conversely, LLM-extracted semantic labels can augment the graph with directed edges (text → graph).

**Table 1. Functional comparison of NetMedEx with related biomedical tools.**
| Feature | NetMedEx | STRING (v12) | iTextMine | PubTator3 | BioGPT |
|---|---|---|---|---|---|
| Co-mention network (real-time) | ✓ | ✗ | ✓ | ✗ | ✗ |
| Graph-guided RAG | ✓ | ✗ | ✗ | ✗ | ✗ |
| LLM-powered query | ✓ | ✗ | ✗ | ✗ | ✓ |
| Hallucination grounding | ✓ | N/A | ✗ | N/A | ✗ |
| Interactive visualization | ✓ | ✓ | ✓ | ✗ | ✗ |
| Export to Cytoscape (XGMML) | ✓ | ✓ | ✗ | ✗ | ✗ |

### System Workflow
NetMedEx guides users through a streamlined three-stage workflow: **Search → Graph → Chat**. 
- **Search Panel**: Users define research scope using natural language (automatically converted to PubTator3 syntax), keywords, or PMIDs. 
- **Graph Panel**: Visualizes co-mention networks with community detection (Louvain method). Users use a sub-selection tool (Shift-select) to isolate sub-networks of interest.
- **Chat Panel**: Constructs the Hybrid RAG from the selected sub-network. To maintain accuracy for non-English queries, NetMedEx employs a multi-stage intermediary reasoning chain—translating the query to scientific English, performing retrieval and synthesis in English, and translating the integrated answer back to the session language. Responses include hyperlinked PMID citations for immediate verification.

### Mechanistic Discovery of Herb–miRNA–Osteoporosis Interactions
To explicitly compare the analytical resolution of co-mention networks versus LLM-assisted semantic analysis, we applied NetMedEx to investigate the literature connecting **Osteoporosis**, **Herbal Medicine**, and **miRNAs** (**Figure 4**). 

The baseline co-mention mode displayed undirected edges between entities like *Icariin* and *PTEN* based on statistical co-occurrence. While this established an association, it lacked mechanistic clarity. For example, previous studies on *Clematis armandii* (Case Study 1) identified lignans as active components in inflammatory models<sup>9,10</sup>, while research in osteoporosis (Case Study 2) has highlighted the role of various phytoestrogens and plant active compounds<sup>11-16</sup>. By transitioning to the **LLM-assisted semantic analysis mode**, we queried the subgraph: *"How does Icariin regulate osteoblast differentiation through miRNAs?"*.

The system provided a precise mechanistic insight: *"Icariin regulates osteoblast differentiation through specific miRNAs such as miR-153 and miR-23a-3p... targeting Runx2 through miR-153 and affecting WNT/beta-catenin via miR-23a-3p."* Manual verification confirmed a citation accuracy of 100%, with each constituent claim traceable to explicitly cited PMIDs. To further validate robustness, we tested the system using local LLMs (e.g., `gemma3:12b`), demonstrating that our specialized **compact prompt strategy** and **context window management** (capping local RAG context to 8 prioritized abstracts) preserved analytical precision even on limited-resource hardware. This underscores the core advantage: elevating analysis from undirected statistical associations to biologically meaningful mechanisms across diverse compute environments.

---

## Discussion
NetMedEx demonstrates that graph-guided scoping is a powerful strategy for grounding LLMs in highly specialized biomedical domains. By allowing users to interactively define the literature context through a structural scaffold, the system bypasses the "black box" nature of typical RAG implementations. The integration of local LLM support and the **"Intermediary English Synthesis"** reasoning chain ensure that the platform remains scientifically rigorous for international researchers while maintaining high operational stability (v0.9.9). Future directions include integrating structured databases (ClinVar, GO) and expanding retrieval to full-text articles<sup>17</sup> and embedded figures.

---

## References
1. Barabási, A.-L. et al. Network medicine: a network-based approach to human disease. *Nat. Rev. Genet.* **12**, 56–68 (2011).
2. Szklarczyk, D. et al. The STRING database in 2023: protein-protein association networks and functional enrichment analysis for any sequenced genome of interest. *Nucleic Acids Res.* **51**, D638–D646 (2023).
3. Ding, J. et al. iTextMine: integrated text-mining system for large-scale knowledge extraction from the literature. *Database* **2020**, baaa079 (2020).
4. Wei, C. H. et al. PubTator 3.0: an AI-powered literature resource for unlocking biomedical knowledge. *Nucleic Acids Res.* **52**, W540–W546 (2024).
5. Lewis, P. et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Adv. Neural Inf. Process. Syst.* **33**, 9459–9474 (2020).
6. Edge, D. et al. From Local to Global: A Graph RAG Approach to Query-Focused Summarization. *arXiv preprint arXiv:2404.16130* (2024).
7. Blondel, V. D. et al. Fast unfolding of communities in large networks. *J. Stat. Mech. Theory Exp.* **2008**, P10008 (2008).
9. Pan, L.-L. et al. Boehmenan, a lignan from the Chinese medicinal plant *Clematis armandii*, inhibits A431 cell growth via blocking p70S6/S6 kinase pathway. *Integr. Cancer Ther.* **16**, 351–359 (2017).
10. Xiong, J. et al. Lignans from the stems of *Clematis armandii* ("Chuan-Mu-Tong") and their anti-neuroinflammatory activities. *J. Ethnopharmacol.* **153**, 737–743 (2014).
11. An, J. et al. Natural products for treatment of bone erosive diseases: The effects and mechanisms on inhibiting osteoclastogenesis and bone resorption. *Int. Immunopharmacol.* **36**, 118–131 (2016).
12. Xu, Q. et al. Effects and mechanisms of natural plant active compounds for the treatment of osteoclast-mediated bone destructive diseases. *J. Drug Target.* **30**, 394–412 (2022).
13. Zhang, N.-D. et al. Traditional Chinese medicine formulas for the treatment of osteoporosis: implication for antiosteoporotic drug discovery. *J. Ethnopharmacol.* **189**, 61–80 (2016).
14. Gorzkiewicz, J. et al. The potential effects of phytoestrogens: The role in neuroprotection. *Molecules* **26**, 2954 (2021).
15. Rietjens, I. M. et al. The potential health effects of dietary phytoestrogens. *Br. J. Pharmacol.* **174**, 1263–1280 (2017).
16. Zhao, Y. et al. Research progress in phytoestrogens of traditional Chinese medicine. *Zhongguo Zhong Yao Za Zhi* **42**, 3474–3487 (2017).
17. Westergaard, D. et al. A comprehensive and quantitative comparison of text-mining in 15 million full-text articles versus their corresponding abstracts. *PLoS Comput. Biol.* **14**, e1005962 (2018).
18. Lai, P. T. et al. BioREx: Improving biomedical relation extraction by leveraging heterogeneous datasets. *J. Biomed. Inform.* **146**, 104487 (2023).
19. Wei, C. H. et al. PubTator central: automated concept annotation for biomedical full text articles. *Nucleic Acids Res.* **47**, W587–W593 (2019).
20. Harman, D. How effective is suffixing? *J. Am. Soc. Inf. Sci.* **42**, 7–15 (191).

---

## Methods

### Data Retrieval and Normalization
NetMedEx leverages the PubTator3 API<sup>4</sup> to retrieve PubMed abstracts annotated with biomedical concepts. For international accessibility, the system integrates an LLM-based Universal Translation Engine that automatically detects CJK character ranges and executes an "English Intermediary" translation for both search and RAG retrieval. Concept mentions are normalized using MeSH standardized terms or conservative plural stemming<sup>20</sup>.

### Network Construction
Co-occurrence networks are constructed where nodes represent entities and edges represent co-occurrence counts. Edge weights are calculated using either scaled frequency or Normalized Pointwise Mutual Information (NPMI). NPMI is used to prune non-specific associations (default threshold 0.2). Community detection is performed using the Louvain method, identifying functional clusters of related terms.

### Hybrid RAG and Mechanism Discovery (v1.2.0)
The Hybrid RAG framework combines graph-based structural filtering with text-based vector retrieval. In version 1.2.0, NetMedEx implements a **Smart 2-hop Retrieval** algorithm. When a user selects anchor nodes, the system traverses up to two hops in the knowledge graph. To reduce false inferences, we apply **Bottleneck Scoring**: the score of a 2-hop path is defined as `min(score_link1, score_link2) * 0.8`, where the 0.8x penalty acknowledges the inherent uncertainty of indirect evidence. Path links are individually scored via **Hybrid Scoring 2.0**: `Score = (NPMI × 0.3) + (Confidence × 0.4) + (Relevance × 0.3)`. Confidence is calibrated by **Mechanistic Boosts** (1.1x for directional verbs like *inhibits*) and **Evidence Consensus** (+5% boost per supporting PMID). Furthermore, the system performs **Species-Aware Study-Type Differentiation**: abstracts are automatically scanned for non-human species nodes; if detected, the context provided to the LLM is explicitly labeled as `[Animal Model/In vitro]`, and the system prompt enforces a strict distinction between preclinical findings and human clinical facts. Vector retrieval using **ChromaDB** and local or remote LLMs completes the reasoning chain, with mandatory PMID grounding for all claims.

## Data Availability
Biomedical concept annotations and article metadata are retrieved via the PubTator3 API (https://www.ncbi.nlm.nih.gov/research/pubtator/). Sample datasets used in Case Studies are available in the GitHub repository.

## Code Availability
NetMedEx is open-source under the MIT License. Source code is available at https://github.com/lsbnb/NetMedEx. Docker images are available at https://hub.docker.com/r/lsbnb/netmedex.

## Competing Interests
The authors declare no competing interests.

---

## Figure Legends

**Figure 1. NetMedEx system workflow diagram.** The pipeline proceeds through three stages: (1) Search & Retrieval—users input natural language queries, keywords, or PMIDs; the LLM converts natural language to PubTator3 syntax; articles are retrieved via the PubTator3 API; (2) Network Construction—entities are extracted, normalized via MeSH standardization, and co-occurrence statistics (NPMI or frequency) are computed; the Louvain algorithm identifies community structure; (3) Chat & RAG—users select subgraph edges; associated abstracts are retrieved, embedded in ChromaDB, and provided to the LLM for evidence-grounded semantic analysis. For local models, the system applies adaptive context truncation to fit hardware-specific limits.

**Figure 2. NetMedEx web interface layout and diagnostic features.** (1) **Search Tab** allowing for direct text queries or file-based inputs, now featuring a **Semantic Diagnostics** alert that provides real-time metrics on processing success and entity coverage (v0.9.7 update). (2) **Graph Tab** providing statistical summaries, community toggles, and interactive control over display layouts (fCose node repulsion). (3) **Chat Tab** demonstrating the multi-turn conversational hybrid RAG interface with smart auto-scroll and hyperlinked PMID citations. (4) Main Graph View with dynamic bottom-overlay panels for detailed node and edge examination.

**Figure 3. Co-mention networks generated by NetMedEx.** **(A)** Network for "Chuan Mu Tong" (105 PubMed abstracts; NPMI threshold 0.2). Hub nodes include *Clematis armandii*, lignans, and inflammation-related terms. **(B)** Network for "Osteoporosis AND Lignans" (most recent 1,000 of ~1,084 PubMed abstracts). Node size is proportional to degree; edge width reflects NPMI score.

**Figure 4. Graph-guided conversational exploration of herb-mediated osteoporosis therapy via miRNAs.** **(A)** Co-mention subgraph with Louvain community clusters color-coded. User-selected edges are shown in pink highlight. **(B)** Chat Panel showing the natural language query ("How does Icariin regulate osteoblast differentiation through miRNAs?") and the evidence-grounded LLM response with clickable PMID citations. **(C)** Proposed mechanistic pathway of Icariin-mediated osteoblast differentiation synthesized from retrieved literature evidence.
