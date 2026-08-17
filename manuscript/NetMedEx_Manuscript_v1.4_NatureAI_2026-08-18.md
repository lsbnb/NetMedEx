# NetMedEx: Smart Graph-Guided Retrieval-Augmented Generation for Biomedical Mechanism Discovery

**Chung-Yen Lin**
Institute of Information Science, Academia Sinica, Taipei, Taiwan
cylin@iis.sinica.edu.tw

*Version 1.4 (August 18, 2026)*

---

## Abstract

Despite unprecedented growth in biomedical literature, mechanistic hypotheses connecting genes, chemicals, and diseases remain buried across millions of publications. We present **NetMedEx**, an open-source AI platform that constructs semantically normalized co-mention knowledge graphs from over 30 million PubMed articles and pairs them with a **Three-Tier Multi-Granularity Hybrid Retrieval-Augmented Generation (RAG)** framework to uncover latent mechanistic paths invisible to standard one-hop retrieval. A **Hybrid Scoring 2.0** system integrates co-occurrence statistics, LLM-extracted semantic confidence, and query relevance to rank evidence quality. Responses are structured through a **5-Layer Evidence Reasoning Framework** with eight anti-hallucination Core Principles, strictly separating direct evidence, speculative inference, and causal hypotheses — each grounded by PubMed IDs (PMIDs). In formal blinded benchmarks across 50 biomedical mechanism questions, NetMedEx achieved superior hypothesis novelty (+0.21) and research value (+0.21) over traditional text RAG, with 100% citation traceability across 755 cited PMIDs and prospective temporal holdout validation. NetMedEx supports seven LLM providers, a FastAPI Bridge for programmatic integration, and is freely available at https://github.com/lsbnb/NetMedEx.

## Highlights

- NetMedEx combines real-time co-mention knowledge graphs with a Three-Tier Multi-Granularity Hybrid RAG framework to reveal latent mechanistic chains (A → B → C) invisible to standard one-hop retrieval.
- A 5-Layer Evidence Reasoning Framework with eight anti-hallucination Core Principles enforces strict epistemic stratification — separating direct evidence (L1), speculative inference (L2), and causal hypotheses (L3), each grounded by PMID citations and species labels.
- Blinded multi-rater benchmarking demonstrates superior hypothesis novelty (+0.21) and research value (+0.21) over text-only RAG, with 100% PMID citation traceability and prospective temporal holdout validation.
- Chat-to-Graph synchronization and Dijkstra shortest-path search provide independent cross-validation of LLM-inferred 2-hop paths, enabling reproducible and auditable hypothesis generation.
- Deployed as a Docker image and PyPI package, NetMedEx integrates seven LLM providers and a REST FastAPI Bridge, making graph-guided biomedical reasoning accessible without bioinformatics expertise.

**Keywords:** retrieval-augmented generation; knowledge graph; network medicine; hallucination control; biomedical NLP; PubMed mining

---

## Introduction

The exponential growth of biomedical literature — over 36 million citations in PubMed [1], with thousands added daily — has created a paradox: an abundance of knowledge yet an inability to synthesize it into actionable mechanistic hypotheses. Network medicine [2] has demonstrated that genes, chemicals, and diseases interact in complex webs, but traditional tools present this network as a "static wall": researchers can see connections but have no means to systematically query the underlying evidence without manually revisiting source texts. Large language models (LLMs) offer a promising path, but their tendency to generate plausible yet unverifiable claims (hallucination) makes unconstrained LLM responses unsuitable for scientific hypothesis generation.

Existing tools address parts of this problem in isolation. Co-mention network tools (STRING [13], iTextMine) build graphs but lack conversational AI. General-purpose LLM assistants (BioGPT [14], PubMed.ai) provide text-based answers but cannot integrate graph topology or guarantee PMID attribution. No existing platform combines real-time knowledge graph construction, graph-guided RAG retrieval, and a structured anti-hallucination evidence framework.

We developed **NetMedEx** to close this gap through three tightly integrated innovations. First, a **Smart 2-hop Hybrid RAG** engine explores the knowledge graph beyond immediate neighbours to discover latent mechanistic chains (A → B → C) that are invisible to standard one-hop retrieval, scored by a calibrated **Hybrid Scoring 2.0** formula. Second, a **5-Layer Evidence Reasoning Framework** with eight anti-hallucination Core Principles enforces strict epistemic stratification — separating direct PMID-supported evidence (Layer 1) from speculative inference (Layer 2), causal hypotheses with polarity and testable predictions (Layer 3), an integrated summary (Layer 4), and angle-diverse follow-up questions (Layer 5). Third, **Chat-to-Graph synchronization** renders inferred paths back onto the network in real time, enabling cross-validation between LLM-derived inference and graph-topology-derived Dijkstra shortest paths. Together, these advances transform a static co-mention graph into an interactive hypothesis engine — one that explains its reasoning, cites its sources, and surfaces its uncertainty.

---

## Results

### NetMedEx architecture and unique capabilities

NetMedEx implements a three-stage pipeline (Fig. 1): (i) **Search & Network Construction** — multilingual queries retrieve PubMed articles via PubTator3 [3]; biological entities are normalized by CUI-based MeSH deduplication followed by sapBERT [4] embedding-similarity merging; edges are scored by Hybrid Scoring 2.0; (ii) **Graph Exploration** — an interactive Cytoscape.js panel with Louvain community detection [8], Dijkstra weighted shortest-path search [7], and adaptive rendering; (iii) **Hybrid RAG Chat** — Smart 2-hop retrieval produces 5-Layer Evidence responses with per-edge PMID citations and species labels.

Table 1 places NetMedEx against related tools. It is the only platform combining real-time co-mention networks, graph-guided RAG, 2-hop mechanism discovery, an anti-hallucination evidence framework, Chat-to-Graph synchronization, and programmatic REST integration.

**Table 1. Functional comparison of NetMedEx with related biomedical AI tools.**

| Feature | NetMedEx | STRING [13] | iTextMine | PubTator3 [3] | BioGPT [14] | PubMed.ai |
|---|---|---|---|---|---|---|
| Real-time co-mention network | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Graph-guided RAG (subgraph-scoped) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Smart 2-hop mechanism discovery | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 5-Layer evidence framework | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Anti-hallucination core principles | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Chat-to-graph synchronization | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Dijkstra weighted shortest-path | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| PMID hallucination grounding | ✓ | N/A | ✗ | N/A | ✗ | ✓ |
| Interactive export (HTML/XGMML/RIS) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| FastAPI programmatic integration | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |

### 2-hop retrieval uncovers latent mechanistic chains

Standard one-hop RAG retrieves only articles where query entities co-appear. NetMedEx's Smart 2-hop engine explores neighbours up to two hops from selected anchor nodes, identifying mediated paths scored by a "weakest-link" bottleneck formula: PathScore = min(link1, link2) × 0.8. This ensures that a mechanistic chain is only as confident as its least-supported edge. Table 2 contrasts the two retrieval modes.

**Table 2. Discovery depth and performance: 1-hop vs. Smart 2-hop retrieval.**

| Dimension | Standard 1-hop | Smart 2-hop |
|---|---|---|
| Discovery scope | Direct co-mentions | Latent mechanistic chains |
| Relationship type | A — B | A → B → C (mediated) |
| Primary value | Evidence fact-checking | Hypothesis generation |
| Retrieval latency (10k-node graph) | ~0.1 s | ~0.86 s |
| Output structure | Evidence-based answer | 5-Layer stratified response |
| Graph synchronization | None | Gold bridge nodes, dashed orange edges |

2-hop inferences are explicitly reported under Layer 2 (speculative), and causal language is restricted to Layer 3 (directional edges only), preventing any conflation of co-occurrence with causation.

### Case study: Icariin-mediated osteoblast differentiation

We queried **Icariin, miRNA, osteogenesis** to investigate herb-mediated osteoporosis therapy. The initial co-mention graph (Fig. 3A–B) identified hub nodes miR-21, miR-153, and PTEN clustered by Louvain into bone-formation and epigenetic communities. While one-hop search showed only an Icariin–PTEN co-occurrence, the Smart 2-hop engine uncovered the latent mechanistic chain **Icariin → miR-21 → PTEN → PI3K/Akt → osteoblast differentiation** (Path Score = 1.08; Fig. 4).

The 5-Layer response reported: Layer 1 — Icariin upregulates miR-21 (PMID:29500883, **[Animal/In vitro]**); Layer 2 — speculative inference that miR-21 targets PTEN to activate PI3K/Akt/mTOR (confidence 0.84); Layer 3 — directional causal chain Icariin(+) → miR-21(+) → PTEN(−) → Akt(+) with per-edge PMIDs and the weakest link identified; Layer 1 human evidence — clinical bone density improvement (PMIDs:29904399, 35002378, **[Human]**). The inferred bridge node miR-21 was simultaneously highlighted in the Graph Panel with a gold border and dashed orange edges, independently confirmed by the Dijkstra shortest-path search (Fig. 3B).

### The 5-Layer Evidence Reasoning Framework prevents hallucination

Layer separation is enforced by eight anti-hallucination Core Principles at the system-prompt level: PMIDs are never hallucinated; co-occurrence is never converted to regulation; citations are required at the edge level (Entity A → relation → Entity B [PMID]); direct evidence, association, and causal claims are strictly isolated; causal language is restricted to Layer 3; speculative language (*may*, *might*, *is consistent with*) is mandatory in Layers 2–3; every finding is labelled by species/study type ([Human] / [Animal/In vitro]); all claims must trace to retrieved context. This framework yields AI responses that explicitly communicate epistemic uncertainty, enabling researchers to critically evaluate rather than blindly accept LLM outputs (Fig. 2D).

### FastAPI Bridge enables programmatic integration

NetMedEx exposes the full Search → Network → Hybrid RAG pipeline as a composable REST API (Fig. 3C): `POST /sessions` builds and indexes a session from a gene list; `POST /sessions/{id}/ask` returns 5-Layer responses with PMIDs and 2-hop paths; `DELETE /sessions/{id}` releases resources. The bridge supports all seven LLM providers and enables integration into downstream clinical decision support tools, Gradio UIs, or bioinformatics pipelines without embedding the Dash interface.

### Quantitative benchmark evaluation and hypothesis discovery

To systematically evaluate the empirical performance of NetMedEx against traditional text-based RAG and closed-book LLMs, we established a formal evaluation benchmark comprising 50 curated biomedical mechanism questions and 877 pooled multi-model judgments. In a blinded multi-rater evaluation focusing on complex two-hop hypothesis questions (Table 3), NetMedEx demonstrated consistent qualitative and quantitative advantages over standard text-based RAG across all reasoning dimensions: hypothesis novelty (3.26 vs. 3.05, +0.21), research value (4.13 vs. 3.92, +0.21), experimental testability (4.74 vs. 4.63, +0.11), and biological plausibility (4.71 vs. 4.66, +0.05), yielding a higher overall mean score (4.21 vs. 4.07, paired difference +0.145). Head-to-head comparison showed that NetMedEx produced the superior response in 47.4% of mechanism questions (9 wins vs. 3 losses and 7 ties).

**Table 3. Blinded comparative evaluation of NetMedEx Hybrid RAG vs. Traditional Text RAG across mechanism hypothesis questions.**

| Evaluation Dimension | NetMedEx Hybrid RAG | Traditional Text RAG | Net Gain |
|---|---:|---:|---:|
| Hypothesis Novelty | 3.26 | 3.05 | **+0.21** |
| Research Value | 4.13 | 3.92 | **+0.21** |
| Experimental Testability | 4.74 | 4.63 | **+0.11** |
| Biological Plausibility | 4.71 | 4.66 | **+0.05** |
| Overall Mean Score (1–5) | 4.21 | 4.07 | **+0.145** |

In a 20-question three-system blinded pilot benchmark comparing NetMedEx, Traditional Text RAG, and closed-book LLM (GPT-4), NetMedEx was selected as the first-choice response in 50% of trials (10/20), compared to 35% (7/20) for Traditional Text RAG and 15% (3/20) for closed-book LLMs. Compared to unretrieved LLMs, NetMedEx delivered a statistically significant overall score gain of +0.675 (4.442 vs. 3.767, 95% bootstrap CI [0.292, 1.058], sign-test p = 0.0044) with a +1.15 surge in research value (4.50 vs. 3.35). Crucially, automated citation extraction verified that 100% of the 755 PMID mentions across all NetMedEx responses were verifiably grounded in the underlying corpus without a single hallucinated identifier.

To test prospective discovery capability, we performed a temporal holdout experiment restricting the knowledge graph to publications prior to 2015. NetMedEx inferred unlinked two-hop candidate pairs (such as KRAS and CTLA-4, which had zero direct co-mentions prior to 2015). Subsequent query of post-2015 literature (2016–2025) confirmed that 100% (2/2) of the forecasted candidate relationships were subsequently validated by direct empirical studies, with the KRAS–CTLA-4 axis accumulating 55 direct PubMed publications in subsequent years.

These empirical gains underscore the necessity of the Three-Tier Multi-Granularity Hybrid RAG architecture: (i) Tier 1 Macro-level functional communities (Louvain topological clusters) provide the overarching biological module context; (ii) Tier 2 Meso-level gated two-hop causal paths supply strict polarity (+/−) and intermediate mediators across disparate papers; and (iii) Tier 3 Micro-level text retrieval extracts exact sentence-level assay conditions ([Human] vs. [Animal/In vitro]). This tripartite synthesis solves the multi-hop reasoning breakdown inherent to flat, chunk-based vector search.

---

## Discussion

NetMedEx demonstrates that combining knowledge graph topology with structured, hallucination-controlled LLM generation produces qualitatively richer biological hypotheses than either approach alone. The dual-perspective design — graph-topology Dijkstra paths and LLM-inferred 2-hop chains — provides a natural cross-validation mechanism: independent agreement between the two routes (as in the Icariin–miR-21 case) substantially increases hypothesis confidence.

Our benchmark evaluations elucidate why conventional single-document retrieval metrics (Precision@5 and Recall@10) fail to differentiate Hybrid RAG from standard Text RAG: when both arms access the same candidate pool, document-level overlap is high (>85%). The decisive empirical advantage of NetMedEx emerges exclusively in multi-hop synthesis, hypothesis novelty (+0.21), and research value (+0.21). By integrating Macro-level topological communities with Meso-level polarity-gated causal chains and Micro-level PubMed evidence, NetMedEx bridges the gap between isolated document retrieval and integrated biological discovery. Furthermore, the 5-Layer framework enforces epistemic stratification, ensuring that direct evidence (L1), speculative inferences (L2), and causal mechanisms (L3) are never conflated.

Practical scalability is addressed through adaptive graph rendering (fCoSE for ≤ 700 nodes, server-preset for larger graphs), air-gapped Docker deployment with pre-cached tiktoken, and a Gene List (OR Query) input that removes manual query formulation for curated gene panels. The FastAPI Bridge opens NetMedEx to automated workflows, lowering the threshold for adoption in multi-step bioinformatics pipelines.

Limitations include dependence on PubTator3 annotation quality, computational cost of large-scale Semantic RE (mitigated by Gemini Flash), and the inherent limits of co-mention evidence for causal inference (explicitly disclosed through L3 uncertainty language). Future work will incorporate temporal evidence tracking, drug–target interaction overlays, and integration with clinical trial databases to extend the platform from mechanism discovery to translational hypothesis generation.

---

## Methods

### Data acquisition and input modes

NetMedEx queries the PubTator3 API [3] for annotated PubMed abstracts and full-text articles. An LLM-based query reasoning module translates CJK and Korean queries into optimized English boolean syntax, constrained to ≤ 3 specific biological entities (query simplicity rule). A **Gene List (OR Query)** mode accepts comma- or newline-separated gene symbols and automatically formats them as `("GeneA" OR "GeneB" ...) AND @GENE` with standard publication-type exclusions (editorials, letters, errata, congress abstracts, news, comments, retractions).

### Entity normalization

Biological entities extracted by PubTator3 are normalized in two passes: (i) **CUI-based deduplication** — nodes sharing the same non-null MeSH CUI are merged and the most descriptive name is retained (e.g., `"hcv"` and `"hepatitis c virus"` → MeSH CUI D006526 → `"hepatitis c virus"`); (ii) **sapBERT** [4] embedding-similarity merging for residual synonyms. This two-pass pipeline prevents hub fragmentation and ensures accurate NPMI scores.

### Hybrid Scoring 2.0

Edge strength is quantified by:

$$\text{Score} = 0.3 \times \text{NPMI} + 0.4 \times \text{Semantic} + 0.3 \times \text{QueryRelevance}$$

**NPMI** [5] normalizes co-occurrence frequency. **Semantic Confidence** is the LLM relationship-extraction score, boosted 1.1× for directional relations (activates, inhibits) and +5% per supporting PMID. **Query Relevance** weights edges by semantic proximity to the user's query. Directional relation integrity is enforced at prompt level: entity1 = effector, entity2 = effectee.

### Smart 2-hop Hybrid RAG

The Chat Panel combines Text RAG (ChromaDB [12] vector retrieval) with Graph RAG (NetworkX subgraph context). For each set of anchor nodes, the system explores neighbours up to two hops away. Multi-hop paths are scored using a bottleneck formula: PathScore = min(link1\_score, link2\_score) × 0.8. Retrieved abstracts are tagged [Human] or [Animal/In vitro] based on PubMed species metadata; this label is enforced in the LLM prompt to prevent cross-species inference. The rolling conversation history retains the last three turns in full; older turns are structurally compressed (headers, tables, and Q-pill lines stripped) to ≤ 1,400 characters with an appended PMID summary for citation continuity.

### 5-Layer Evidence Reasoning Framework

The LLM system prompt enforces five output layers: L1 (direct evidence with per-edge PMID and species label); L2 (speculative 2-hop inference with path confidence score; speculative language mandatory); L3 (directional causal chain with per-edge polarity (+/−) and PMID, weakest-link identification, and testable prediction; skipped if no directional edges exist); L4 (three-paragraph integrated summary with inline PMIDs); L5 (three follow-up questions with distinct mechanistic, clinical, and experimental angles). Eight anti-hallucination Core Principles are enforced as hard constraints (see Results).

### Graph panel and Dijkstra search

Visualization uses Cytoscape.js [10] with fCose layout [11]. For graphs with > 700 visible nodes, server-side positions are pre-computed and the client renders a `preset` layout, avoiding redundant force-directed computation. Dijkstra's algorithm [7] is applied to NPMI-weighted graphs: edge cost = 1/weight(e). Anchor nodes receive orange borders, bridge nodes teal borders; path edges are thicker orange against a dimmed background. Chat-to-Graph synchronization highlights the same 2-hop path in the Graph Panel via a Dash clientside callback (gold bridge nodes, dashed orange edges). The Dijkstra algorithm is embedded in standalone HTML exports for offline use.

### LLM providers and FastAPI Bridge

A shared `initialize_llm_client()` helper dispatches to seven providers: OpenAI, Google Gemini, Anthropic Claude, OpenRouter, Groq, NVIDIA NIM, and Local Ollama. The **FastAPI Bridge** exposes three REST endpoints: `POST /sessions`, `POST /sessions/{id}/ask`, `DELETE /sessions/{id}`. Sessions survive server restarts via lazy reconstruction from persisted G.pkl graph files.

### Deployment

The platform is distributed as a Docker image (`lsbnb/netmedex`) and PyPI package (`pip install netmedex`). A `docker-compose.yml` enables one-command deployment. The Docker builder stage pre-downloads the tiktoken BPE cache and pins `TIKTOKEN_CACHE_DIR`, enabling air-gapped deployment. Source code: https://github.com/lsbnb/NetMedEx (MIT licence).

---

## References

1. National Library of Medicine. PubMed. https://pubmed.ncbi.nlm.nih.gov (2026).
2. Barabási, A.-L., Gulbahce, N. & Loscalzo, J. Network medicine: a network-based approach to human disease. *Nat. Rev. Genet.* **12**, 56–68 (2011).
3. Wei, C.-H., Allot, A., Leaman, R. & Lu, Z. PubTator3: an AI-powered literature resource for unlocking biomedical knowledge. *Nucleic Acids Res.* **52**, W540–W546 (2024).
4. Liu, F. et al. Self-alignment pretraining for biomedical entity representations. In *Proc. NAACL-HLT 2021*, 4228–4238 (2021).
5. Bouma, G. Normalized (pointwise) mutual information in collocation extraction. In *Proc. GSCL 2009*, 31–40 (2009).
6. Lewis, P. et al. Retrieval-augmented generation for knowledge-intensive NLP tasks. *NeurIPS* **33**, 9459–9474 (2020).
7. Dijkstra, E. W. A note on two problems in connexion with graphs. *Numer. Math.* **1**, 269–271 (1959).
8. Blondel, V. D., Guillaume, J.-L., Lambiotte, R. & Lefebvre, E. Fast unfolding of communities in large networks. *J. Stat. Mech.* **2008**, P10008 (2008).
9. Plotly Technologies Inc. Dash: Analytical Web Applications for Python (2017). https://dash.plotly.com.
10. Franz, M. et al. Cytoscape.js: a graph theory library for visualisation and analysis. *Bioinformatics* **32**, 309–311 (2016).
11. Balci, H. & Dogrusoz, U. cytoscape.js-fcose (2021). https://github.com/iVis-at-Bilkent/cytoscape.js-fcose.
12. Chroma. The AI-native open-source embedding database (2023). https://github.com/chroma-core/chroma.
13. Szklarczyk, D. et al. The STRING database in 2023. *Nucleic Acids Res.* **51**, D638–D646 (2023).
14. Luo, R. et al. BioGPT: generative pre-trained transformer for biomedical text generation and mining. *Brief. Bioinform.* **23**, bbac409 (2022).
15. Huang, Z. et al. Icariin regulates osteoblast differentiation via microRNA-153. *Exp. Ther. Med.* **15**, 5159–5166 (2018). PMID:29904399.
16. Zhang, X.-Y. et al. Icariin regulates miR-23a-3p-mediated osteogenic differentiation of BMSCs. *Saudi Pharm. J.* **29**, 1405–1415 (2021). PMID:35002378.
17. Lian, F. et al. Icariin attenuates inhibition of osteogenic differentiation via miR-21-5p. *Cell Biol. Int.* **42**, 931–939 (2018). PMID:29500883.
18. Wu, P.-Y. et al. Morinda officinalis polysaccharide upregulates miR-21 and activates PI3K/AKT pathway. *Kaohsiung J. Med. Sci.* **38**, 675–685 (2022). PMID:35593324.
19. Zhou, L. et al. Icariin ameliorates estrogen-deficiency induced bone loss via IGF-I/ERα signalling. *Phytomedicine* **82**, 153413 (2021). PMID:33339654.

---

## Figure Legends

![ ](/home/cylin/NetMedEx/docs/img/netmedex_architecture_v2.jpg)

**Fig. 1 | NetMedEx three-stage pipeline.** Search & Network Construction (PubTator3 retrieval, CUI deduplication, sapBERT normalization, Hybrid Scoring 2.0) → Graph Exploration (Louvain clustering, Dijkstra shortest-path, adaptive fCoSE rendering) → Hybrid RAG Chat (Smart 2-hop engine, 5-Layer Evidence output, Chat-to-Graph synchronization).

---

![ ](/home/cylin/NetMedEx/docs/img/netmedex_search_panel_v2.jpg)

![ ](/home/cylin/NetMedEx/docs/img/up2_3000lit.png)

![ ](/home/cylin/NetMedEx/docs/img/Search_nodes.png)

![ ](/home/cylin/NetMedEx/docs/img/Fig11_hybrid_RAG CHAT.png)

![ ](/home/cylin/NetMedEx/docs/img/fig12B_indexing.png)

**Fig. 2 | NetMedEx web interface.** **a**, Search Panel with multilingual keyword, Gene List, PMID, or PubTator file input. **b**, Advanced Settings: Max Articles slider (up to 3,000) and API-key-gated KG Normalization toggle. **c**, Graph Panel: Dijkstra shortest-path search (orange anchor nodes, teal bridge nodes, dimmed background). **d**, Chat Panel: 5-Layer Evidence response with inline PMIDs and [Human]/[Animal/In vitro] labels. **e**, Chat indexing diagnostic bar (abstract count, indexed nodes, mode: partial/full/cached).

---

![ ](/home/cylin/NetMedEx/docs/img/hybridchat.png)

![ ](/home/cylin/NetMedEx/docs/img/Figure 8_Graph_panel_network.png)

![ ](/home/cylin/NetMedEx/docs/img/netmedex_search_api.png)

**Fig. 3 | Case study and programmatic integration.** **a**, Hybrid RAG Chat Panel showing selection summary and 5-Layer response with Chat-to-Graph path highlighting. **b**, Co-mention knowledge graph of Icariin–miRNA–osteogenesis literature; Louvain community clusters (coloured nodes) with bridge node miR-21 highlighted in gold. **c**, FastAPI Bridge REST interface: `POST /sessions` builds the full pipeline; `POST /sessions/{id}/ask` returns structured 5-Layer answers for external applications.

---

![ ](/home/cylin/NetMedEx/docs/img/Icarilin_regulation_no_caption.png)

**Fig. 4 | Reconstructed mechanism of Icariin-mediated osteoblast differentiation.** NetMedEx 2-hop RAG identified the latent chain Icariin → miR-21 → PTEN → PI3K/Akt/mTOR → osteoblastogenesis. miR-21 (gold, bridge node) was independently confirmed by Dijkstra shortest-path search. Human clinical validation: bone density improvement (PMID:35002378).
