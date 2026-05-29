# NetMedEx vs MRTKG 系統比較參考文件

**建立日期**：2026-05-29  
**比較情境查詢**：有哪些 miRNAs 可以 enhance the treatment of Acute Liver Failure (ALF) and sorafenib-resistant liver cancer (SR-HCC)

---

## 一、系統簡介

### NetMedEx
- 即時抓取 PubMed 文獻，動態建立知識圖譜
- 使用 PubTator3 進行 NER（Gene / Chemical / Disease / Variant / Species 實體自動標注）
- 以 NER 共現關係建構 Graphic RAG
- 整合 AbstractRAG（語意向量）+ NodeRAG（節點向量）+ GraphRetriever（圖譜推論）
- 提供 Cytoscape 互動式知識圖譜可視化
- 支援多 LLM 供應商（OpenAI / Google / Groq / NVIDIA / OpenRouter / Local）

### MRTKG（miRNA-Related Text and Knowledge Graph）
- 預建索引，涵蓋 **30,000 篇** miRNA 相關 PubMed 文獻
- **建構方式與 NetMedEx 完全相同**：NER 共現 → Graphic RAG
- 同時建置 Text RAG（語意向量）+ Graphic RAG（知識圖譜）+ LLM 整合
- 領域專屬：以 miRNA 為核心的生醫知識庫
- 靜態資料庫（建庫時間點後不自動更新）

---

## 二、架構層級比較

| 系統組件 | NetMedEx | MRTKG |
|---|---|---|
| **文獻來源** | PubMed 即時查詢 | 預建 30,000 篇 miRNA 文獻 |
| **NER 標注** | PubTator3（Gene/Chemical/Disease/Variant） | 相同方式 |
| **邊的建構** | NER 共現，PMID 邊級標注 | 相同方式 |
| **Text RAG** | AbstractRAG（每次查詢動態建立） | 預建，語意向量持久化 |
| **Graphic RAG** | GraphRetriever（2-hop，混合評分） | 相同架構 |
| **NodeRAG** | ChromaDB 持久化節點向量索引 | 相同原理 |
| **LLM 整合** | ✅ GPT-4o / Gemini / Groq 等多供應商 | ✅ 與語言模型結合 |
| **知識圖譜視覺化** | ✅ Cytoscape 互動式圖譜 | ❌ 通常無 |
| **2-hop 路徑高亮** | ✅ twohop_highlight_paths → 圖形高亮 | ❌ |

---

## 三、Graphic RAG 多跳跨文件推論機制（兩系統相同）

兩個系統的 Graphic RAG 採用**完全相同的架構**，僅規模不同。

### 推論流程

```
用戶查詢
    ↓
find_relevant_nodes()
    ├── 子字串精確比對（High Precision）
    └── NodeRAG 語意向量搜尋（High Recall）
    ↓
_extract_top_k_paths()
    ├── 1-hop: start_node → neighbor
    └── 2-hop: start_node → neighbor → n2
    ↓
混合評分（Hybrid Scoring）
    ├── 30% NPMI 拓撲共現強度
    ├── 40% 語意提取信心度 × 關係強度 × 證據頻率
    └── 30% NodeRAG 語意相關度
    ↓
LLM 五層式推論輸出
    ├── Layer 1：直接文獻證據（PMID 引用）
    ├── Layer 2：關聯推論（2-hop 圖路徑，推測性）
    ├── Layer 3：因果機制假說（有向邊，可測試預測）
    ├── Layer 4：整合摘要
    └── Layer 5：建議追問問題
```

### 跨文件推論的關鍵設計

每條 edge 儲存多篇文獻的關係（PMID 邊級標注）：

```python
edge["relations"] = {
    "pmid_1": ["inhibits"],        # 文獻 A 的關係
    "pmid_2": ["associated_with"], # 文獻 B 的關係
    "pmid_3": ["activates"],       # 文獻 C 的關係
}
```

一條 2-hop 路徑 `A → B → C`：
- A→B edge 由 pmid_1, pmid_2 支撐（跨文獻）
- B→C edge 由 pmid_3, pmid_4 支撐（跨文獻）
- **此路徑本質上就是跨 4 篇文獻的多跳推論**

---

## 四、規模差異（核心差距）

兩系統技術架構相同，主要差距在於**圖的密度**：

| 規模指標 | NetMedEx（本次查詢） | MRTKG |
|---|---|---|
| **索引文獻數** | ~85 篇（PubTator3 標注完整者） | 30,000 篇 |
| **圖節點數（估計）** | ~170 | > 100,000 |
| **圖邊數（估計）** | ~354 | > 1,000,000 |
| **2-hop 可探索路徑** | 有限（稀疏圖） | 大量（密集圖） |
| **中介節點多樣性** | 少 | 豐富（更多間接機制路徑） |

### 圖密度對推論品質的影響

```
NetMedEx (85篇)
  miR-21 → [少數中介節點] → ALF
  → 可找到的間接路徑假說：有限

MRTKG (30,000篇)
  miR-21 → [數百個中介節點] → ALF
  → 可找到的間接路徑假說：豐富
  → 可能發現 ALF → miRNA → Exosome → SR-HCC 等長鏈路徑
```

---

## 五、為何 NetMedEx 只找到 85 篇（上限 300）

### 三層篩選機制

**第一層：PubMed 查詢範圍**
- 查詢詞為「ALF + SR-HCC + miRNA + Compounds + Exosome」的交集
- 主題高度特定，PubMed 符合文章本即有限

**第二層：PubTator3 標注覆蓋率**
- 並非所有 PubMed 文章都有 PubTator3 的 NER 標注
- 新發表文章標注延遲較高

**第三層：`biocjson_parser.py` 的強制過濾（第 103-104 行）**
```python
if not title_passage or not abstract_passage:
    continue  # 缺少 title 或 abstract 的文章直接跳過
```
- 文章必須同時具備 title 與 abstract 的 PubTator3 完整標注
- 僅缺一者即被完全排除

---

## 六、搜尋精確度 vs 召回率

| 指標 | NetMedEx | MRTKG |
|---|---|---|
| **Precision（精確度）** | 高（文章需多實體共現） | 中高（miRNA 相關即可納入） |
| **Recall（召回率）** | 低（受 85 篇及標注覆蓋限制） | 高（30,000 篇預索引） |
| **ALF ∩ SR-HCC 交集** | 強（圖譜共現直接呈現） | 需跨集合推論 |
| **罕見 miRNA 覆蓋** | 較弱 | 較強 |
| **最新文獻** | ✅ 即時 | ❌ 靜態 |
| **適合任務** | 跨疾病機制探索、圖譜視覺化 | 全面 miRNA 文獻回顧 |

---

## 七、針對 ALF + SR-HCC 查詢的預期結果差異

| 結果面向 | NetMedEx | MRTKG |
|---|---|---|
| **Layer 1 直接文獻證據** | 來自 ~85 篇的直接共現 | 更多直接相關文獻 |
| **Layer 2 關聯推論路徑** | 少（稀疏圖） | 多（密集圖，路徑更豐富） |
| **Layer 3 因果機制假說** | 受限於有向邊數量 | 有向邊更多，假說更豐富 |
| **Exosome 遞送路徑** | 有（若原文共現） | 較完整（miRNA-Exosome 路徑更多） |
| **視覺化路徑展示** | ✅ 圖形高亮 2-hop 路徑 | ❌ |

### 兩庫均應找到的核心 miRNA（高信心度候選）

| miRNA | ALF 相關 | SR-HCC 相關 | 備註 |
|---|---|---|---|
| **miR-21** | ✅ 抗凋亡 | ✅ 促抗藥性 | 兩疾病雙重角色，最可能共現 |
| **miR-122** | ✅ 肝細胞損傷標誌 | ✅ Sorafenib 敏感性 | 肝臟特異性高 |
| **miR-155** | ✅ 炎症調控 | ✅ 腫瘤微環境 | 炎症路徑共享 |
| **miR-223** | ✅ 肝保護 | ✅ 間接相關 | ALF 研究較多 |

### NetMedEx 較易遺漏的 miRNA（MRTKG 優勢）

| miRNA | SR-HCC 相關 | 可能遺漏原因 |
|---|---|---|
| miR-199a-3p | ✅ HIF-1α 抑制 | ALF+SR-HCC 未共現於同篇文章 |
| miR-375 | ✅ 抑制抗藥性 | 研究較新，PubTator3 標注率低 |
| miR-193a | ✅ 增敏 Sorafenib | 樣本數小的研究易被過濾 |
| miR-296-5p | ✅ Sorafenib 相關 | 稀有，需大型庫才能捕捉 |

---

## 八、互補使用建議

### 最佳工作流程

```
步驟 1：MRTKG（深度召回）
    ↓ 從 30,000 篇語意召回 ALF + SR-HCC 候選 miRNA（高召回率）
    ↓ 取得 Layer 2/3 豐富的間接路徑假說

步驟 2：NetMedEx（即時驗證 + 視覺化）
    ↓ 以候選 miRNA 為關鍵詞，查詢最新文獻（即時性）
    ↓ 視覺化 miRNA ↔ Exosome ↔ Compound 的多元關係圖
    ↓ 2-hop 路徑高亮，直接在圖上探索機制假說

步驟 3：兩系統結果取交集
    ↓ 高信心度核心 miRNA（如 miR-21、miR-122）
    ↓ 作為後續實驗優先驗證標的
```

### 各系統最適使用情境

| 情境 | 建議系統 |
|---|---|
| 全面 miRNA 文獻回顧 | MRTKG |
| 最新發表文獻納入 | NetMedEx |
| 跨疾病機制圖譜探索 | NetMedEx |
| 豐富的間接路徑假說 | MRTKG |
| 互動式圖譜可視化 | NetMedEx |
| miRNA ↔ Exosome 連結 | MRTKG（覆蓋更廣） |
| 罕見 miRNA 候選發現 | MRTKG |
| 即時驗證最新研究 | NetMedEx |

---

## 九、技術同源性總結

```
MRTKG 與 NetMedEx 相同之處：
━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ NER 共現建圖（PubTator3 同架構）
✅ PMID 邊級溯源（每條邊標注來源文獻）
✅ 2-hop 跨文件路徑推論
✅ 方向性邊偵測（[DIRECTIONAL] / [SYMMETRIC]）
✅ 混合評分（NPMI + 信心度 + 語意相關）
✅ Text RAG + Graphic RAG 雙軌架構
✅ LLM 五層式推論輸出

MRTKG 額外優勢：
━━━━━━━━━━━━━━━
→ 30,000 篇的圖密度（更多路徑、更豐富假說）
→ miRNA 領域深度覆蓋

NetMedEx 額外優勢：
━━━━━━━━━━━━━━━━━━
→ 即時 PubMed 查詢（最新文獻）
→ 互動式 Cytoscape 知識圖譜
→ 2-hop 路徑視覺高亮
→ 跨生醫領域（不限 miRNA）
```

---

*本文件由 NetMedEx + MRTKG 系統比較討論整理，日期：2026-05-29*
