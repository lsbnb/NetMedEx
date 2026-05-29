# NetMedEx Token 消耗與費用估算

> 以 **30 篇文章、1 次 Chat 回應** 為基準場景進行估算。
> Token 費率參考截至 2026-05 各平台公告價格。

---

## 一、各處理階段 Token 明細

| 階段 | 觸發條件 | 輸入 Token | 輸出 Token | 小計 |
|------|---------|-----------|-----------|------|
| **① 語言偵測** | 永遠 | 0（程式碼判斷）| 0 | 0 |
| **② 中文翻譯** (`translate_to_english`) | 非英文查詢 | 138（提示）+ ~30（查詢）≈ **168** | ~30 | ~200 |
| **③ Boolean 查詢轉換** (`translate_query_to_boolean`) | AI Search 開啟 | 920（提示）+ ~40（查詢）≈ **960** | ~40 | ~1,000 |
| **④ PubTator API 搜尋** | 永遠 | 0（API 呼叫，非 LLM）| 0 | 0 |
| **⑤ Semantic 邊分析 × 30 篇** | Semantic 邊模式 | (726 + 450) × 30 ≈ **35,280** | ~300 × 30 = **9,000** | ~44,280 |
| **⑥ KG Normalization** | 需 embedding 支援 | embedding 模型（非 chat token）| — | 另計 |
| **⑦ Chat RAG 回應**（含 8 篇 context） | 每次對話 | 3,486（系統提示）+ ~3,000（context）+ ~50（查詢）≈ **6,536** | 3,000–**8,192** | ~10,000–15,000 |
| **⑧ 追問 (follow-up)** | 每次追問 | ~4,000–5,000 | ~3,000–6,000 | ~7,000–11,000 |

---

## 二、完整流程總消耗（依使用場景）

| 場景 | 輸入合計 | 輸出合計 | **總計** |
|------|---------|---------|---------|
| 英文查詢 + Semantic 邊 + 1 次 Chat | ~42,000 | ~12,000 | **~54,000** |
| 中文查詢 + AI Search + Semantic 邊 + 1 次 Chat | ~43,000 | ~12,000 | **~55,000** |
| 英文查詢 + **一般邊**（無 Semantic）+ 1 次 Chat | ~6,700 | ~3,100 | **~9,800** |
| 英文查詢 + Semantic 邊 + 1 次 Chat + 3 次追問 | ~69,000 | ~24,000 | **~93,000** |

> **Semantic 邊分析佔總 Token 的 80% 以上**，是最大費用來源。
> 若改用一般共現邊（Co-occurrence），費用可降低約 82%。

---

## 三、各模型費用估算

### 場景：完整流程（含 Semantic 邊）≈ 55,000 tokens（輸入 43,000 + 輸出 12,000）

| Provider | 模型 | 輸入費 /1M | 輸出費 /1M | 單次估算費用 | Chat max_tokens |
|---------|------|----------|----------|------------|----------------|
| **OpenAI** | gpt-4o | $2.50 | $10.00 | **~$0.23** | 6,000 |
| **OpenAI** | gpt-4o-mini | $0.15 | $0.60 | **~$0.013** | 8,000 |
| **Anthropic** | claude-sonnet-4-6 | $3.00 | $15.00 | **~$0.31** | 8,192 |
| **Anthropic** | claude-opus-4-8 | $15.00 | $75.00 | **~$1.55** | 8,192 |
| **Google** | gemini-1.5-pro | $1.25 | $5.00 | **~$0.11** | 6,000 |
| **Google** | gemini-1.5-flash | $0.075 | $0.30 | **~$0.007** | 6,000 |
| **Groq** | llama-3.3-70b-versatile | $0.59 | $0.79 | **~$0.035** | 8,000 |
| **Groq** | llama-3.1-8b-instant | $0.05 | $0.08 | **~$0.003** | 8,000 |
| **OpenRouter** | deepseek-v3 | $0.27 | $1.10 | **~$0.025** | 6,000 |
| **Local / Ollama** | llama3 / qwen 等 | $0 | $0 | **$0**（電費）| 8,000 |

### 場景：輕量模式（無 Semantic 邊）≈ 9,800 tokens（輸入 6,700 + 輸出 3,100）

| Provider | 模型 | 單次估算費用 |
|---------|------|------------|
| **OpenAI** | gpt-4o | **~$0.048** |
| **OpenAI** | gpt-4o-mini | **~$0.003** |
| **Anthropic** | claude-opus-4-8 | **~$0.33** |
| **Google** | gemini-1.5-pro | **~$0.024** |
| **Groq** | llama-3.3-70b | **~$0.006** |

---

## 四、Chat 回應 max_tokens 設定（現行）

| Provider | Bootstrap（初始摘要）| 主要對話 | 備註 |
|---------|---------------------|---------|------|
| **Anthropic** | 8,192 | 8,192 | Claude 標準輸出上限 |
| **Groq / Local** | 5,000 | 8,000 | 低費用，預算較寬 |
| **OpenAI gpt-4o-mini** | 5,000 | 8,000 | 費用低，值得放寬 |
| **其他（gpt-4o、Gemini、OpenRouter、NVIDIA）** | 4,000 | 6,000 | 平衡品質與費用 |

---

## 五、KG Normalization Embedding 費用（另計）

| Provider | Embedding 模型 | 費用 /1M tokens | 支援 KG Normalization |
|---------|--------------|----------------|----------------------|
| **OpenAI** | text-embedding-3-small | $0.02 | ✅ |
| **Google Gemini** | text-embedding-004 | $0.025 | ✅ |
| **NVIDIA NIM** | nv-embed-qa-4 | ~$0.02 | ✅（需 NIM 伺服器）|
| **Local / Ollama** | nomic-embed-text | $0 | ✅（需載入模型）|
| **Groq** | 不支援 | — | ❌ |
| **OpenRouter** | 不支援 | — | ❌ |
| **Anthropic** | 不支援 | — | ❌ |

> KG Normalization 每次約使用 2,000–5,000 embedding tokens（節點名稱正規化），費用極低（< $0.001）。

---

## 六、費用優化建議

1. **使用一般邊（Co-occurrence）替代 Semantic 邊**：費用降低 ~82%，適合探索性查詢
2. **首選 gpt-4o-mini 或 gemini-1.5-flash**：費用不到 gpt-4o 的 5%，品質適合多數應用
3. **Local / Ollama**：無 API 費用，適合高頻使用，需自備 GPU
4. **Groq llama-3.3-70b**：速度快、費用低，適合 Semantic 邊批次分析
5. **claude-opus-4-8**：推理能力最強，但費用最高；建議僅在需要最高品質時使用
