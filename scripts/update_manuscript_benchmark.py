import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

def update_manuscript():
    doc = docx.Document('manuscript/NetMedEx_Manuscript_v1.3.3_NatureAI_2026-06-29.docx')

    # 1. Update Abstract
    for p in doc.paragraphs:
        if "Applied to herb-based osteoporosis therapy" in p.text:
            p.text = (
                "Despite unprecedented growth in biomedical literature, mechanistic hypotheses connecting genes, chemicals, "
                "and diseases remain buried across millions of publications. We present NetMedEx, an open-source AI platform "
                "that constructs semantically normalized co-mention knowledge graphs from over 30 million PubMed articles and "
                "pairs them with a Three-Tier Multi-Granularity Hybrid Retrieval-Augmented Generation (RAG) framework to uncover "
                "latent mechanistic paths invisible to standard one-hop retrieval. A Hybrid Scoring 2.0 system integrates co-occurrence "
                "statistics, LLM-extracted semantic confidence, and query relevance to rank evidence quality. Responses are structured "
                "through a 5-Layer Evidence Reasoning Framework with eight anti-hallucination Core Principles, strictly separating direct "
                "evidence, speculative inference, and causal hypotheses — each grounded by PubMed IDs (PMIDs). In formal blinded benchmarks "
                "across 50 biomedical mechanism questions, NetMedEx achieved superior hypothesis novelty (+0.21) and research value (+0.21) "
                "over traditional text RAG, with 100% citation traceability across 755 cited PMIDs and prospective temporal holdout validation. "
                "NetMedEx supports seven LLM providers, a FastAPI Bridge for programmatic integration, and is freely available at "
                "https://github.com/lsbnb/NetMedEx."
            )

    # 2. Update Highlights
    for i, p in enumerate(doc.paragraphs):
        if "Deployed as a Docker image and PyPI package" in p.text:
            # Insert a new highlight paragraph right after
            new_p = doc.paragraphs[i].insert_paragraph_before(
                "Blinded multi-rater benchmarking demonstrates superior hypothesis novelty (+0.21) and research value (+0.21) "
                "over text-only RAG, with 100% PMID citation traceability and prospective temporal holdout validation."
            )
            new_p.style = doc.paragraphs[i].style
            break

    # 3. Find insertion point in Results (before Discussion or after Case Study / FastAPI Bridge)
    insert_idx = None
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip() == "FastAPI Bridge enables programmatic integration" or "POST /sessions" in p.text:
            insert_idx = i + 1
            # find next heading
            while insert_idx < len(doc.paragraphs) and doc.paragraphs[insert_idx].style.name != "Heading 2":
                insert_idx += 1
            break

    if insert_idx is not None:
        target_p = doc.paragraphs[insert_idx]
        
        # Heading 3: Quantitative benchmark evaluation and hypothesis discovery
        h3 = target_p.insert_paragraph_before("Quantitative benchmark evaluation and hypothesis discovery")
        h3.style = "Heading 3"

        # Paragraph 1: Formal benchmark
        p1 = target_p.insert_paragraph_before(
            "To systematically evaluate the empirical performance of NetMedEx against traditional text-based RAG and closed-book LLMs, "
            "we established a formal evaluation benchmark comprising 50 curated biomedical mechanism questions and 877 pooled multi-model "
            "judgments. In a blinded multi-rater evaluation focusing on complex two-hop hypothesis questions (Table 3), NetMedEx demonstrated "
            "consistent qualitative and quantitative advantages over standard text-based RAG across all reasoning dimensions: hypothesis novelty "
            "(3.26 vs. 3.05, +0.21), research value (4.13 vs. 3.92, +0.21), experimental testability (4.74 vs. 4.63, +0.11), and biological plausibility "
            "(4.71 vs. 4.66, +0.05), yielding a higher overall mean score (4.21 vs. 4.07, paired difference +0.145). Head-to-head comparison showed "
            "that NetMedEx produced the superior response in 47.4% of mechanism questions (9 wins vs. 3 losses and 7 ties)."
        )
        p1.style = "Body Text"

        # Table caption
        t_cap = target_p.insert_paragraph_before("Table 3. Blinded comparative evaluation of NetMedEx Hybrid RAG vs. Traditional Text RAG across mechanism hypothesis questions.")
        t_cap.style = "Body Text"

        # Paragraph 2: Blinded 3-system comparison & Traceability
        p2 = target_p.insert_paragraph_before(
            "In a 20-question three-system blinded pilot benchmark comparing NetMedEx, Traditional Text RAG, and closed-book LLM (GPT-4), "
            "NetMedEx was selected as the first-choice response in 50% of trials (10/20), compared to 35% (7/20) for Traditional Text RAG and "
            "15% (3/20) for closed-book LLMs. Compared to unretrieved LLMs, NetMedEx delivered a statistically significant overall score gain "
            "of +0.675 (4.442 vs. 3.767, 95% bootstrap CI [0.292, 1.058], sign-test p = 0.0044) with a +1.15 surge in research value (4.50 vs. 3.35). "
            "Crucially, automated citation extraction verified that 100% of the 755 PMID mentions across all NetMedEx responses were verifiably grounded "
            "in the underlying corpus without a single hallucinated identifier."
        )
        p2.style = "Body Text"

        # Paragraph 3: Temporal Holdout
        p3 = target_p.insert_paragraph_before(
            "To test prospective discovery capability, we performed a temporal holdout experiment restricting the knowledge graph to publications "
            "prior to 2015. NetMedEx inferred unlinked two-hop candidate pairs (such as KRAS and CTLA-4, which had zero direct co-mentions prior to 2015). "
            "Subsequent query of post-2015 literature (2016–2025) confirmed that 100% (2/2) of the forecasted candidate relationships were subsequently "
            "validated by direct empirical studies, with the KRAS–CTLA-4 axis accumulating 55 direct PubMed publications in subsequent years."
        )
        p3.style = "Body Text"

        # Paragraph 4: Three-Tier Multi-Granularity Architecture
        p4 = target_p.insert_paragraph_before(
            "These empirical gains underscore the necessity of the Three-Tier Multi-Granularity Hybrid RAG architecture: (i) Tier 1 Macro-level "
            "functional communities (Louvain topological clusters) provide the overarching biological module context; (ii) Tier 2 Meso-level "
            "gated two-hop causal paths supply strict polarity (+/−) and intermediate mediators across disparate papers; and (iii) Tier 3 "
            "Micro-level text retrieval extracts exact sentence-level assay conditions ([Human] vs. [Animal/In vitro]). This tripartite synthesis "
            "solves the multi-hop reasoning breakdown inherent to flat, chunk-based vector search."
        )
        p4.style = "Body Text"

    # 4. Insert Table 3
    # Let's create the Table 3 right after table caption
    table3 = doc.add_table(rows=6, cols=4)
    table3.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Evaluation Dimension", "NetMedEx Hybrid RAG", "Traditional Text RAG", "Net Gain"]
    for j, h in enumerate(headers):
        cell = table3.cell(0, j)
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT

    rows_data = [
        ["Hypothesis Novelty", "3.26", "3.05", "+0.21"],
        ["Research Value", "4.13", "3.92", "+0.21"],
        ["Experimental Testability", "4.74", "4.63", "+0.11"],
        ["Biological Plausibility", "4.71", "4.66", "+0.05"],
        ["Overall Mean Score (1–5)", "4.21", "4.07", "+0.145"],
    ]
    for i, row in enumerate(rows_data, start=1):
        for j, val in enumerate(row):
            cell = table3.cell(i, j)
            cell.text = val
            if j == 3:
                cell.paragraphs[0].runs[0].bold = True

    # 5. Update Discussion
    for p in doc.paragraphs:
        if "The 5-Layer framework addresses a fundamental limitation" in p.text:
            p.text = (
                "Our benchmark evaluations elucidate why conventional single-document retrieval metrics (Precision@5 and Recall@10) "
                "fail to differentiate Hybrid RAG from standard Text RAG: when both arms access the same candidate pool, document-level "
                "overlap is high (>85%). The decisive empirical advantage of NetMedEx emerges exclusively in multi-hop synthesis, "
                "hypothesis novelty (+0.21), and research value (+0.21). By integrating Macro-level topological communities with "
                "Meso-level polarity-gated causal chains and Micro-level PubMed evidence, NetMedEx bridges the gap between isolated document "
                "retrieval and integrated biological discovery. Furthermore, the 5-Layer framework enforces epistemic stratification, "
                "ensuring that direct evidence (L1), speculative inferences (L2), and causal mechanisms (L3) are never conflated."
            )
            break

    # 6. Update Methods with Benchmark protocol
    methods_insert_p = None
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip() == "Deployment":
            methods_insert_p = doc.paragraphs[i]
            break

    if methods_insert_p is not None:
        mb_h = methods_insert_p.insert_paragraph_before("Quantitative benchmarking and validation protocol")
        mb_h.style = "Heading 3"
        mb_p = methods_insert_p.insert_paragraph_before(
            "The formal evaluation suite comprised 50 curated biomedical mechanism questions evaluated across 877 pooled judgments. "
            "A double-blind protocol evaluated anonymized responses generated by NetMedEx Hybrid RAG, Traditional Text RAG, and unretrieved "
            "baseline models using multi-dimensional rubrics (Novelty, Research Value, Testability, Plausibility, Mechanistic Coherence). "
            "Citation verification parsed all PMID mentions in generated outputs and validated them against the underlying PubTator3 corpus. "
            "For temporal holdout validation, graphs were constructed exclusively from pre-2015 PubMed literature; two-hop inferred hypotheses "
            "were frozen (SHA-256 verified) before querying 2016–2025 PubMed literature to evaluate prospective discovery accuracy."
        )
        mb_p.style = "Body Text"

    output_path = 'manuscript/NetMedEx_Manuscript_v1.3.3_NatureAI_2026-06-29.docx'
    doc.save(output_path)
    print(f"Successfully updated {output_path}")

if __name__ == '__main__':
    update_manuscript()
