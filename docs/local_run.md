# S2 純向量基準線：本地跑一次的結果（2026-09-28）

只記錄這一次的實跑結果。全部在本機，沒有呼叫任何雲端 API。

## 設定

| 項目 | 內容 |
|---|---|
| 硬體 | RTX 3070 Laptop，8GB VRAM |
| 推論引擎 | llama.cpp（commit `a97cce8`），CUDA，只編 sm_86 |
| Embedding | `bge-large-en-v1.5` F16 GGUF，CLS pooling，1024 維；查詢端加 BGE 建議的 instruction 前綴 |
| 語料 | `data/processed/corpus.jsonl`，3640 篇（一個實體一篇），其中 1 篇超過 512 token 被截斷 |
| 向量索引 | FAISS `IndexFlatIP`（L2 正規化，等同 cosine），top-k = 5 |
| Generator | `Qwen3.5-4B` Q8_0 GGUF，`llama-server -c 4096 -np 1 --jinja`，temperature 0，max_tokens 256，thinking 關閉 |
| Prompt | 固定 system prompt 放最前面：只能用給定段落、用 `[n]` 標來源、資料不足就回固定句、前提被段落推翻時要指出 |
| 題庫 | `eval/questions.jsonl`，106 題、7 種題型 |
| 資源 | 兩個 server（embedding + generation）合計約 5.5GB VRAM |

建索引：3640 篇在 GPU 上約 20 秒。

## 結果

答案正確率：correct = 1、partial = 0.5、wrong = 0。檢索 recall@5：標準來源被撈進前 5 篇的比例。

| 題型 | 題數 | 答案正確率（原判定） | 稽核修正後 | 檢索 recall@5 |
|---|---|---|---|---|
| single_fact | 22 | 1.000 | 1.000 | 1.000 |
| relational | 22 | 1.000 | **0.977** | 1.000 |
| numeric | 22 | 0.955 | 0.955 | 0.955 |
| comparison | 10 | 0.900 | 0.900 | 0.950 |
| false_premise | 6 | 0.833 | 0.833 | 0.583 |
| multi_hop | 18 | 0.778 | **0.722** | 0.815 |
| unanswerable | 6 | 1.000 | 1.000 | — |
| **全部** | 106 | 0.934 | **0.920** | |

「稽核修正後」是把 q08 由 correct 改為 wrong 的結果，**已寫回**評分檔並重跑 `run_eval.py score`（`vector_baseline_scores.json` 現在就是這一欄的數字；「原判定」欄是修正前的數字，見下方「判定的可信度」）。

**2026-09-28 補記（q60）**：Boss↔地點資料對齊後，q60（Belurat Tower Settlement 有哪些 boss）的標準答案由一隻改為兩隻（加上 Ulcerated Tree Spirit，使用者依遊戲知識確認）。本次跑的是舊資料與舊索引，模型只答 Divine Beast Dancing Lion，因此 q60 由 correct 重判為 partial（重判者為 Claude，非人工）。這個變動只反映在「稽核修正後」欄（relational 1.000 → 0.977、全部 0.925 → 0.920）；「原判定」欄保留為歷史數字，未追溯更動，所以兩欄之間 relational 的差異來自 q60，不是稽核。

只看檢索的 recall@k（`eval/retrieval_only.py`，top-10）：

| 題型 | R@1 | R@3 | R@5 | R@10 |
|---|---|---|---|---|
| single_fact | 0.955 | 1.000 | 1.000 | 1.000 |
| relational | 1.000 | 1.000 | 1.000 | 1.000 |
| numeric | 0.909 | 0.955 | 0.955 | 1.000 |
| comparison | 0.500 | 0.800 | 0.950 | 1.000 |
| multi_hop | 0.481 | 0.731 | 0.815 | 0.861 |
| false_premise | 0.250 | 0.500 | 0.583 | 0.667 |

## 延遲

| 指標 | 數值 |
|---|---|
| 生成端到端 | 中位數 1.51 秒，最長 11.09 秒 |
| prefill（prompt 處理）| 中位數約 405 ms |
| prompt 長度 | 中位數 574 token |

沒有做 streaming，所以量不到嚴格的 TTFT；prefill 時間可視為 TTFT 的主要部分。

## 答錯的題

原評分檔中 6 題 wrong、2 題 partial（另加 q60 重判的 1 題 partial，見表末）：

| 題 | 題型 | 現象 |
|---|---|---|
| q09 | multi_hop | 沒撈到「Volcano Manor 主線 boss」（Rykard）的文件，答資料沒有 HP |
| q76 | multi_hop | 撈到 Volcano Manor 地點與 Fire Giant 的紀念品，沒撈到 Rykard 的紀念品文件 |
| q77 | multi_hop | 答「資料沒說紀念品能換武器」，未查檢索結果，原因待查 |
| q84 | multi_hop | 答「資料沒說是哪個 Ash of War」，未查檢索結果，原因待查 |
| q49 | numeric | 撈到 `+1 Variant`、沒撈到 `+2 Variant`（名稱相近的物品互相干擾）|
| q89 | comparison | 沒撈到 Fire Giant 的文件，只能講 Radahn 的 HP |
| q97 | false_premise | partial：答了 Legacy Dungeons 區域，但沒明確指出「Stormveil Castle 不是 DLC」|
| q100 | false_premise | partial：指出 Ensha 是 NPC 不是 boss，但沒說到 Roundtable Hold |
| q60 | relational | partial（2026-09-28 重判）：標準答案更新為兩隻，模型只答 Dancing Lion 並說「the only boss」；舊索引撈到的資料本來就沒有 Ulcerated Tree Spirit |

觀察：
- 多跳題的錯誤多半出在「題目沒直接寫出關鍵實體」（例如「某地點的 boss」），撈到地點文件卻沒撈到 boss 文件。q77、q84 沒逐一驗證是否同因
- q49、q89 是命名實體本身沒撈到
- false_premise 的 recall 只有 0.583，但答對率 0.833：多半是模型以「資料沒提到」拒答避開陷阱，不是因為撈對了資料
- 數值題不弱：題目是模板產生、直接寫實體名，語料每個實體一篇且含數值

## 判定的可信度

- 評分檔 `vector_baseline_grading.jsonl`、`vector_baseline_scores.json` 不是這條對話產生的，而是同一個 session 被兩個終端機同時 resume 時，另一個 Claude Code 行程產生的（14:03:49）。做法是 `eval/draft_judgment.py` 用字詞重疊自動初判，再由該行程自行複查被標記的題。**沒有人工判定**
- 我重新稽核了 multi_hop、comparison、false_premise、unanswerable 全部題目與其餘題型的低重疊題，判定大致正確，但：
  - **q08 判錯**：標準答案是 Ensha，模型答「沒有人同時是 NPC 和 boss」，卻被判 correct，應為 wrong。**已改為 wrong**（評分檔該題加 `audit_note`）並重跑 score
  - q101（錯誤前提）偏鬆，比照 q97、q100 應為 partial，屬邊界
- unanswerable 的拒答：`vector_rag.py` 的 `refused` 旗標只比對固定句子，跑完當下只標到 3/6；6 題實際上都拒答，`scores.json` 記為 6/6（該檔由另一行程產生）

## 限制

- 判定非人工；multi_hop 只有 18 題，一題約 5.6 個百分點
- 單跳題由模板依欄位產生且含實體名，對向量檢索偏容易
- 只跑了一次、單一 generator（Qwen3.5-4B）、單一 k（5），沒有重複實驗

## 檔案

- `eval/results/vector_baseline_predictions.jsonl`：106 題原始答案、檢索結果、延遲
- `eval/results/retrieval_only_predictions.jsonl`：只看檢索的 top-10 結果
- `eval/results/vector_baseline_grading.jsonl`：評分表（含 `judgment`、`needs_review`、`draft_note`）
- `eval/results/vector_baseline_scores.json`：各題型彙總
- 程式：`src/ingest/build_corpus.py`、`src/vector/{embed_client,build_index,search}.py`、`src/agent/{vector_rag,run_vector_baseline}.py`、`eval/{retrieval_only,run_eval,draft_judgment}.py`
