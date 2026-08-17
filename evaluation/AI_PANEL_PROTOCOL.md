# NetMedEx Multi-model AI Panel Protocol

This protocol replaces full human blind review with a provider-diverse, blinded AI panel. Results
must be described as **multi-model AI-adjudicated**, never human expert-validated.

## Frozen inputs

Build the answer worksheet and enrich the existing frozen-edge worksheet before rating:

```bash
python evaluation/build_answer_worksheet.py
python evaluation/enrich_edge_worksheet.py
python evaluation/freeze_ai_panel.py
```

The `answer_ratings_key.csv` and `hypothesis_ratings_key.csv` files are private blinding keys. Do
not include them in any judge prompt. `panel_freeze_v1.json` records all input checksums.

## Independent judges

Run each provider into a separate output and checkpoint directory. Example for the answer task:

```bash
python evaluation/rate_ai_panel.py --task answer \
  --input evaluation/formal/answer_ratings_worksheet.csv \
  --output evaluation/formal/ai_panel/answer_ratings_openai.csv \
  --provider openai

python evaluation/rate_ai_panel.py --task answer \
  --input evaluation/formal/answer_ratings_worksheet.csv \
  --output evaluation/formal/ai_panel/answer_ratings_gemini.csv \
  --provider google

python evaluation/rate_ai_panel.py --task answer \
  --input evaluation/formal/answer_ratings_worksheet.csv \
  --output evaluation/formal/ai_panel/answer_ratings_claude.csv \
  --provider anthropic
```

When Gemini is unavailable, an OpenAI-compatible on-premises biomedical model may replace the
Google judge explicitly (never label its output as Gemini):

```bash
python evaluation/rate_ai_panel.py --task answer \
  --input evaluation/formal/answer_ratings_worksheet.csv \
  --output evaluation/formal/ai_panel/answer_ratings_medgemma.csv \
  --provider local --model gpt-oss:120b
```

The local endpoint is read from `LOCAL_LLM_BASE_URL` and the optional key from
`LOCAL_LLM_API_KEY`. Record the judge as `local/gpt-oss:120b`. A local replacement reduces
provider diversity and is not methodologically identical to a Gemini panel, so report that
substitution in the manifest and limitations.

Use the same pattern with `--task hypothesis` and `--task edge`. Edge rating must use
`edge_ratings_worksheet_enriched.csv`; it includes supporting abstracts rather than titles alone.
Every batch is checkpointed and safe to resume.

Before any full run, use `--dry-run` to print the exact prompt-character count and a rough input
token estimate. Edge adjudication should default to cross-judge disagreements rather than all
edges:

```bash
python evaluation/select_ai_panel_items.py \
  --left evaluation/formal/edge_ratings_worksheet_gemini.csv \
  --right evaluation/formal/edge_ratings_worksheet_openai.csv \
  --id-field edge_id --field biologically_meaningful --field relation_type_correct \
  --per-question 2 \
  --output evaluation/formal/ai_panel/edge_disagreement_calibration_ids.txt

python evaluation/rate_ai_panel.py --task edge \
  --input evaluation/formal/edge_ratings_worksheet_enriched.csv \
  --output evaluation/formal/ai_panel/edge_ratings_third_judge.csv \
  --provider openai --model gpt-4.1 \
  --item-file evaluation/formal/ai_panel/edge_disagreement_calibration_ids.txt \
  --dry-run
```

Do not launch the full answer panel solely because credentials are available. First estimate each
provider's input size, set an explicit item cap, and expand only when the calibration changes a
decision-relevant conclusion.

## Aggregation

```bash
python evaluation/aggregate_ai_panel.py --task answer \
  --rating openai=evaluation/formal/ai_panel/answer_ratings_openai.csv \
  --rating gemini=evaluation/formal/ai_panel/answer_ratings_gemini.csv \
  --rating claude=evaluation/formal/ai_panel/answer_ratings_claude.csv \
  --key evaluation/formal/answer_ratings_key.csv \
  --output-long evaluation/formal/ai_panel/answer_ratings_long.csv \
  --output-consensus evaluation/formal/ai_panel/answer_ratings_consensus.csv \
  --output-summary evaluation/formal/ai_panel/answer_panel_summary.json
```

The summary reports provider-blind paired system differences, question-level bootstrap confidence
intervals, sign tests, Fleiss' kappa (three or more judges), Krippendorff's alpha, and question-level
pairwise preference consensus.

## Claim boundary

Superiority requires a predeclared primary outcome whose paired 95% confidence interval excludes
zero, plus non-inferiority on direct-evidence/retrieval questions. A positive point estimate alone
is a trend, not superiority. Provider/model IDs, prompts, checkpoints, freeze manifest, raw response
hashes, and all disagreement decisions must remain available for audit.

## Adaptive retrieval profile

`run_formal_50.py --hybrid-profile F_adaptive` uses frozen `question_type` metadata rather than an
additional LLM call. Direct-evidence/retrieval questions use text-only retrieval, association and
cross-species questions use 1-hop graph retrieval, and mechanism/hypothesis/2-hop questions use
the evidence-gated 2-hop profile. Evidence-gated paths require every hop to carry a stored semantic
extraction quote. Path ranking uses the mean of the nested per-PMID/per-relation extraction
confidences; it must not silently fall back to 0.5 when those nested scores are present.
