# NetMedEx 量化評估重整與 Hybrid RAG／語意整合／2-hop 優勢驗證方案

## 1. 決策摘要

目前最嚴謹的 formal-v2 結果**不能支持 NetMedEx 在一般文件檢索上優於 Traditional
RAG**。兩者 Precision@5 同為 0.852，Traditional RAG 的 Recall@10 反而高 0.0079，
nDCG@10 差異不顯著。這個結果應如實保留，不宜再以早期 10 題 seed 結果主張整體
retrieval superiority。

NetMedEx 現階段最有利、但仍屬初步的訊號，出現在**機制與假說生成價值**：19 題
mechanism／hypothesis／2-hop 子集的盲化 AI 評分中，NetMedEx overall mean 為 4.21，
Traditional RAG 為 4.07；NetMedEx 在 9 題較高、3 題較低、7 題平手。不過 paired mean
difference 為 +0.145，95% CI [-0.020, 0.316]，sign-test p=0.146，尚未達統計顯著。

現有設計未能充分放大 Hybrid RAG 差異。兩個 RAG 使用相同的小型 PubMed corpus 與
相同向量檢索器，NetMedEx 主要只對 graph path 涵蓋的 PMID 乘上 1.5 倍 boost。兩臂
top-10 的平均 Jaccard overlap 為 0.850，50 題中 29 題的 top-10 集合完全相同；核心
9 題 hypothesis／2-hop 題型中，平均 overlap 更達 0.897，且 7/9 題完全相同。當兩臂
取得幾乎相同的文件，文件層級 P@5、Recall@10、nDCG@10 自然難以量到 graph reasoning
的增益。

因此，後續不應只重跑同一套 retrieval benchmark。建議把研究主張改成兩階段：

1. 證明 NetMedEx 在一般文件檢索上不劣於 text-only RAG。
2. 以 path-level、cross-document synthesis 與 evidence-grounded hypothesis 指標，驗證
   語意整合及 2-hop 在機制型任務上的額外價值。

## 2. 證據層級與可用結論

| 證據層級 | 資料 | 可用方式 | 不可用方式 |
|---|---|---|---|
| 主要結果 | formal-v2：50 題、877 個 pooled judgments、兩個 RAG 的 Judged@10=1.0 | 報告正式 retrieval 結果與 paired CI/p-value | 宣稱 human expert-validated；所有標籤皆為 multi-model AI adjudication |
| 補充結果 | 19 題 hypothesis/mechanism 盲化雙 AI 評分 | 報告方向性趨勢與 effect estimate | 宣稱顯著優勢或臨床／專家驗證 |
| 診斷結果 | 224 個 semantic edges、雙 AI 評分 | 定位 relation extraction 與 directionality 問題 | 當作 NetMedEx 優勢證據 |
| 探索性結果 | 10 題 curated seed | 說明評估流程與早期假說 | 與正式 50 題結果混在同一主表，或作為最終效能結論 |

建議所有論文表格明確標示 `Formal internal-AI benchmark`、`Supplementary blinded AI
rating`、`Exploratory curated seed`，避免不同成熟度的結果被讀者誤認為同一批實驗。

## 3. 重整後的量化結果

### 3.1 主要終點：formal-v2 文件檢索

| System | Precision@5 | Recall@10 | nDCG@10 | Judged@10 | Bpref |
|---|---:|---:|---:|---:|---:|
| NetMedEx Hybrid RAG | 0.8520 | 0.4316 | 0.6289 | 1.0000 | 0.3954 |
| Traditional RAG | 0.8520 | 0.4394 | 0.6341 | 1.0000 | 0.4254 |
| NetMedEx − Traditional | 0.0000 | -0.0079 | -0.0053 | — | -0.0300 |
| 95% CI（前三項） | [-0.0160, 0.0160] | [-0.0146, -0.0023] | [-0.0182, 0.0059] | — | — |
| Wilcoxon p（前三項） | 0.9836 | 0.0144 | 0.8080 | — | — |

正確解讀是：Precision@5 持平、nDCG@10 無顯著差異，而 Traditional RAG 在 Recall@10
有很小但顯著的優勢。這組指標只衡量「相關文件是否排得較前」，並未衡量系統是否把
兩篇不同文獻串成可追溯的 A → B → C 機制。

### 3.2 題型分層的探索性分析

| Stratum | n | System | P@5 | Recall@10 | nDCG@10 |
|---|---:|---|---:|---:|---:|
| Hypothesis + two-hop | 9 | NetMedEx | 0.7778 | 0.3983 | 0.5151 |
| Hypothesis + two-hop | 9 | Traditional | 0.8000 | 0.3983 | 0.5054 |
| 擴充機制型題組 | 19 | NetMedEx | 0.8316 | 0.4350 | 0.6161 |
| 擴充機制型題組 | 19 | Traditional | 0.8526 | 0.4407 | 0.6124 |

這些分層數值只適合作描述，不應單獨宣稱顯著性。它們進一步顯示：即使限縮到機制／
2-hop 題型，文件相關性指標仍沒有穩定的 NetMedEx 優勢；需要改用能直接量到 path 與
跨文件整合的終點。

### 3.3 假說與機制整合價值

| Dimension | NetMedEx | Traditional RAG | Difference |
|---|---:|---:|---:|
| Novelty | 3.26 | 3.05 | +0.21 |
| Plausibility | 4.71 | 4.66 | +0.05 |
| Testability | 4.74 | 4.63 | +0.11 |
| Research value | 4.13 | 3.92 | +0.21 |
| Overall mean | 4.21 | 4.07 | +0.145（paired question-level） |

這是目前最接近 NetMedEx 核心價值主張的結果，但仍只是「promising directional
signal」。95% CI 包含 0，且 testability 的雙評者 weighted kappa 僅 0.12；後續應用
人類生醫專家、較清楚的 rubric 與更大的 mechanism/2-hop 題組確認。

### 3.4 語意關係品質與風險

| Metric | Baseline | 95% bootstrap CI |
|---|---:|---:|
| Biological edge precision | 0.531 | [0.483, 0.619] |
| Relation-type precision | 0.328 | [0.280, 0.398] |
| Relation-type precision，2-hop edges | 0.28 | — |
| Relation-type precision，1-hop edges | 0.36 | — |

雙 AI 評者的一致性並不低（biological meaningfulness kappa=0.62；relation type
kappa=0.75），所以目前低 precision 不能簡單歸因於評分雜訊。主要錯誤包含：

- 關係方向顛倒，例如 cause/effect 或 miRNA target 的 source/target 反轉。
- 非生物字串成為節點，例如 `0409`。
- supporting title 無法支持抽出的 relation type；需要回到 evidence sentence 判斷。
- 2-hop 路徑會累積兩條 edge 的誤差，任一錯誤都可能使整條機制失效。

第二 LLM direction verification 的 paired 結果未顯著改善 relation-type precision：整體
mean difference -0.018，95% CI [-0.105, 0.058]；2-hop raw precision 由 0.28 到 0.34，
但 paired CI 仍包含 0。因此目前只能說 verifier 機制可運作，不能說它已解決方向問題。

### 3.5 效率與可追溯性

正式 run 共處理 531 篇 PubTator 文件、1,499 個節點與 1,951 條邊；每題總時間中位數
約 110 秒，semantic graph construction 平均約 64.6 秒，是主要成本。NetMedEx 回答中
抽出的 755 次 PMID mentions 均可回溯到該題 corpus，但這只證明 citation traceability，
不等於 claim-level citation support。

## 4. 為何現行評估難以顯示 Hybrid RAG 優勢

### 4.1 比較臂缺乏足夠 contrast

目前兩臂共用相同的最多 15 篇文件與相同 vector index。Hybrid arm 的主要 retrieval
差別是把 graph path 涵蓋的 PMID score 乘以 1.5；這通常只微調相同候選文件的排序，
沒有測試 graph 能否從較大的 corpus 中找到 text-only 未找到的 bridge evidence。

### 4.2 指標與產品主張錯位

P@5、Recall@10、nDCG@10 適合 direct retrieval，但 NetMedEx 的主張是 semantic
normalization、typed relation、cross-document evidence stitching 與 2-hop discovery。
若 gold label 只有 question-PMID relevance，就無法判斷 bridge entity、兩條邊、方向與
per-edge evidence 是否正確。

### 4.3 Graph quality 形成效益上限

若單條 relation-type precision 約 0.33，在僅供直覺說明的獨立假設下，兩條邊皆正確的
期望比例約為 0.11。真實錯誤不一定獨立，不能把 0.11 當成實測 path precision；但這仍
說明先改善 semantic edge quality，通常比調整 2-hop score 權重更優先。

### 4.4 題數與評者不足

核心 hypothesis／2-hop 僅 9 題，擴充後也只有 19 題；目前 effect estimate 的 CI 已
明確顯示檢定力不足。AI rating 可協助開發，但不足以支持 biomedical expert validation。

## 5. 建議解決方案

### P0：重做能隔離各元件效益的 ablation study

固定相同 corpus snapshot、generator LLM、prompt、top-k 與 token budget，至少比較：

| Arm | Vector text | Entity normalization | Semantic graph | 2-hop traversal |
|---|---:|---:|---:|---:|
| A. Text-only RAG | ✓ | — | — | — |
| B. Text + normalized entities | ✓ | ✓ | — | — |
| C. 1-hop Graph RAG | ✓ | ✓ | ✓ | — |
| D. 2-hop Graph RAG | ✓ | ✓ | ✓ | ✓ |
| E. Full Hybrid RAG | ✓ | ✓ | ✓ | ✓，並與 text score 融合 |

這可分別回答：「語意正規化是否改善 entity recall」、「semantic edge 是否改善機制
正確性」、「2-hop 是否增加受證據支持的新橋接假說」、「hybrid fusion 是否兼顧一般
retrieval 與 graph discovery」。所有 arm 應由同一批盲化評者成對比較。

### P0：新增真正對應 2-hop 的 primary endpoints

對每題建立 path qrels：`source`、`bridge`、`target`、兩個 relation types、方向、每條邊
的 supporting PMIDs 與 evidence level。至少報告：

- **Bridge Entity Precision/Recall/F1**：系統提出的中介節點是否為 gold 或專家接受的
  合理橋接點。
- **Supported Path Precision**：A → B 與 B → C 兩條邊都具有可核對 evidence 的路徑比例。
- **Exact／Partial Path Recall**：完整命中兩條邊與只命中其中一條邊分開計算。
- **Direction Accuracy**：只對有方向的 semantic relations 計分，neutral relation 另列。
- **Evidence Completeness**：兩條邊是否各有 PMID，且引用是否直接支持該 edge。
- **Cross-document Synthesis Rate**：有效路徑的兩條邊來自不同文章的比例；這是 text-only
  RAG 最難直接呈現、也最能反映 NetMedEx 的指標。
- **Supported Discovery Gain@k**：相較 text-only arm，NetMedEx 額外提出且被專家判為
  plausible、non-redundant、evidence-supported 的 bridge/path 數。

文件 retrieval 改為 secondary endpoint，並採「non-inferiority + path superiority」：
先確認 Full Hybrid 在一般 nDCG@10 不明顯劣於 text-only，再檢驗 path-level 與 supported
discovery 指標是否顯著較高。

### P0：先修 semantic graph，再擴大 2-hop

1. 在建圖前加入 entity validity gate，拒絕純數字碎片、截斷 ID 與未通過 PubTator／
   ontology mapping 的節點。
2. 對 gene、miRNA、disease、chemical 分別做 namespace-aware normalization；保留原始
   mention、canonical ID 與 normalization confidence，避免錯誤合併。
3. relation extraction 必須輸出 source span、target span、evidence sentence、relation、
   direction 與 confidence；沒有足夠 evidence 時退回 `associated_with` 或 abstain。
4. direction verifier 應審核**同一批已抽出的 edge**，不可重新抽 graph 後再比較，否則
   extraction non-determinism 會污染 verifier effect。
5. 2-hop path score 採 weakest-link/min-link 原則並校準 confidence；若任一 edge 未通過
   biological validity、direction 或 evidence gate，整條 path 不進入回答主張。
6. 在回答中明確區分 `direct evidence`、`supported multi-document inference` 與
   `speculative hypothesis`，避免把 2-hop 可達性誤寫成因果證明。

建議在進入新的 end-to-end benchmark 前，先把獨立人類審查的 biological edge precision
與 directional relation precision 提升到預先註冊的門檻；例如兩者分別至少 0.80 與
0.75。這是未來目標，不是現有成績。

### P1：讓 Hybrid retrieval 真正帶入 graph-only evidence

- 將 corpus 由每題最多 15 篇擴大到能產生真實 bridge competition 的規模，並固定
  corpus snapshot 以維持公平。
- 不只對已在相同小 corpus 的 PMID 做 1.5 倍 boost；先由 query entities 找 graph
  neighborhoods，再用 edge evidence PMIDs 擴展候選文件。
- 比較 weighted sum、reciprocal rank fusion 與 learned/query-adaptive fusion；在 direct
  question 降低 graph weight，在 mechanism／2-hop question 提高 graph contribution。
- 每題記錄 `graph-only candidates`、`graph-promoted documents`、`unique relevant gain` 與
  最終答案實際使用的 path，避免只有內部 path_count、卻無法證明回答受益。
- 啟用 NodeRAG／ontology-aware query-to-node matching；目前 evaluation 曾因 substring-only
  matching 使部分題目得到 0 edge，代表 query linking 本身也是效益瓶頸。

### P1：建立專門的 2-hop benchmark

建議新增至少 50 題 mechanism／2-hop paired questions，並在 pilot variance 完成後正式做
power analysis。題目需包含：

- 跨兩篇以上文章才能完整回答的 compositional questions。
- bridge entity 不直接出現在原始 question 的 latent-path questions。
- 方向敏感題，例如 treatment → pathway inhibition → phenotype improvement。
- human／animal／in-vitro evidence 需要分層整合的問題。
- negative controls：只有 A–B、缺少 B–C，或方向互相矛盾；正確系統應 abstain。
- temporal holdout：只用時間點 T 前的文獻建圖，再用 T 後文獻驗證預測的 path，用來
  評估真正的 hypothesis discovery，而不只是重述已知知識。

### P1：人類專家與統計設計

- 由至少 2 位盲化生醫專家評 path、claim 與 hypothesis，分歧由第 3 位裁決。
- 報告 inter-rater agreement；低 agreement 的 rubric 先修訂再擴大收案。
- 所有比較以 question-level paired bootstrap CI 為主，搭配 permutation／sign test；
  多個 secondary endpoints 做 multiplicity control。
- 先預註冊一個 primary path endpoint 與一個 primary answer endpoint，避免事後挑選最有利
  指標。

### P2：效率與實用價值

把 semantic extraction 視為可快取的離線成本，分開報告 cold build、warm query 與增量
update latency。使用者研究採相同的 mechanism tasks，比較 manual PubMed 與 NetMedEx 的
完成時間、正確完成率、找到的有效 bridge 數及 NASA-TLX／SUS。現有單一 seed 使用者的
79.17% time saving 與 SUS=75 只能當流程示例，不能作正式結論。

## 6. 建議的主表與論文敘事

最終稿建議只保留三張主表：

1. **General retrieval and grounding**：P@5、Recall@10、nDCG@10、claim support、
   unsupported claim rate，回答 Hybrid 是否維持基本檢索與證據品質。
2. **Mechanistic integration and 2-hop discovery**：bridge F1、supported path precision、
   exact path recall、direction accuracy、cross-document synthesis、supported discovery gain，
   直接回答 NetMedEx 的核心優勢。
3. **Expert utility and efficiency**：hypothesis value、task success、time、SUS，回答是否對
   真實研究工作有用。

現階段可安全使用的結果敘述為：

> 在 50 題、877 個 pooled question–PMID judgments 的 internal multi-model AI-adjudicated
> benchmark 中，NetMedEx Hybrid RAG 與 Traditional RAG 的 Precision@5 相同，nDCG@10
> 無顯著差異，而 Traditional RAG 具有小幅 Recall@10 優勢。因此本研究未觀察到一般
> 文件檢索優勢。另一方面，在 19 題機制與假說生成題的補充盲化 AI 評估中，NetMedEx
> 的平均假說價值呈正向但未顯著的差異（+0.145；95% CI -0.020 至 0.316）。此結果支持
> 進一步以 path-level gold standards、semantic-edge quality control 與人類專家評估，
> 驗證 Hybrid RAG 的跨文件語意整合與 2-hop discovery 價值。

不建議使用「NetMedEx 已證實優於 Traditional RAG」；目前最精確的定位是：**一般
retrieval 尚未顯示優勢，mechanistic hypothesis value 有方向性訊號，但 semantic relation
quality 與實驗 contrast 必須先改善，才能對 2-hop 優勢做可發表的因果歸因。**

## 7. 建議執行順序

1. 修正 entity validation、relation direction 與 evidence gating，並以固定 edge set 做
   verifier paired audit。
2. 擴充 evaluation schema，加入 path qrels 與上述 2-hop 指標。
3. 實作 A–E ablation，確認每一 arm 真正產生不同 evidence exposure。
4. 建立至少 50 題專門 mechanism／2-hop benchmark 與 negative controls。
5. 先做小型人類 pilot、修訂 rubric、估計 variance，再完成 power analysis 與正式收案。
6. 最後才重跑 end-to-end benchmark，並以「retrieval non-inferiority + path superiority」
   作為核心結論架構。
