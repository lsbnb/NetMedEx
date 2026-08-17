# Manuscript Results Draft

## Quantitative Pilot Evaluation

We established a structured quantitative evaluation framework to assess NetMedEx Hybrid RAG
across retrieval quality, answer grounding, hallucination control, semantic relationship quality,
use efficiency, hypothesis value, system performance, and user acceptance. The formal benchmark
workspace contains 50 biomedical questions spanning direct evidence retrieval,
mechanistic synthesis, 2-hop path discovery, cross-species interpretation, multilingual querying,
and negative-control style stress tests. The formal-v1 retrieval benchmark contains 384 PMID
relevance judgments across all 50 questions. These judgments were internally adjudicated through
three AI-assisted review passes against PubMed records and abstracts and frozen with a row-level
audit trail. They should not be described as human expert-reviewed unless an independent expert
sign-off is subsequently completed.

In the curated pilot seed set, NetMedEx Hybrid RAG achieved higher retrieval quality than both
traditional RAG and a general LLM baseline. NetMedEx reached a Precision@5 of 0.76, Recall@10
of 0.6443, and nDCG@10 of 0.7996, compared with 0.36, 0.3124, and 0.4542 for traditional RAG,
and 0.20, 0.1791, and 0.3024 for the general LLM baseline. These preliminary results were
recalculated after final Q001-Q010 relevance adjudication and suggest
that graph-guided retrieval and evidence-aware ranking improve the prioritization of relevant
biomedical literature, especially when the task requires mechanistic or pathway-level synthesis.

Claim-level seed annotation further suggested strong evidence grounding for NetMedEx. Among
the curated NetMedEx claims, the direct citation support rate was 0.9231, and no unsupported
claims were observed in this seed set. In contrast, the general LLM baseline showed a high
unsupported-claim rate in the same annotation workflow. These results should be interpreted as
workflow-validating pilot evidence rather than final benchmark performance, because the seed
answers were curated, the relevance labels were AI-adjudicated, and the outputs were not yet
generated from frozen system versions under blinded evaluation conditions.

The fixed-version 50-question system run is now complete, with 50 nonblank answers in each of the
three comparison arms. Under the strict frozen qrels, NetMedEx and Traditional RAG both reached
Precision@5 of 0.1040; Recall@10 was 0.0786 versus 0.0863, and nDCG@10 was 0.1019 versus 0.1025.
Paired bootstrap confidence intervals included zero for all three differences. Because 92.3% and
91.7% of the respective top-10 outputs were unjudged, these values are lower-bound estimates from
an incomplete relevance pool and do not support a retrieval-superiority claim.

The next formal evaluation step is to blind-rate the pooled union of retrieved PMIDs, freeze the
expanded qrels, and then repeat retrieval scoring. Blinded human ratings also remain necessary for
answer correctness, claim support, relationship quality, and hypothesis value. Final reporting
will keep the curated pilot, strict formal retrieval results, preliminary AI-panel ratings, and
human-reviewed endpoints separate.
