# Hybrid RAG 增量效益實驗結果

本結果為 20 題 path-positive 開發集、兩輪同一地端 gpt-oss:120b 匿名盲評；
不是人類生醫專家評審，也不是代表性 ITT 或正式 superiority study。
14 題未觸發 incremental intervention，所有系統直接重用同一份 B 答案；只有 6 題有實際 treatment 差異。

## 平均總分

| System | ITT 20 | Intervention 6 |
|---|---:|---:|
| B_traditional_rag | 4.3042 | 4.2639 |
| C1_kg_reranking | 4.2208 | 3.9861 |
| C2_kg_expansion | 4.1000 | 3.5833 |
| D1_all_safe_paths | 4.4083 | 4.6111 |
| D2_incremental_paths | 4.3417 | 4.3889 |
| D3_incremental_natural_fusion | 4.1500 | 3.7500 |
| Oracle_local_path_selection | 4.2958 | 4.2361 |

## 主要配對比較（Intervention 6）

| Contrast | Mean diff | Question bootstrap 95% CI | W/L/T | Cluster n | Cluster mean | Cluster 95% CI | Pass1 / Pass2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1-B | -0.2778 | -1.1944 to +0.7503 | 2/3/1 | 3 | -0.2083 | -0.4167 to +0.0000 | -0.3611 / -0.1944 |
| C2-B | -0.6806 | -1.8333 to +0.3611 | 3/3/0 | 3 | -0.7315 | -1.1667 to -0.3611 | -0.8611 / -0.5000 |
| D1-B | +0.3472 | -0.3750 to +1.1389 | 2/2/2 | 3 | +0.1898 | -0.3750 to +0.9444 | +0.2778 / +0.4167 |
| D2-B | +0.1250 | -0.5972 to +0.8333 | 2/1/3 | 3 | +0.0093 | -0.6667 to +0.6944 | +0.1389 / +0.1111 |
| D3-B | -0.5139 | -1.1667 to +0.0417 | 1/4/1 | 3 | -0.4213 | -0.7083 to +0.0000 | -0.3889 / -0.6389 |
| D2-D1 | -0.2222 | -0.5417 to +0.1111 | 1/3/2 | 3 | -0.1806 | -0.2917 to +0.0000 | -0.1389 / -0.3056 |
| D3-D2 | -0.6389 | -1.2639 to -0.0694 | 1/4/1 | 3 | -0.4306 | -1.2500 to +0.0000 | -0.5278 / -0.7500 |
| Oracle-D3 | +0.4861 | +0.0694 to +1.0833 | 4/0/2 | 3 | +0.3611 | +0.0833 to +0.8333 | +0.3333 / +0.6389 |

## 解讀限制

- 六個 intervention 題只來自三個獨立 source/endpoint clusters，cluster CI 極不穩定。
- Oracle 選徑與盲評使用同一地端模型，Oracle 分數不是獨立外部驗證。
- 兩輪 pass 的差異反映同一模型的順序與抽樣變異；細小差距不可宣稱 superiority。
- Frozen graph 使用較舊的 graph/NER schema；結果只適用於本次凍結 exposure。
