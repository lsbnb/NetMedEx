# Hybrid RAG 增量效益實驗結果

本結果為 20 題 path-positive 開發集、兩輪同一地端 gpt-oss:120b 匿名盲評；
不是人類生醫專家評審，也不是代表性 ITT 或正式 superiority study。
16 題未觸發 incremental intervention，所有系統直接重用同一份 B 答案；只有 4 題有實際 treatment 差異。

## Intervention 題平均總分

| System | Intervention 4 |
|---|---:|
| B_traditional_rag | 4.4583 |
| C1_kg_reranking | 4.2292 |
| C2_kg_expansion | 4.6458 |
| D1_all_safe_paths | 4.5417 |
| D2_incremental_paths | 4.6042 |
| D3_incremental_natural_fusion | 4.1250 |
| Oracle_local_path_selection | 4.0833 |

## 主要配對比較（Intervention 4）

| Contrast | Mean diff | Question bootstrap 95% CI | W/L/T | Cluster n | Cluster mean | Cluster 95% CI | Pass1 / Pass2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1-B | -0.2292 | -1.5625 to +1.2500 | 1/2/1 | 2 | -0.1528 | -0.3056 to +0.0000 | -0.4167 / -0.0417 |
| C2-B | +0.1875 | -1.0625 to +1.6250 | 1/1/2 | 2 | +0.1250 | +0.0000 to +0.2500 | +0.1250 / +0.2500 |
| D1-B | +0.0833 | -1.1042 to +1.5625 | 1/3/0 | 2 | -0.0278 | -0.2500 to +0.1944 | +0.2917 / -0.1250 |
| D2-B | +0.1458 | -0.8542 to +1.5000 | 1/3/0 | 2 | +0.0139 | -0.2500 to +0.2778 | +0.1667 / +0.1250 |
| D3-B | -0.3333 | -2.0000 to +1.4167 | 1/3/0 | 2 | -0.3056 | -0.3611 to -0.2500 | -0.3750 / -0.2917 |
| D2-D1 | +0.0625 | -0.0625 to +0.2500 | 1/1/2 | 2 | +0.0417 | +0.0000 to +0.0833 | -0.1250 / +0.2500 |
| D3-D2 | -0.4792 | -1.8125 to +0.3750 | 1/1/2 | 2 | -0.3194 | -0.6389 to +0.0000 | -0.5417 / -0.4167 |
| Oracle-D3 | -0.0417 | -0.5417 to +0.5833 | 1/2/1 | 2 | -0.0278 | -0.0556 to +0.0000 | -0.0417 / -0.0417 |

## 解讀限制

- 4 個 intervention 題只來自 2 個獨立 source/endpoint clusters，cluster CI 極不穩定。
- 未重評完全相同的 non-intervention 答案，因此不提供各系統 ITT 絕對平均；相對差值將這些題精確設為 0。
- Oracle 選徑與盲評使用同一地端模型，Oracle 分數不是獨立外部驗證。
- 兩輪 pass 的差異反映同一模型的順序與抽樣變異；細小差距不可宣稱 superiority。
- Frozen graph 使用較舊的 graph/NER schema；結果只適用於本次凍結 exposure。
