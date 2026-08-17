# Hybrid RAG 增量效益實驗（query-aligned v3）

## 核心假設

Graph RAG 只有在提供跨文獻、可驗證、且 Traditional RAG top-k 尚未涵蓋的機制證據時，
才應改變檢索排序或答案。不得以放寬 Tier-A claim-safety gate 的方式提高 coverage。

每條安全 path 的選擇分數為：

`mechanism utility = 0.55 × query/path relevance + 0.45 × incremental mechanism value`

incremental mechanism value 由下列預先固定特徵組成：outside-top-k PMID、bridge novelty、
cross-document support、bounded multi-hop。所有 path 均在讀取答案分數前分類。

Path 必須完整覆蓋問題端點與題目明示的 bridge；一般安全但 bridge 不完整的 path 不得進入
D2、D3 或 Oracle 候選。D1 刻意保留所有 Tier-A safe paths，作為「多放 path」的對照。

## 三段式介入

| 證據狀態 | 部署行為 |
|---|---|
| 無 Tier-A path | Traditional RAG fallback |
| 只有 confirmatory Tier-A path | Text RAG；記錄可驗證 PMID，但不注入 graph claim |
| 至少一條 incremental Tier-A path | Full Hybrid RAG |

每題的決策、理由、path 數量與 validation PMID 都寫入
`result.json:evidence_exposure.integration_decision`。

## 預先固定實驗臂

| Arm | Treatment |
|---|---|
| B | Traditional RAG |
| C1 | relevance + incremental-utility KG reranking；無 expansion、無 path answer |
| C2 | bounded KG expansion；無 KG reranking、無 path answer |
| D1 | C1 + C2 + 所有 Tier-A safe paths（安全上限十條） |
| D2 | C1 + C2 + 最多兩條 incremental paths |
| D3 | D2，但以完整 Text-RAG 篇幅加上 deterministic natural-language evidence 句，不顯示 PATH／箭頭 notation |
| Oracle | 地端模型只能從既有、query-aligned 的 Tier-A paths 選最多兩條；不能建立或修改 path |

所有臂共用 frozen questions、corpora、graph exposure、top-k、答案模型與 token budget。
Oracle 與答案生成都使用 `provider=local`；Oracle 原始選擇回應保留於 result audit。
答案生成必須以 `finish_reason=stop` 結束；若為 `length` 會提高 token 上限重試，仍截斷則該題失敗。

## 執行

```bash
python evaluation/run_hybrid_gain_ablation.py \
  --queries evaluation/formal/path_positive_20_v1/queries.csv \
  --questions-metadata evaluation/formal/path_positive_20_v1/questions.csv \
  --reuse-corpora-dir <FROZEN_CORPORA_QUESTIONS_DIR> \
  --reuse-exposures-dir <FROZEN_GRAPH_EXPOSURES_QUESTIONS_DIR> \
  --output-dir evaluation/formal/runs/hybrid_gain_v3_untruncated \
  --expected-question-count 20 \
  --answer-max-tokens 2400
```

先加上 `--dry-run` 檢查完整命令。正式 superiority study 應另以 80–120 個獨立
endpoint clusters 執行；20 題 path-positive cohort 僅作開發與 effect-size calibration。

## 地端模型盲評

先將七臂匿名化；private key 不提供給評分模型：

```bash
python evaluation/build_answer_worksheet.py \
  --questions evaluation/formal/path_positive_20_v1/questions.csv \
  --system-outputs evaluation/formal/runs/hybrid_gain_v3_untruncated/hybrid_gain_system_outputs.csv \
  --worksheet evaluation/formal/runs/hybrid_gain_v3_untruncated/blinded_answers_pass1.csv \
  --key evaluation/formal/runs/hybrid_gain_v3_untruncated/blinded_answer_key_pass1.csv \
  --system B_traditional_rag \
  --system C1_kg_reranking \
  --system C2_kg_expansion \
  --system D1_all_safe_paths \
  --system D2_incremental_paths \
  --system D3_incremental_natural_fusion \
  --system Oracle_local_path_selection

python evaluation/rate_ai_panel.py \
  --task answer \
  --input evaluation/formal/runs/hybrid_gain_v3_untruncated/blinded_answers_pass1.csv \
  --output evaluation/formal/runs/hybrid_gain_v3_untruncated/judge_local_pass1.csv \
  --provider local \
  --model gpt-oss:120b
```

至少進行兩次獨立、重新隨機化的地端盲評 pass，並報告 panel/order sensitivity。
若選徑 Oracle 與 judge 使用同一模型，必須明確揭露其非獨立性；較嚴謹的做法是使用不同的
地端模型或模型版本作 judge。

## Primary outcomes

1. D3 − B 的 cluster-level 平均答案分數與 95% CI。
2. D3 − D2：自然語言融合是否改善完整性、相關性與機制連貫性。
3. D2 − D1：incremental-only selection 是否減少冗餘或負效益。
4. C1 − B 與 C2 − B：reranking、expansion 的獨立貢獻。
5. Oracle − D3：自動 path selection 尚可改善的上限。

同時報告 intervention rate、claim-safe/incremental/cross-PMID coverage、expanded PMID 的 pooled
relevance、unsupported claim rate、wins/losses/ties、延遲與 tokens。主要推論單位是獨立
source/endpoint cluster，不把同義改寫題當成獨立樣本。
