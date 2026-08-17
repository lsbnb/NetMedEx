# NetMedEx path-positive-20-v1 protocol

This is a **conditional KG efficacy benchmark**, not a representative estimate of overall
NetMedEx performance. Its question is: *when a current claim-safe Tier-A path exists before
answer generation, does KG reranking or path-grounded answering improve over Traditional RAG?*

Selection is frozen without reading generated answers, judge ratings, or qrels. Every retained
path must have `gate_tier=A`, `claim_safe=true`, and every edge must contain a relation-aligned
quote with confidence >= 0.8. The frozen set contains 5 direct, 2 same-PMID multi-hop, and 13
cross-PMID multi-hop items.

Arms share the same frozen corpus and answer model (`gpt-oss:120b`): A is closed-book; B is text
RAG; C is text RAG plus Tier-A PMID reranking without graph context; D adds bounded KG expansion
and claim-safe path context. The primary contrasts are C-B and D-B, paired by question. Results
from the original all-question pilot remain the intention-to-treat evidence.

Three blinded AI judges are used (GPT-4.1, Claude Sonnet 4.6, and local gpt-oss 120B). They are
AI proxies, not human biomedical experts. Because gpt-oss is also the answer model, a sensitivity
analysis using only the two external judges must be reported. Bootstrap resampling uses questions,
not individual ratings, as the independent unit.
