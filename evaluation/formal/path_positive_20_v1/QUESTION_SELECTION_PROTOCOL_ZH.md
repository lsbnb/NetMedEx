# NetMedEx 題目選擇與偏差控制 protocol

## 為何題目設計會大幅影響結果

會。retrieval 題偏向 text RAG，mechanism/multi-hop 題較可能讓 KG 有作用；直接把答案寫在
query 中、gold PMID 已位於 top ranks、特定 domain 重複過多、刻意只選 path-positive 題，
都會改變 effect size。相同 biological endpoint 改寫成多題也會造成假性樣本量增加。

## 必須分開的兩個 estimand

1. **ITT / deployable effectiveness**：從預先定義的真實查詢母體抽樣，包含沒有 path 的題目；
   回答「一般使用時整體是否優於 Traditional RAG」。
2. **Path-positive efficacy**：在答案生成前，以固定 gate 判定有 Tier-A path 的 enrichment
   cohort；回答「有可靠 KG substrate 時是否有效」。不得用此結果宣稱整體勝率。

## Confirmatory benchmark 建議

- 在跑任何答案前凍結 protocol、題目、queries、corpus、qrels、主要 endpoint 與分析程式。
- 由臨床／研究使用情境建立 sampling frame，不由 KG 目前會不會成功反向挑題。
- 分層抽樣並設配額：retrieval、association、mechanism、multi-hop、discovery、negative/null；
  domain、species、study type、answerability 與年代亦須平衡。
- 每個 biological endpoint／entity pair 最多一題進 primary analysis；改寫題只放 robustness set。
- 題目作者不得查看 system outputs；path preflight 不得讀答案、judge rating 或 qrels 分數。
- 保留所有失敗與 zero-path 題；不得在結果出來後排除。缺失答案按預先規則計為 failure。
- Primary unit 是 endpoint/domain cluster，不是表面 question ID；以 cluster bootstrap 或 mixed
  model 計算 CI，並做 leave-one-domain-out 與 leave-one-endpoint-out sensitivity analysis。
- 同時報 all-query ITT、router-eligible、pre-frozen path-positive；其他 subgroup 僅探索性。
- 另設完全未參與開發的 external holdout：新 domain、不同日期區間與不同 curator。

## 建議規模

20 題適合開發與找 failure mode，不適合證明優越。修正完成後先用另一組 20–30 題做
locked validation；正式 confirmatory 建議至少 80–120 個**獨立 endpoint clusters**，再依 pilot
中的 paired variance 做 power calculation。Temporal discovery 需另建 pre-cutoff KG 與
post-cutoff validation cohort，不和一般答案品質題混合。
