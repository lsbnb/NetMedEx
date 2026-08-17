# NetMedEx 20 題 pilot 與 Temporal Holdout 結果

## 結論摘要

兩個需求都已執行完成。20 題 pilot 顯示兩種 RAG 都明顯優於 closed-book GPT-4.1，但目前沒有證據顯示 NetMedEx Hybrid RAG 的平均表現優於 Traditional RAG。Temporal holdout 的流程可行，也找到 2015 年前未直接共現、後來出現直接研究的關係；不過嚴格實驗佐證只有 1/2，尚不能宣稱達到 70–80% 或證明優於 Traditional RAG。

「生醫專家」評審實際為 Claude Sonnet 4.6 的盲測 AI expert proxy，並非人類專家；所有結果都保留這項標示。

## 20 題三系統 pilot

固定 20 題、三個系統均由 GPT-4.1 產生答案：NetMedEx Hybrid RAG、Traditional RAG、closed-book general LLM。評審看不到系統名稱，逐題評 6 個 1–5 分指標。

| 系統 | Correctness | Completeness | Relevance | Grounding | Mechanistic | Research value | 總平均 |
|---|---:|---:|---:|---:|---:|---:|---:|
| NetMedEx Hybrid RAG | 4.20 | 4.60 | 4.85 | 3.95 | 4.55 | 4.50 | 4.442 |
| Traditional RAG | 4.30 | 4.55 | 4.95 | 4.05 | 4.60 | 4.55 | 4.500 |
| closed-book GPT-4.1 | 4.05 | 3.65 | 4.80 | 2.45 | 4.30 | 3.35 | 3.767 |

逐題首選票為 Hybrid 10、Traditional 7、general LLM 3。配對總分分析：

- Hybrid − general：+0.675，95% bootstrap CI 0.292–1.058，sign-test p=0.0044。
- Traditional − general：+0.733，95% CI 0.425–1.058，p=0.0192。
- Hybrid − Traditional：−0.058，95% CI −0.300–0.125，p=0.5811。

因此可支持「RAG 優於不檢索 LLM」，不能支持「Hybrid 平均分優於 Traditional」。20 題且只有一個 AI 評審，應視為 pilot，不是最終論文結論。

檢索端 P@5 為 0.83、R@10 為 0.471；兩個 RAG arm 的 R@10 完全相同，因為目前實驗設計讓兩者共用相同的基礎 retrieval pool。這項 pilot 比較的是回答合成，不是不同 retriever，因此不能用它證明 Hybrid 的 retrieval superiority；R@10 也未達原訂 0.90。

## Token 與估計價格

20 題產生共 601,083 tokens；Claude 盲評共 74,137 tokens；合計 675,220 tokens。以 GPT-4.1 每百萬 input/output tokens US$2/US$8，Claude Sonnet 每百萬 US$3/US$15 估算，20 題 pilot 約 US$3.16（GPT-4.1 US$2.83；Claude US$0.34）。

Temporal holdout 的有效、日期稽核後 graph run 使用 328,704 GPT-4.1 tokens，約 US$1.65。另有一輪因 PubMed 日期欄位跨年而作廢的 run，耗用 339,776 tokens，約 US$1.69。故有效工作約 US$4.82；把作廢 run 也計入實際消耗約 US$6.50。未含稅、網路與本機運算成本。

## Temporal Holdout feasibility

發現 corpus 共 124 篇，實際納入文獻的最大出版年為 2015。PubMed 原始日期查詢混入 7 篇標為 2016 的紀錄；程式已加入 ESummary 年份硬過濾，第一輪受污染結果完全排除。候選先凍結並計算 SHA-256，之後才查 2016–2025。

三個候選中，KRAS–PD-1 因 2015 年前已有 7 篇直接共現而排除。兩個合格候選如下：

| 候選 | 2015 前直接文獻 | 2016–2025 直接文獻 | 嚴格判讀 |
|---|---:|---:|---|
| KRAS–CTLA-4 | 0 | 55 | 部分實驗支持；2017 KRAS-mutant 小鼠模型測試 MEK inhibitor + anti-CTLA-4，但沒有直接證明 KRAS status 的因果調節 |
| celiac disease–periodontitis | 0 | 6 | 有後續直接人體研究，但屬觀察性且未驗證 dysbiosis 中介；結果並不支持簡單正向關係 |

因此：future direct-link recovery 2/2（100%）、嚴格或部分實驗佐證 1/2（50%）、完整 A→B→C 中介鏈驗證 0/2（0%）。這證明實驗管線可以運作，但樣本太小且未達預設 70–80% 嚴格目標。

## 下一階段的必要修正

要真正檢驗 Hybrid 優於 Traditional，正式研究應先固定至少 50–100 個由 2015 前資料演算法產生的候選，讓兩系統在完全相同的 pre-cutoff corpus 與 token budget 下各自產生候選，再以 2016–2025 實驗文獻盲評。現代 GPT-4.1 本身知道 2015 後資訊，因此 temporal discovery 的候選生成必須限制為可逐邊追溯的圖路徑，不能把 LLM 自由生成內容當成 2015 年的預測。

## 主要 artifacts

- `pilot20/pilot_results_v1.json`：20 題數值摘要。
- `pilot20/answer_ratings_worksheet.csv`：60 筆盲化答案。
- `pilot20/answer_ratings_claude.csv`：Claude AI proxy 評分。
- `pilot20/retrieval_metrics.json`：檢索指標。
- `temporal_holdout_pilot/candidate_freeze_v1.json`：未查看未來文獻前的候選凍結檔。
- `temporal_holdout_pilot/future_validation_v1.json`：2016–2025 查核結果。
- `temporal_holdout_pilot/temporal_results_v1.json`：嚴格判讀摘要。

