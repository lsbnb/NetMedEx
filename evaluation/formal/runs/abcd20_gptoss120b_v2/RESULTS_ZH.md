# NetMedEx A/B/C/D 20 題 pilot 結果

執行日期：2026-08-13（Asia/Taipei）

## 結論

本次 pilot 證明 Text RAG（B）優於 closed-book LLM（A），但沒有證明加入 KG 的 C 或 D
優於 B。C 與 B 幾乎等效；D 在 path-enabled 題目反而較差，主要原因是 graph section
壓縮了原本答案的完整性與可讀性，而非 citation grounding 下降。

本結果是 20 題、三位 AI judge 的 pilot，不可表述為人類生醫專家驗證或正式臨床證據。

## 實驗設計與完整性

- A：closed-book gpt-oss:120b
- B：traditional text RAG
- C：text RAG + KG reranking；不向生成模型顯示 path context
- D：KG expansion + reranking + Tier-A path-grounded answer
- 20 題 × 4 arms = 80 份完整答案；四臂均 20/20、0 failed
- 三位匿名 judge：GPT-4.1、Claude Sonnet 4.6、gpt-oss:120b
- 80 答案 × 3 judges = 240 ratings
- Gemini API 未使用
- edge Tier A：aligned quote + confidence >= 0.8；Tier B 只供 retrieval expansion
- 13/20 題由 deterministic router 啟動 KG；其餘 7 題 text-only
- graph 由 GPT-4.1 一次性預建；A/B 不載入 graph，C/D 重用同一批 graph
- repair 僅處理被 completion cap 截斷的答案；不改 retrieval、graph 或 arm treatment

## AI judge 分數

六項指標均為 1–5 分；下表是每題先跨三位 judge 平均，再跨 20 題平均。

| Arm | Overall | Correct | Complete | Relevant | Grounded | Mechanistic | Research |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 4.214 | 4.183 | 4.500 | 4.867 | 3.100 | 4.467 | 4.167 |
| B | **4.592** | 4.600 | 4.333 | 4.950 | 4.450 | **4.717** | **4.500** |
| C | 4.575 | **4.633** | 4.333 | 4.950 | 4.450 | 4.667 | 4.417 |
| D | 4.475 | 4.533 | 4.167 | 4.883 | 4.450 | 4.567 | 4.250 |

配對比較：

- B − A = +0.378；95% bootstrap CI +0.194 至 +0.575；sign-test p=0.0309。
- C − B = −0.017；95% CI −0.075 至 +0.042；p=0.8145。
- D − B = −0.117；95% CI −0.258 至 +0.011；p=0.3323。
- 在 5 題 Tier-A path-enabled subset，D − B = −0.456；95% CI −0.778 至 −0.178；
  D 為 0 wins / 5 losses。此 subset 很小，仍應視為 pilot signal。

Judge question-level preference consensus：C 4 題、B 3 題、D 1 題、A 1 題、tie/無共識 11 題。
三 judge 一致性偏低：六項 ordinal Krippendorff alpha 約 0.11–0.36，因此應重視配對分數、
逐題理由與後續人類評審，不應只引用 winner count。

## Path 與 expansion

- 任一 Tier-A path coverage：5/13 KG-routed 題（38.5%）
- multi-hop Tier-A coverage：4/13（30.8%）
- cross-PMID Tier-A coverage：2/13（15.4%）
- 有 path 的題目：Q001、Q004、Q008、Q011、Q037
- C/D 實際 rerank boost：5 題、8 個 PMID
- D expansion 實際觸發：Q008、Q029、Q037
- 每題新增 15 PMID；bounded merge 各接受 2 篇，共 6 篇進入 top-10 treatment
- 這 6 篇新增文獻目前全部是 qrels-unjudged，不能據現有 qrels 判定真陽性或假陽性
- D 最終輸出 graph claims：Q001、Q004、Q008、Q037；deterministic verifier 為 7/7
  supported、0 unsupported。這只證明 path/PMID/方向與 frozen evidence 結構一致，不等同生醫專家
  判定機制為真。

Path coverage 沒達到原訂至少 60%。將 corpus 從 top-15 擴到 top-50 的 probe（Q004、Q011）
仍未新增嚴格跨 PMID path，因此瓶頸主要是可組合 evidence 與 entity/relation schema，而非單純文獻數量。

## Retrieval 結果與限制

| Arm | P@5 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|
| B | 0.190 | 0.182 | **0.227** |
| C | 0.190 | 0.182 | 0.211 |
| D | 0.190 | 0.175 | 0.206 |

Top-10 中平均 86% 文獻未被 qrels 判定，因此這組 retrieval metric 有嚴重 incomplete-judgment bias。
D 新加入的 6 篇均未判定，數值下降不能直接解讀為 expansion 無效；應先 pool/adjudicate 後再重算。

## 延遲與 tokens

以下是 cached/prebuilt KG 部署情境；不含一次性 GPT-4.1 graph build。

| Arm | Median sec/question | Total sec/20 | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| A | 27.32 | 568.42 | 3,283 | 21,540 |
| B | 35.37 | 700.71 | 65,522 | 24,320 |
| C | 40.19 | 768.16 | 66,202 | 23,642 |
| D | 41.70 | 828.72 | 69,119 | 25,521 |

C 比 B 的 median latency 增加 4.82 秒（13.6%）；D 增加 6.33 秒（17.9%）。本地模型 API
帳單成本為 $0，但 GPU、電力與折舊未計。

## 外部 API 成本

按 2026-08-13 公開 list price 估算：GPT-4.1 input/output $2/$8 per MTok；Claude Sonnet 4.6
$3/$15 per MTok。未計稅、企業折扣或網路成本。
價格來源：[OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)、
[Anthropic Claude Sonnet 4.6](https://www.anthropic.com/claude/sonnet)。

| 用途 | Model | Input | Output | 估算 USD |
|---|---|---:|---:|---:|
| 13 題正式 graph prebuild | GPT-4.1 | 176,161 | 202,371 | $1.9713 |
| 第一位 judge | GPT-4.1 | 62,815 | 9,982 | $0.2055 |
| 第二位 judge | Claude Sonnet 4.6 | 76,579 | 12,464 | $0.4167 |
| 答案生成 + 第三位 judge | local gpt-oss:120b | — | — | $0 API |
| **正式 pipeline 合計** |  |  |  | **$2.5935** |

另有 top-50 domain-KG probe（非正式四臂結果）使用 GPT-4.1 157,450 input + 168,890 output，
約 $1.6660。連同探索 probe，本次實際外部 API 估算共 $4.2595。

## 為何 KG 沒有提升整體表現

1. 只有 5/13 KG-routed 題有 Tier-A path；15/20 題 C 實際上沒有可用 rerank evidence。
2. C 的 8 個 PMID boost 沒有帶來可量測的內容增益，且某些 qrels-relevant 文獻排序反而下降。
3. D 的 path section 佔用有限 answer budget，使 Q004/Q011/Q037 少了傳統 RAG 已能整理出的機制細節。
4. 一篇文獻內的 direct Tier-A edge 可提高可追溯性，但不是 cross-document discovery。
5. Tier-B expansion 找到的新文獻目前沒有 qrels，系統可能找到新證據，但 benchmark 看不見它。
6. PATH notation 對 judge/讀者不夠自然；Q008/Q037 評語明確指出 graph 區塊較難讀或突兀。
7. qrels coverage 太低、AI judge agreement 偏低，使小幅提升很難被可靠偵測。

## 建議優先順序

1. 以 C 作 deployment baseline：保留 router + cached KG + conservative reranking，但目前只能宣稱
   non-inferior pilot signal，不能宣稱優於 B。
2. D 改成最多補一條 verifier-passed、cross-PMID、<=2-hop path；用自然語言插入既有段落，避免獨立
   graph section 與 PATH jargon。
3. 對 expansion 接受的 6 篇 PMID 做 blinded human/AI adjudication，擴充 pooled qrels 後重算
   Recall@10/nDCG@10。
4. 將 path target 拆成 overall、multi-hop、cross-PMID；主要 academic claim 只使用 cross-PMID 指標。
5. 改善 entity normalization、direction、negation、species、study context，並優先建立真正可組合的
   domain KG，而非只增加同一主題的文獻數量。
6. 下一輪增加人工生醫評審；三 AI judge 僅可稱 AI panel，不能假裝人類專家。

## 可重現 artifacts

- `analysis.json`：完整分數、配對 CI、strata、retrieval、latency/tokens
- `judge_summary.json`：judge reliability 與 preference consensus
- `judge_ratings_long.csv`、`judge_consensus.csv`：逐列評分
- `blinded_answer_worksheet.csv`、`blinded_answer_key.csv`：匿名題本與 private key
- `arm_A` 至 `arm_D`：每題 corpus、ranking、path、expansion、answer 與 manifest
