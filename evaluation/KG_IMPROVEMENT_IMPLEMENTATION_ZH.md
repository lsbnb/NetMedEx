# KG 改善第一階段實作與 replay

## 已完成

- Query router：只有 mechanism、multi-hop、hypothesis、discovery 類型啟動 KG；其餘走 text-only。
- Content-addressed persistent graph cache：相同 corpus、model 與 extraction 設定可跨 run 重用。
- 第二階段 PubMed expansion：從 retrieval-safe、跨 PMID、非 generic bridge 的路徑建立查詢。
- Claim safety 分離：Tier-B 路徑可用來找文獻，但不能作為回答中的 graph claim。
- Generic bridge 與跨 PMID gate：排除 cancer、signaling、inflammation 等單獨作為橋接的捷徑。
- Bounded expansion：最多兩個新文件進入 top-10，且必須超過原 ranking tail 的分數 margin。
- A/B/C/D runner 與 protocol。

## 20 題零生成 replay

這次重用既有 corpus 與 frozen graph exposure，不產生答案，也沒有 LLM completion tokens。

| 指標 | 結果 |
|---|---:|
| KG routed | 13/20 |
| Text-only bypass | 7/20 |
| Claim-safe path coverage（全部） | 3/20 = 15.0% |
| Claim-safe path coverage（KG routed） | 3/13 = 23.1% |
| Expansion-query coverage（全部） | 4/20 = 20.0% |
| Expansion-query coverage（KG routed） | 4/13 = 30.8% |
| Expansion 抓取文件 | 60 |
| 通過 bounded merge 進入 top-10 | 7 |

Expansion 出現在 Q008、Q028、Q029、Q037。Q028 原本沒有 claim-safe path，但 Tier-B 路徑仍成功產生第二階段查詢，證明 retrieval-only 與 claim-safe 分層有效。

## Retrieval 判讀限制

Traditional RAG 的 P@5/R@10/nDCG@10 為 0.83/0.4712/0.6078；bounded KG expansion 為
0.79/0.4571/0.5784。新增文獻造成 judged@10 從 1.0 降至 0.9637，表示部分新增 PMID 不在原本 frozen qrels pool。不能直接把 unjudged 當作不相關，否則會系統性懲罰任何真正找到新文獻的 expansion 方法。下一步必須把 A–D pooled top-k 合併、盲化評定新增 PMID，再重新計算 recall 與 nDCG。

## 為何尚未達 60%

現有 frozen exposure 中只有 3/13 KG 題有 claim-safe path，而且 replay 顯示 graph schema 與 NER schema 已過期。60% 不能透過放寬 evidence gate 達成；必須改用較大的預建 domain KG、以最新版 schema 重建，並改善 endpoint normalization。正式 acceptance criteria 應分成：

- claim-safe path coverage >=60%；
- retrieval-expansion coverage >=70%；
- biological edge precision 不下降；
- 新增文件經 pooled blind review 後的 Precision@10 不低於 Traditional；
- 每題 latency/token 成本另行報告。

## 四臂執行方式

使用 `evaluation/run_ablation_abcd.py`。完整設計見 `evaluation/ABLATION_ABCD_PROTOCOL.md`。Runner 會輸出四個獨立 run、共享 frozen corpus 與 graph cache，最後合併為 `ablation_system_outputs.csv`，供後續盲評。
