# S5：讓 LLM 自己挑工具（向量搜尋／圖查詢）

狀態：**已對真實模型跑完全部 106 題 × 3 組（A／B／C）並判分**（2026-09-30）。79 個單元測試全過；B、C 兩組各跑滿 106 題（分批、溫度監控，避免筆電過熱關機，見下）；A 組用重建後的向量索引（3649 篇）重跑。三組的分數與具體發現見下方「已驗證的結果」。

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
| `scripts/run_agent_paced.sh` | 分批跑 106 題（預設每批 10 題、每輪目標 300 秒），批次間監控 GPU／CPU 溫度，沒降到安全值以下就多等，避免這台筆電（ASUS，ACPI 熱管理有 bug，過熱時似乎直接硬斷電、不留 log）長時間高負載跑到過熱關機 |

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

## 怎麼跑

```
bash scripts/start_llama_servers.sh start                        # 啟動 embedding（8801）與生成（8802），等到兩個就緒
python3 src/vector/build_index.py                                 # 重建向量索引（語料庫 3649 篇）
python3 -m pytest tests -q                                        # 單元測試
bash scripts/run_agent_paced.sh graph 10 300                      # B 組，分批、溫度監控
bash scripts/run_agent_paced.sh all   10 300                      # C 組
python3 src/agent/run_vector_baseline.py --backend anthropic      # A 組（Haiku，本地只需 embedding，發熱量小）
```

`run_agent.py` 結束時會印：題數、伺服器錯誤數、沒呼叫任何工具就回答的題數、工具呼叫出錯次數、被強制回答的題數、各工具的使用次數、各題型第一個呼叫的工具。

## 已驗證的結果（2026-09-30，106 題 × 3 組，AI 判定、非人工）

**計畫書列的最大風險——4B 模型工具呼叫穩不穩——基本上不成立。** 106 題 × 2 個 agent 模式全程 0 個伺服器錯誤、0 題完全不呼叫工具、0 個空答案；`llama.cpp`（commit `a97cce8`，`--jinja`）能正確解析 Qwen3.5-4B 的工具呼叫，甚至會在一輪裡同時發兩個並行呼叫（例如比較題一次查兩個實體）。`Qwen3.5-9B` 的退路沒有用上。

**分數**（`correct`=1、`partial`=0.5、`wrong`=0；判定為 AI 逐題對照標準答案，非人工，方法論見 `docs/eval-methodology.md`）：

| 題型 | 題數 | A 純向量 | B 純圖 | C 向量+圖 |
|---|---|---|---|---|
| single_fact | 22 | 1.000 | 0.955 | 0.955 |
| numeric | 22 | 0.955 | 1.000 | 1.000 |
| relational | 22 | 1.000 | 1.000 | 1.000 |
| multi_hop | 18 | 0.833 | 1.000 | 1.000 |
| comparison | 10 | 0.900 | 1.000 | 0.900 |
| false_premise | 6 | 0.833 | 0.167 | 0.333 |
| unanswerable | 6 | 1.000 | 1.000 | 1.000 |
| **整體** | 106 | 0.943 | 0.943 | 0.943 |

三組整體正確率巧合地完全相同（都是 100/106），但分題型看故事不同：

- **multi_hop 圖明顯贏**：A 組在 q09、q76、q77、q89 這類需要跨檔案關聯的題上撈不到文件（向量檢索的固有弱點），B／C 用 `get_neighbors`／`get_entity` 直接按關係查，全對。
- **false_premise 圖明顯輸**：A 組 0.833 vs B 0.167／C 0.333，而且 A 組這個題型的 retrieval recall@5 只有 0.583（比 B／C 的 0.75 還低）卻答得比較對。原因：向量檢索撈不到確認矛盾的文件時，模型傾向老實拒答，剛好貼近「這題本來就有問題」；圖工具反而查到了正確的關係資料（例如 q101 明明查到 Divine Beast Dancing Lion 實際在 Ancient Ruins of Rauh），卻只顧著回答查到的東西，沒有回頭比對題目宣稱的前提。**檢索能力強不代表推理能力強，這個題型把兩者的落差暴露出來了。**

**其他發現**：
- **`fields=['properties']` 參數誤用**（q86）：`properties` 不是真正的屬性名稱，只是包裝鍵；模型誤以為指定 `fields=['properties']` 能拿到完整屬性，結果每次都查到空值。兩個模式都在 q86 踩到，C 組因此答錯（沒找到 Godrick 紀念品的符文值），B 組運氣好在更早的呼叫已經拿到數字。
- **同名多重身分題會繞路**（q08、q100、q98）：Ensha、Ranni 這類同時是 NPC 又（可能）是 Boss 的名字，模型會嘗試多種 `label` 組合甚至虛構名稱變體（例如 "Ranni, the Witch of the Deep"），撞到 `tool_error` 才修正，但最終結論通常還是對的，只是多花 2-4 次呼叫。
- **q14 資料誤讀**：`damage_type` 欄位是 `Slash`，模型從 `description` 風味文字的「deals fire damage」誤判成傷害類型，兩個模式都錯。這是模型讀錯欄位，不是圖或檢索的問題。
- **延遲**：B 組中位數 1.97 秒／最長 12.64 秒；C 組中位數 2.25 秒／最長 13.32 秒（都含多輪工具呼叫）。A 組（S2 單次檢索＋生成）中位數約 1 秒量級，agent 因為多輪呼叫明顯更慢。

## `--no-hint` 對照結果（2026-10-01）

拿掉「問題中偵測到的實體」提示，同樣 106 題重跑 B、C 兩個模式。

| | B（有提示）| B（無提示）| C（有提示）| C（無提示）|
|---|---|---|---|---|
| 整體 | 0.943（100/106）| **0.915**（97/106）| 0.943（100/106）| **0.934**（99/106）|
| multi_hop | 1.000 | 0.944 | 1.000 | 0.889 |
| relational | 1.000 | 0.909 | 1.000 | 1.000 |
| false_premise | 0.167 | 0.333 | 0.333 | **0.750** |

**提示對 B（只有圖工具）的影響比 C（多一個 `vector_search` 當備援）大**：B 掉 2.8 個百分點，C 只掉 0.9 個百分點。

**最乾淨的證據——q08（Ensha）**：兩個模式、有提示都答對、沒提示都答錯，是唯一一題四個條件裡呈現完美對照的。沒提示時兩個模式都直接斷定「沒有角色同時是 NPC 又是 boss」，沒有像有提示時那樣順利找到 Ensha。

**其他變化**：q06、q60、q86 在 B 模式沒提示時答錯（有提示時對），但 q60 在 C 模式沒提示時還是對（`vector_search` 接住了）；q04、q74 是沒提示才冒出來的新錯誤，只在 C 模式出現（q04 答出 66,505 而非標準答案 33,251，疑似查到 `bs_health_total` 這個分階段加總的欄位，不是 `bosses.csv` 的單一 HP 值）。

**意外發現，還沒有確定的解釋**：C 模式的 false_premise 沒提示反而從 0.333 進步到 0.750。可能的解釋是有提示時模型太信任提示給的實體身分、直接查資料沒有花力氣核對周邊矛盾，沒提示時得自己多方嘗試（例如同時查 NPC 和 Boss 標籤）反而意外撞見矛盾線索——但這只是推測。這跟 `docs/eval-methodology.md` 討論過的「LLM 生成本身也有變動性，不只是判官」是同一類警訊，單次跑的差異不能直接當成提示本身造成的因果，要多次重跑才能確認是穩定效應還是噪音。

**結論**：提示確實有真實、可量測的貢獻（尤其對純圖模式），C 組（S6 的主角）相對 A 組的優勢裡有一部分要歸因於這個提示，不是完全是圖本身。這點在 S6 報告裡要講清楚，不能把提示的功勞算在圖頭上。

## 還沒做

- **`fields=['properties']` 誤用、false premise 弱、同名實體繞路**——這三個行為毛病要不要修（改工具描述／system prompt），還是就當作 S6 的失敗案例記錄，待決定。
- 依這輪發現調整 prompt／工具描述、重跑，看分數會不會變；如果要確認「false_premise 沒提示反而變好」是不是穩定效應，需要多次重跑取平均，不是只跑一次。
- commit、打 `s5` tag。
