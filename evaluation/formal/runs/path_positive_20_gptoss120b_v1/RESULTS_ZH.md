# NetMedEx path-positive 20 題 efficacy pilot

## 結論

在預先凍結且實際 20/20 有 claim-safe Tier-A path 的題組中，KG reranking（C）與
Traditional RAG（B）近乎持平；把 path 與 expansion 直接放入答案的完整 Hybrid arm
（D）則顯著較差。因此目前證據**不支持 Hybrid RAG 優於 Traditional RAG**。瓶頸已從
path availability 轉為 path selection、verbalization 與 answer-side evidence gate。

此為刻意富集 path-positive 題目的條件式 efficacy benchmark，不能取代原 20 題 ITT
結果，也不能估計一般查詢的 path coverage。裁判均為 AI proxy，不是人類生醫專家。

## 設計與完整性

- 20 題：5 direct、2 same-PMID multi-hop、13 cross-PMID multi-hop。
- 每條 path 在答案生成前凍結；path Tier A、`claim_safe=true`，且每個 edge 均有
  relation-aligned quote 與 confidence >= 0.8。
- A：closed-book；B：Traditional text RAG；C：B + KG reranking（不給模型 path）；
  D：KG expansion + reranking + path-grounded answer。
- 四臂共用 frozen corpus 與地端 gpt-oss 120B；80/80 答案完成。
- GPT-4.1、Claude Sonnet 4.6、地端 gpt-oss 120B 完成 240/240 盲化評分；另做只含
  GPT-4.1 與 Claude 的外部裁判敏感度分析。

## 三裁判主要結果（1–5）

| Arm | 平均分 | 相對 B | 95% bootstrap CI | Wins/Losses/Ties |
|---|---:|---:|---:|---:|
| A | 4.253 | -0.272 | -0.600–0.011 | 7/13/0 |
| B | 4.525 | reference | — | — |
| C | 4.497 | -0.028 | -0.136–0.086 | 8/11/1 |
| D | 3.653 | -0.872 | -1.167–-0.575 | 3/17/0 |

外部兩裁判結果相同：C-B = -0.021（95% CI -0.117–0.079）；D-B = -0.804
（95% CI -1.063–-0.533）。cross-PMID 題的 D-B 更差：三裁判 -1.162，外部裁判
-1.077。C 沒有證明增益，D 則有一致且明顯的負向效果。

## 結構性與可靠度稽核

- C/D 都是 20/20 Tier-A path-positive。
- KG boost 發生 11/20；C 的 top ranking 實際改變 9/20。
- D 的 ranking 改變 17/20；13/20 題由 expansion 新增文獻，共 173 篇。
- D 的 deterministic claim verifier：18 個帶 PATH claims 中 11 supported、7
  unsupported（38.9%）；另有 5 題完全未引用 PATH。
- 主要失敗為 4-hop path 被現有 2-hop 固定句型截斷、方向或 PMID 遺失，以及 generic
  或不自然 bridge（例如縮寫／低資訊節點）造成答案負擔。
- 裁判一致度有限；三裁判 Krippendorff alpha 依欄位約 0.309–0.615，外部裁判的
  grounding alpha 為 -0.051，故不應過度解讀細微分差。

## 可否在不降低可靠度下增加 paths？

可以。只用目前已存在的 source-local candidates，維持完全相同 gate，並要求起終點
node name 精確相符，20 題可由 20 條增加到 **44 條 unique claim-safe paths**：增加
24 條（+120%），12/20 題有多於一條。這是保守下限，尚未使用 domain-KG union、
同義詞 normalization 或 Tier-B retrieval expansion 後重新抽取。

但 44 條不應全部放進答案。建議把「可搜尋 path pool」與「answer context」分離：

1. 擴大候選 pool，Tier-B 只用於 retrieval expansion；新 edge 仍須重新通過 Tier A。
2. 先做 entity normalization、generic-node suppression、negation/species/context 對齊。
3. 對同起終點路徑以 bridge、PMID set、quote set 去重，優先跨 PMID 且真正增量的 path。
4. answer context 每題最多 1–2 條；4-hop 必須逐 hop 結構化呈現，不能套 2-hop 句型。
5. 生成後逐 claim 驗證；任何 hop 不符便刪除該 graph claim，回退到 C 或 B 的答案。

## 成本與效率

答案生成使用地端 gpt-oss 120B，無外部 API 費。各臂總時間：A 561 秒、B 677 秒、
C 679 秒、D 696 秒；在 frozen graph 條件下 C 幾乎沒有額外 latency，D 約比 B 多
19 秒總計。外部裁判實際成本約 **US$0.544**：GPT-4.1 約 US$0.179，Claude Sonnet
4.6 約 US$0.365；地端裁判無 API 費。

最合理的下一版不是增加 D 的輸入 path 數量，而是實作「large reliable pool + top-1/2
answer selection + hop-complete renderer + post-generation evidence gate」，再只重跑 C/D。
