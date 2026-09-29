# S5：讓 LLM 自己挑工具（向量搜尋／圖查詢）

狀態：**程式與單元測試已寫好，尚未執行**（2026-09-29）。沒有啟動過 llama 服務，沒有對真實的 LLM 跑過任何一題，單元測試也還沒跑。下面「還沒驗證的事」是實跑時要看的重點。

## 目的

計畫書 S5：一個入口，讓 LLM 自己決定用向量搜尋、圖查詢，或兩者並用；回答時標註資訊來自哪個工具、哪個實體；記錄每題實際呼叫了哪些工具，用來分析工具選擇是否合理。完成標準：能端到端回答題庫所有題目，並有每題的工具呼叫紀錄。

## 檔案

| 檔案 | 內容 |
|---|---|
| `src/agent/graph_rag.py` | 工具定義（給 LLM 的 JSON schema）、工具結果壓縮、實體提示、LLM 呼叫、`Agent` 迴圈 |
| `src/agent/run_agent.py` | 對題庫跑 agent、存預測檔、印工具使用彙總 |
| `tests/test_agent.py` | 單元測試，用假的 LLM 與假的工具，不需要模型、Neo4j、向量索引 |
| `scripts/start_llama_servers.sh` | 啟動 embedding（8801）與生成（8802）兩個 llama-server |
| `src/graph/tools.py` | 新增 `GraphTools.source_of(uid)`，回報節點來源（檔案＋列號），agent 用它記錄檢索到哪些來源 |

## 兩種模式，共用同一個迴圈

計畫書規定 S6 的 A／B／C 三組必須用同一個 generator（Qwen3.5-4B），這樣分數差異才能歸因於檢索方式。

| 設定 | 怎麼跑 | 工具 |
|---|---|---|
| A 純向量 | `src/agent/run_vector_baseline.py`（S2，沒有變）| 無（固定先檢索再生成）|
| B 只用圖 | `run_agent.py --mode graph` | `get_entity`、`get_neighbors`、`find_path`、`filter_by_attribute` |
| C 向量＋圖 | `run_agent.py --mode all` | 上面四個＋`vector_search` |

## 迴圈

1. 對問題跑 `GraphTools.link_entities`，把偵測到的實體名稱與標籤當提示接在使用者訊息後面（見下）。
2. 把 system prompt、使用者訊息、工具定義送給 llama-server（`/v1/chat/completions`，temperature 0，thinking 關閉，`tool_choice=auto`）。
3. 模型回傳工具呼叫 → 執行 → 結果（壓縮後）以 `tool` 訊息回給模型 → 再問一次。模型不再呼叫工具時，它的文字就是答案。
4. 最多 6 輪工具呼叫；用完還在呼叫就不給工具、要求它用手上的結果回答（`forced_final`）。
5. 工具參數不是合法 JSON、工具名稱不存在、參數名稱錯、或工具回傳 `{"error": ...}` 時，錯誤文字回給模型讓它修正，紀錄裡標出來，不會讓整題失敗。

## 幾個設計決定

- **實體連結是前處理，不是工具**：確定性的步驟，不需要模型判斷，也讓 4B 模型少一個工具可選。**代價**：C 組（以及 `--mode graph`）比 A 組多了這個提示。這是「圖增強」的一部分，S6 的比較要寫明；`--no-hint` 可以關掉，用來看提示本身貢獻多少。
- **工具結果壓縮後才給 LLM**：截斷長文字（240 字元）、限制單次結果 6000 字元與 40 個鄰居、把同一對節點之間的平行邊合成一筆（S3 留下的「同一個鄰居列兩次」在這一層解掉，不必動圖）、`at_location` 合併成清單、丟掉內部欄位（`merged_from`、`item_types`）。來源不放進給 LLM 的結果，另外記在紀錄裡。
- **數字字串容忍**：`filter_by_attribute` 的數值運算子（`<`、`<=`、`>`、`>=`）如果模型把數字當字串傳（`"12"`），agent 這一層先轉成數字；`GraphTools` 本身仍然嚴格檢查。
- **system prompt**：規則是只用工具結果、列出所有找到的項目、資料沒有就回固定拒答句 `I don't know based on the provided data.`（與 S2 相同，unanswerable 題靠它判斷）、前提被資料推翻要指出、一到兩句。prompt 裡也提到「有些物品合併了同一物品的多個狀態，其他狀態在 `merged_variants`」。

## 預測檔格式

沿用 S2（可直接餵給 `eval/run_eval.py init`），多了：

| 欄位 | 內容 |
|---|---|
| `tool_calls` | 每次呼叫一筆：`step`、`tool`、`args`、`error`（null 或錯誤字串）、`seconds`、`result_chars` |
| `forced_final` | 是否用完步數被強制回答 |
| `linked` | 問題中偵測到的實體名稱 |
| `retrieved_sources` | 所有工具結果裡出現的實體的來源（檔案＋列號），供算 recall@k |
| `latency` | `total_s`、`llm_s`、`tool_calls`（呼叫次數）|
| `error` | 只有伺服器錯誤時出現（例如 context 超過），該題答案為空，不影響其他題 |

## 怎麼跑（尚未執行過；需要依序）

```
bash scripts/start_llama_servers.sh start                        # 啟動 embedding（8801）與生成（8802），等到兩個就緒
python3 src/vector/build_index.py                                 # 重建向量索引（語料庫 3649 篇，現有索引是舊的 3640 篇）
python3 -m pytest tests -q                                        # 單元測試（test_agent.py 不需要服務；test_graph_tools.py 需要 Neo4j）
python3 src/agent/run_agent.py --mode all --sample-per-type 2     # 小規模試跑：每個題型前 2 題（14 題），存到 *_smoke_predictions.jsonl
python3 src/agent/run_agent.py --mode all                         # 全部 106 題（C 組）
python3 src/agent/run_agent.py --mode graph                       # 只用圖（B 組）
```

`run_agent.py` 結束時會印：題數、伺服器錯誤數、沒呼叫任何工具就回答的題數、工具呼叫出錯次數、被強制回答的題數、各工具的使用次數、各題型第一個呼叫的工具。

## 還沒驗證的事（實跑時要看）

計畫書把這列為 S5 的風險：**4B 模型的工具呼叫穩定度**，不穩的話退路是換 `Qwen3.5-9B`（與 bge 同放 8GB VRAM 很緊，要先把問題向量算好、關掉 bge 再跑）。具體要看：

1. **llama.cpp 能不能正確解析 Qwen3.5 的工具呼叫**：需要 `--jinja`（腳本有帶）；我不確定這個版本（commit `a97cce8`）的模板對 `tools` 與 `tool_choice` 的支援，沒有實測。
2. **模型會不會呼叫工具**：小模型可能不呼叫就直接回答（紀錄裡是 `沒呼叫任何工具就回答`），或參數亂填、重複呼叫同一個工具。
3. **選對工具的比例**：例如「某地點有哪些 boss」是不是用 `get_neighbors(relation=LOCATED_AT, direction=in, target_label=Boss)`，方向與參數常是小模型會弄錯的地方。
4. **context 夠不夠**：生成端從 S2 的 4096 改成 8192（`GEN_CTX` 可調）；system prompt、五個工具的 schema、幾次工具結果加起來會佔多少，我只估過沒量過。超過時該題會記成伺服器錯誤。
5. **`value` 欄位的 schema 我沒有寫型別**（怕型別陣列在 llama.cpp 轉成文法時出問題），實際是否影響工具呼叫的格式要看。
6. **提示對結果的影響**：`--no-hint` 對照能看出實體提示貢獻多少。
7. **延遲**：每題多輪呼叫，S2 單題約 1.5 秒；agent 會多好幾倍，S6 若要報延遲要另外量。

## 還沒做

- 任何真實執行、判分與分析（S6 的內容）。
- 依試跑結果調整 prompt、工具描述、壓縮方式。
- `Qwen3.5-9B` 的退路只是計畫，沒有準備。
- 向量基準線（A 組）在 S6 前要用重建後的索引重跑；現有的 A 組結果是舊索引、舊資料。
