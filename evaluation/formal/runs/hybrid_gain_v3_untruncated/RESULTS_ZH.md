# Hybrid RAG 增量效益實驗結果

本結果為 20 題 path-positive 開發集、兩輪同一地端 gpt-oss:120b 匿名盲評；
不是人類生醫專家評審，也不是代表性 ITT 或正式 superiority study。
16 題未觸發 incremental intervention，所有系統直接重用同一份 B 答案；只有 4 題有實際 treatment 差異。

## 結論摘要

- D3 相對 B 在 intervention 題為 +0.0417，cluster mean +0.1111（95% CI -0.0278 至 +0.2500）；納入 16 題零差異後，ITT 差值僅 +0.0083。**未證明 Hybrid 優於 Traditional RAG**。
- D3 相對 D2 為 +0.2917（兩輪方向一致），但只有 2 個 clusters，cluster CI +0.0000 至 +0.3889；自然語言融合有正向訊號，尚非確認性證據。
- C2 KG expansion 相對 B 為 +0.1042；D2 相對 D1 為 +0.1667。目前訊號較支持精準 expansion 與 incremental-only selection，不支持無差別加入更多安全 paths。
- 介入率為 4/20 （20.0%）；覆蓋率仍是主要限制。

## Intervention 題平均總分

| System | Intervention 4 |
|---|---:|
| B_traditional_rag | 4.7083 |
| C1_kg_reranking | 4.7500 |
| C2_kg_expansion | 4.8125 |
| D1_all_safe_paths | 4.2917 |
| D2_incremental_paths | 4.4583 |
| D3_incremental_natural_fusion | 4.7500 |
| Oracle_local_path_selection | 4.5625 |

## 主要配對比較（Intervention 4）

| Contrast | Mean diff | Question bootstrap 95% CI | W/L/T | Cluster n | Cluster mean | Cluster 95% CI | Pass1 / Pass2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1-B | +0.0417 | +0.0000 to +0.0833 | 2/0/2 | 2 | +0.0556 | +0.0278 to +0.0833 | +0.0000 / +0.0833 |
| C2-B | +0.1042 | +0.0000 to +0.2083 | 2/0/2 | 2 | +0.1528 | +0.0556 to +0.2500 | +0.0833 / +0.1250 |
| D1-B | -0.4167 | -0.9792 to +0.0625 | 1/3/0 | 2 | -0.1944 | -0.6389 to +0.2500 | -0.1250 / -0.7083 |
| D2-B | -0.2500 | -0.6667 to +0.1667 | 2/2/0 | 2 | -0.0833 | -0.4167 to +0.2500 | -0.1667 / -0.3333 |
| D3-B | +0.0417 | -0.3125 to +0.3333 | 2/1/1 | 2 | +0.1111 | -0.0278 to +0.2500 | +0.0417 / +0.0417 |
| D2-D1 | +0.1667 | -0.2083 to +0.5417 | 2/1/1 | 2 | +0.1111 | +0.0000 to +0.2222 | -0.0417 / +0.3750 |
| D3-D2 | +0.2917 | +0.0833 to +0.5000 | 3/0/1 | 2 | +0.1944 | +0.0000 to +0.3889 | +0.2083 / +0.3750 |
| Oracle-D3 | -0.1875 | -0.6250 to +0.0625 | 1/1/2 | 2 | -0.1250 | -0.2500 to +0.0000 | -0.2500 / -0.1250 |

## ITT 20 相對差值

Non-intervention 題的答案逐字相同，因此其 paired difference 精確設為 0。

| Contrast | ITT mean diff | Question bootstrap 95% CI |
|---|---:|---:|
| C1-B | +0.0083 | +0.0000 to +0.0208 |
| C2-B | +0.0208 | +0.0000 to +0.0500 |
| D1-B | -0.0833 | -0.2333 to +0.0167 |
| D2-B | -0.0500 | -0.1542 to +0.0292 |
| D3-B | +0.0083 | -0.0625 to +0.0750 |
| D2-D1 | +0.0333 | -0.0417 to +0.1167 |
| D3-D2 | +0.0583 | +0.0000 to +0.1292 |
| Oracle-D3 | -0.0375 | -0.1250 to +0.0125 |

## 解讀限制

- 4 個 intervention 題只來自 2 個獨立 source/endpoint clusters，cluster CI 極不穩定。
- 未重評完全相同的 non-intervention 答案，因此不提供各系統 ITT 絕對平均；相對差值將這些題精確設為 0。
- Oracle 選徑與盲評使用同一地端模型，Oracle 分數不是獨立外部驗證。
- 盲評者未看到完整 source documents；其 grounding 分數僅為輔助，引用安全性以 deterministic claim audit 為準。
- 兩輪 pass 的差異反映同一模型的順序與抽樣變異；細小差距不可宣稱 superiority。
- Frozen graph 使用較舊的 graph/NER schema；結果只適用於本次凍結 exposure。
