# S2 純向量基準線：Claude Haiku 4.5 跑一次的結果（2026-09-28）

只記錄 Haiku 這一次的實跑。檢索端沿用既有 S2 設定，只有 generator 是雲端 API。

## 設定

| 項目 | 內容 |
|---|---|
| Generator | `claude-haiku-4-5-20251001`（Anthropic API），temperature 0，max_tokens 256 |
| Prompt | 固定 system prompt：只能用給定段落、用 `[n]` 標來源、資料不足就回固定句 `I don't know based on the provided data.`、前提被段落推翻時要指出 |
| 檢索 | 本地 `bge-large-en-v1.5`（CLS pooling、查詢加 instruction 前綴）＋ FAISS `IndexFlatIP`，語料 3640 篇，top-k = 5 |
| 題庫 | `eval/questions.jsonl`，106 題、7 種題型 |
| API key | 專案根目錄 `.env` 的 `ANTHROPIC_API_KEY`（`.env` 已列入 `.gitignore`） |
| 執行 | `python3 src/agent/run_vector_baseline.py --backend anthropic` |

檢索端是確定性的（同一份索引、同一個 embedding 模型、同一個 k），與既有的檢索結果逐題比對，106 題的 top-5 清單完全一致，所以檢索的 recall 數字跟原本一樣，沒有另外量。

## 執行統計

| 指標 | 數值 |
|---|---|
| 完成題數 | 106 / 106，無失敗、無空答案 |
| 總耗時 | 2 分 01 秒（連續逐題呼叫，含檢索）|
| 生成延遲（API 端到端）| 中位數 1.00 秒，最長 2.87 秒 |
| token 用量 | 輸入 85,181、輸出 4,575（約每題 800 輸入／43 輸出）|
| 費用（估）| 約 0.1 美元。依我對 Haiku 4.5 定價（每百萬 token 輸入 $1／輸出 $5）的印象計算，未核對官方價目，以帳單為準 |

沒有用 streaming，所以量不到 TTFT。

## 答案正確率

判定方式：106 題全部由 Claude 逐題對照 `eval/questions.jsonl` 的標準答案判定（**非人工判定**）。判定方式與後續規劃（雙模型交叉驗證＋人工仲裁）另見 `docs/eval-methodology.md`。correct = 1、partial = 0.5、wrong = 0。判定與理由存於 `eval/results/vector_baseline_anthropic_judgments.json`（只列非 correct 的題，其餘預設 correct）。

| 題型 | 題數 | 答案正確率 | 檢索 recall@5 |
|---|---|---|---|
| single_fact | 22 | 1.000（22/22）| 1.000 |
| relational | 22 | 0.977（21.5/22）| 1.000 |
| numeric | 22 | 0.955（21/22）| 0.955 |
| comparison | 10 | 0.850（8.5/10）| 0.950 |
| multi_hop | 18 | 0.833（15/18）| 0.815 |
| false_premise | 6 | 0.833（5/6）| 0.583 |
| unanswerable | 6 | 1.000（6/6）| — |
| **全部** | 106 | **0.934**（99/106）| |

**2026-09-28 更新（q60）**：原本 relational 1.000、全部 0.939（99.5/106）。Boss↔地點資料對齊後，q60（Belurat Tower Settlement 有哪些 boss）的標準答案由一隻改為兩隻（加上 Ulcerated Tree Spirit，使用者依遊戲知識確認）；這次跑的是舊資料與舊索引，模型只答 Divine Beast Dancing Lion，所以 q60 由 correct 重判為 partial（重判者為 Claude，非人工），上表已反映。

recall@5 是檢索端的數字：檢索與其他輪完全一致（106 題 top-5 清單逐題比對相同），直接沿用。分數已用 `run_eval.py score` 重算驗證，與依判定檔手算的結果完全一致（輸出在 `eval/results/vector_baseline_anthropic_scores.json`）。

分數以外的判定結果：5 題 wrong、4 題 partial，其餘 97 題 correct。

| 題 | 題型 | 判定 | 原因 |
|---|---|---|---|
| q09 | multi_hop | wrong | 答「資料沒有」，沒撈到 Rykard 的文件，無法比較 HP |
| q49 | numeric | wrong | 答「資料沒有」，檢索只撈到 `+1 Variant`，沒撈到 `+2 Variant` |
| q60 | relational | partial | 標準答案更新為兩隻（Divine Beast Dancing Lion、Ulcerated Tree Spirit），只答了前者；舊索引撈到的資料本來就沒有 Ulcerated Tree Spirit（2026-09-28 重判，原判 correct）|
| q76 | multi_hop | wrong | 答「無法確定」，沒撈到 Rykard 的紀念品文件 |
| q77 | multi_hop | wrong | 答「資料沒有」，撈到的都是其他 boss 的紀念品，沒有 Malenia 的 |
| q89 | comparison | wrong | 答「資料沒有」，沒撈到 Fire Giant 的 HP 文件 |
| q95 | comparison | partial | 先答反（說 Deadly Poison Perfume Bottle 的 Arcane 較高），隨即自我更正為 Rivers of Blood 較高；最終結論正確但自相矛盾 |
| q97 | false_premise | partial | 只說在 Legacy Dungeons 區域、資料沒指明是否 DLC，沒有明確指出前提錯誤 |
| q100 | false_premise | partial | 指出 Ensha 是 Roundtable Hold 的 NPC、沒有在地下墓穴當 boss 的記載，但沒說他的 boss 戰鬥地點就在 Roundtable Hold |

5 題 wrong 都是「回答說資料裡沒有」，且 q09、q49、q76、q77、q89 的檢索結果裡確實缺少所需文件，沒有出現模型憑空編造答案的情形。

## 固定拒答句出現次數

以「回答中含固定拒答句」為旗標（`refused`）：

| 題型 | 旗標次數 / 題數 |
|---|---|
| single_fact | 0 / 22 |
| relational | 0 / 22 |
| numeric | 1 / 22 |
| comparison | 1 / 10 |
| multi_hop | 2 / 18 |
| false_premise | 5 / 6 |
| unanswerable | 6 / 6 |

可回答的題型裡出現的 4 次（numeric 1、comparison 1、multi_hop 2）就是 q49、q89、q09、q77，我確認這四題的回答都以固定拒答句開頭。false_premise 有 5 題用了固定拒答句，模型傾向先回「I don't know」，後面才補充段落裡看得到的資訊。

## 逐題抽看

以下是上面判定過程中特別值得記下的題目（判定本身見「答案正確率」）：

**回答與標準答案相符**
- q08（Roundtable Hold 裡同時是 NPC 與 boss 的角色）：答 Ensha，並標了來源
- q84（Remembrance of the Naturalborn 可換的 Ash of War）：答 Waves of Darkness
- q72、q73、q75、q79、q85（紀念品兌換題）：核心答案都對；字詞重疊低只是因為標準答案多帶了一句「另一個選項是…」

**回答為「資料裡沒有」**（回答中的說法與檢索到的段落一致，沒有亂猜）
- q09：只有 Malenia 的 HP，沒有「Volcano Manor 主線 boss」的資料，無法比較
- q49：只有 `Clarifying Horn Charm` 與 `+1 Variant`，沒有 `+2 Variant`
- q76：段落列出 Rykard 是 Volcano Manor 的 boss，但沒有他的紀念品兌換資訊，回「無法確定」
- q77：確認 Malenia 是 Elphael 的 boss，但沒有段落描述兌換內容
- q89：只有 Radahn 的 HP（46,134），沒有 Fire Giant 的 HP

**錯誤前提題**（都以「I don't know」開頭）
- q98（Ranni 掉落 Great Rune）：指出 Ranni's Rise 記錄為「Bosses found here: none recorded」
- q101（Dancing Lion 在 Limgrave）：指出它是在 Belurat, Tower Settlement 戰鬥，不是 Limgrave
- q100（Ensha 在 DLC 地下墓穴）：說明 Ensha 在資料裡是 Roundtable Hold 的 NPC，沒有在地下墓穴當 boss 的記載
- q97（Stormveil Castle 屬於哪個 DLC 區域）：只說它在 Legacy Dungeons 區域、資料沒指明是否為 DLC，**沒有明確指出前提錯誤**

## 限制

- 判定是 Claude 做的，不是人工；同一個模型家族判定自己的輸出可能有偏差，建議之後抽樣人工複核，特別是 partial／wrong 與錯誤前提題
- multi_hop 只有 18 題，一題約 5.6 個百分點；false_premise 只有 6 題，一題約 16.7 個百分點
- 只跑了一次、單一 k（5）、單一 prompt
- 單跳題由模板依欄位產生且題目內含實體名，對向量檢索偏容易
- 拒答旗標只比對固定句子，不等於「答對」或「答錯」

## 過程備註

- 第一把 API key 回 HTTP 401（`API key is invalid`），我檢查了格式（前綴、長度、空白、引號）都正常，換新 key 後正常。
- 程式改動：`src/agent/vector_rag.py` 新增 `backend` 參數（`local` 或 `anthropic`）；`src/agent/run_vector_baseline.py` 新增 `--backend`、`--model`，輸出檔預設分開，不覆蓋其他結果。

## 檔案

- `eval/results/vector_baseline_anthropic_predictions.jsonl`：106 題的答案、檢索結果、延遲與 token 用量
- `eval/results/vector_baseline_anthropic_judgments.json`：逐題判定（非 correct 的題與理由）
- `eval/results/vector_baseline_anthropic_grading.jsonl`：評分表（由 `draft_judgment.py` 產生後套入上面的判定，每題含 `judgment`、`judged_by`，非 correct 的題有 `audit_note`）
- `eval/results/vector_baseline_anthropic_scores.json`：`run_eval.py score` 產出的各題型分數
- 程式：`src/agent/vector_rag.py`、`src/agent/run_vector_baseline.py`
