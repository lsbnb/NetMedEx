# GPT-5.6 Sol Rater-2 Results

## Completion

- Reviewer type: AI
- Provider/model: OpenAI `gpt-5.6-sol`
- Completed questions: 50/50
- Completed candidate judgments: 877/877
- Validation errors: 0
- Checkpoints: 50
- Blinded from system identity, rank, score, provenance, and prior relevance

## Label distribution

| Relevance | Count |
|---|---:|
| 0 | 64 |
| 1 | 365 |
| 2 | 448 |

| Confidence | Count |
|---|---:|
| 1 | 2 |
| 2 | 36 |
| 3 | 839 |

Among the 64 grade-0 judgments, exclusion reasons were: wrong context (19), too broad (15),
no usable evidence (12), wrong entity (11), off topic (4), wrong study type (2), and duplicate
(1).

## Comparison with AI preliminary rater-1

- Raw agreement: 0.7537
- Cohen's kappa: 0.5443
- Quadratic-weighted kappa: 0.6613
- Agreements automatically carried into adjudication: 661
- Disagreements requiring adjudication: 216
- Severe grade-0 versus grade-2 disagreements: 3
- Questions with no candidate-level disagreement: 2/50

These values describe agreement between two AI rating passes. They are not human inter-rater
reliability and must not be reported as expert validation.

## Comparison with formal-v1 labels

For the 384 candidates already present in formal-v1:

- Raw agreement: 0.7630
- Cohen's kappa: 0.5176
- Quadratic-weighted kappa: 0.5728

For the 493 newly pooled candidates, GPT-5.6 Sol assigned 49 grade-0, 220 grade-1, and 224 grade-2
labels. These new labels demonstrate why treating every previously unjudged document as irrelevant
was not defensible, but they still require adjudication before becoming formal-v2 qrels.

