# Structured gated path answer（D v2）修正與測試

## 修正內容

- reliable retrieval pool 由 20 條擴至 44 條，Tier-A 規則未變：path Tier A、
  `claim_safe=true`、每個 edge 有 relation-aligned quote 且 confidence >= 0.8。
- 新增 answer-path selector：每題最多 2 條，優先 graph-incremental、跨 PMID、非 generic、
  非 cycle，並按 bridge + PMID evidence 去重。
- LLM 不再自行抄寫 PATH；正文只根據 reranked PubMed context 生成。
- graph insights 由程式逐 hop 決定性渲染，每 hop 含 source、relation、target 與 PMID。
- verifier 支援標記式 1–4 hop 與重複節點；任何 unsupported PATH claim 令該題 fail-closed。

## Evidence-compliance 結果

| 指標 | 舊 D | 新 D v2 |
|---|---:|---:|
| Reliable pool | 20 | 44 |
| 放入答案的 paths | 不穩定 | 32（每題 1–2） |
| Supported PATH claims | 11 | 32 |
| Unsupported PATH claims | 7 | 0 |
| 完全未引用 PATH 的題目 | 5/20 | 0/20 |
| Unsupported rate（有 PATH claims） | 38.9% | 0% |

20/20 題生成成功。新 D 總時間 712.79 秒、median 35.32 秒；舊 D 分別為
696.39 秒、34.11 秒。安全性提升只增加約 0.8 秒/題 median latency。

## 兩個外部 AI 裁判盲評

GPT-4.1 與 Claude Sonnet 4.6 對 B、C、舊 D、新 D 的 80 份匿名答案完成 160 筆評分。
它們是 AI proxy，不是人類生醫專家。

| System | 平均分 |
|---|---:|
| B Traditional RAG | 4.583 |
| C KG reranking | 4.679 |
| 舊 D | 3.896 |
| 新 D v2 | 4.596 |

- 新D − 舊D：**+0.700**，95% CI 0.392–0.992；17勝3負；sign-test p=0.0026。
- 新D − B：+0.013，95% CI -0.267–0.279；11勝6負3平；未證明優越。
- C − B：+0.096，95% CI -0.025–0.221；未證明優越。

以 11 個 source/endpoint clusters 而非 20 個題號重算：

- 新D − 舊D：+0.673，95% CI 0.352–0.955。
- 新D − B：+0.088，95% CI -0.158–0.299。
- C − B：+0.126，95% CI -0.014–0.268。

因此修正明確消除了舊 D 的傷害，但目前只能說新 D 與 B 相當，尚不能宣稱優於 B。

## 題目設計與選擇偏差

題目選擇會造成大幅差異。一般 ITT、事後 path subset、刻意 path-positive enrichment
回答的是不同問題；mechanism/multi-hop 比例、gold PMID 在原 text rank 的位置、domain
重複、endpoint 改寫題與 null/negative 題比例都會改變效果量。

本組 20 題實際只有 11 個 source/endpoint clusters；若把改寫題當成 20 個獨立樣本，CI
會過度樂觀。相同 B/C 答案在不同盲評 pass 的平均分亦有變化，顯示 AI judge 本身具有
panel/order variance，細微差異不能只評一次。

避免方式：

1. 同時保留代表性 ITT 與預先凍結 path-positive efficacy cohort，分開報告。
2. 從實際 query sampling frame 分層隨機抽樣，不以 KG 成功與否反向選題。
3. 每個 endpoint/entity pair 最多一題進 primary analysis；其餘改寫只做 robustness。
4. 以 endpoint/domain cluster bootstrap 或 mixed model 分析，並做 leave-one-domain-out。
5. 預先凍結題目、query、corpus、qrels、排除規則與 primary endpoint；zero-path 不得事後刪除。
6. 使用未參與開發的新 domain、不同 curator、不同時間窗作 external locked holdout。
7. 多裁判重複盲評並報 judge sensitivity；細微優勢必須跨 panel 才能宣稱。

目前 20 題適合開發驗證。正式 superiority study 建議 80–120 個獨立 endpoint clusters，
並以本次 paired variance 做 power calculation。

外部裁判成本約 US$0.539；D v2 生成使用地端 gpt-oss 120B，無外部 API 費。
