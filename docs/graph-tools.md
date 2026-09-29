# 圖檢索工具（S4）

狀態：**已實作並測試**（2026-09-28）。程式 `src/graph/tools.py`，單元測試 `tests/test_graph_tools.py`（58 個），題庫檢查 `eval/graph_tools_check.py`。給 S5 的 LLM 呼叫；目前還沒有給 LLM 用的 JSON schema（S5 才做）。

需要 Neo4j 在跑且已建圖（`python3 src/graph/build_graph.py`）。連線資訊從 `.env` 讀。

```python
from tools import GraphTools          # src/graph/tools.py
with GraphTools() as t:
    t.get_neighbors("Volcano Manor", relation="LOCATED_AT", direction="in", target_label="Boss")
```

命令列手動試用：`python3 src/graph/tools.py get_entity '{"name": "Rykard"}'`

## 工具

所有工具回傳可 JSON 序列化的 dict。輸入有問題時回傳 `{"error": "..."}` 而不是拋例外，好讓 LLM 能修正呼叫。整數值的 float 會轉成 int（`89613.0` → `89613`）。

| 工具 | 參數 | 回傳重點 |
|---|---|---|
| `get_entity` | `name`（或 uid）、`label?`、`fields?` | 所有候選實體；每個有 `properties`、`source`（檔案＋列號）；Boss 的 `bs_*` 數值另放 `boss_stats`（去掉前綴）；`fields` 可只取指定屬性 |
| `get_neighbors` | `name`、`relation?`、`direction?`（in／out／both）、`target_label?`、`label?`、`limit?` | 每個候選實體各一組結果；每個鄰居帶關係、方向、實體摘要、邊上的屬性（`sources`、`at_location`、`runes`、`note`、`source_file`…）；`total` 與 `truncated` 告知是否被截斷 |
| `find_path` | `a`、`b`、`max_hops?`（1～6）、`max_paths?`、`relations?`、`label_a?`、`label_b?` | 最短路徑（不看邊的方向），每條含節點與邊；找不到時 `paths` 為空並附說明 |
| `filter_by_attribute` | `label`、`conditions`、`order_by?`、`descending?`、`limit?`、`fields?`、`include_stubs?` | 符合條件的實體與所要求欄位的值、`total`、`truncated` |
| `link_entities` | `text`、`min_len?`（預設 5） | 問句中出現的已知實體，依出現順序，每個帶候選節點（精確的排前面）|

**關係**：`LOCATED_AT`、`DROPS`、`LOCATED_IN`、`EXCHANGES_FOR`、`HAS_SKILL`、`GRANTS`（方向與端點標籤見 `docs/graph-schema.md`）。

**常用查詢寫法**

| 問題 | 呼叫 |
|---|---|
| 某地點有哪些 Boss／NPC | `get_neighbors(地點, relation="LOCATED_AT", direction="in", target_label="Boss"／"NPC")` |
| 某 Boss 掉落什麼 | `get_neighbors(Boss, relation="DROPS", direction="out")` |
| 某紀念品可以換什麼 | `get_neighbors(紀念品 uid, relation="EXCHANGES_FOR", direction="out")` |
| 某 Boss 的 HP | `get_entity(Boss, label="Boss", fields=["hp"])` |
| 哪些武器力量需求 ≤ 12 | `filter_by_attribute("Weapon", [{"field": "str", "op": "<=", "value": 12}], order_by="weight")` |
| 兩個實體有什麼關係 | `find_path(a, b)` |

## 設計決定

- **重名**：同名 Item 合併之前，圖裡 111 個名字對到 226 個節點（例如 Boss 與 Creature 同名 16 組）。合併後 Item 不再有同名，但 Boss 與 Creature、Boss 與 NPC 等跨類別的同名仍然存在，所以 `get_entity`／`get_neighbors` 不假設只有一個結果：回傳所有候選並附 `note`，可用 `label` 縮小或直接給 `uid`。
- **名稱解析順序**：uid → 精確 → 別名 → 去尾端括號 → 逗號前的簡稱（`Rykard` → `Rykard, Lord of Blasphemy`）→ 模糊比對（相似度 ≥ 0.9、數字一致）。指定 `label` 後某一層沒有結果就往下一層找。正規化與建圖用的 `norm()` 完全一致（測試有比對）。
- **別名**：建圖時把別名表寫成目標節點的 `aliases` 屬性（`build_graph.attach_aliases`），工具只讀圖、不必 import 建圖腳本。例：問句的 `Rennala, Queen of the Full Moon` 精確對到 NPC、別名才對到 Boss `Rennala Carian Queen of the Full Moon`。`link_entities` 會把各層的候選合併，`resolve`（不帶 label）則是精確優先。
- **`link_entities` 的限制**：名稱後面多一個 `s` 也算命中（所有格 `Volcano Manor's`、複數；因為正規化會把撇號去掉）；只做精確／別名／去括號／簡稱比對，不做模糊；名稱短於 `min_len` 的（例如 `Fia`）不會被掃描到，但直接呼叫 `get_entity("Fia")` 可以（走別名）。
- **`find_path` 預設排除 `LOCATED_IN`**：Region 會把同區域的一切連在一起，路徑變雜訊。同一個 Location 底下的兩個實體仍會經 `LOCATED_AT` 得到 2 步路徑，這是資料本來的關係，不代表因果。
- **`filter_by_attribute` 的安全與型別**：欄位名稱必須存在於該標籤（白名單，也擋掉注入式的名稱）、值一律用參數。數值運算子（`<`、`<=`、`>`、`>=`）對欄位用 `toFloatOrNull`，所以存成字串的數字（Weapon 的 `fp_cost` 是 `"25"`）也能比，轉不了的視為不符。預設排除 stub（`include_stubs=True` 才含）。
- **唯讀**：連線用 `READ_ACCESS`，而且工具裡沒有任何寫入的 Cypher。（Neo4j Community 不強制存取模式，所以真正的保證是程式碼裡沒有寫入。）
- **來源可追溯**：每個實體帶 `source`（檔案＋列號），每條邊帶建圖時記錄的來源屬性；Boss↔地點的邊帶 `sources`（哪個檔案說的），回答時可以引用。`GraphTools.source_of(uid)` 回報節點的來源（檔案＋列號），S5 的 agent 用它記錄「這題檢索到了哪些來源」。

## 測試與題庫檢查

**單元測試**（`python3 -m pytest tests/test_graph_tools.py -v`，58 個，Neo4j 連不上時整份 skip）：名稱正規化與建圖一致、名稱解析各層、實體連結（含所有格與別名）、四個工具的正常與錯誤輸入、來源屬性、截斷旗標、注入式欄位名、同名 Item 合併（合併後不再有同名、合併節點同時有兩邊的欄位與邊、正確拼法留在 `aliases`、衝突欄位值保留、物品各狀態的取得方式仍在 `merged_variants`、稽核檔 44 列）。預期值取自題庫標準答案（q06、q09、q59–q64、q60、q72、q87）。已用一個真實 bug（所有格）驗證過測試抓得到問題：拿掉修正後 `test_link_entities_q09` 會失敗，其餘不受影響。

**題庫檢查**（`python3 eval/graph_tools_check.py`，結果存 `eval/results/graph_tools_check.json`）：題庫 relational 與 multi_hop 共 40 題，句型分成 6 個家族，每個家族對應一組**我事先定好的固定工具呼叫**（不經過 LLM）。把工具取回的實體名稱從標準答案文字裡扣掉（名稱先做和工具一致的正規化，並忽略尾端括號與 `Ash of War:` 這類前綴），扣完沒有剩下實體名稱才算 PASS。

| 題型 | 題數 | PASS | FAIL | SKIP |
|---|---|---|---|---|
| relational | 22 | **22** | 0 | 0 |
| multi_hop | 18 | 13 | 1（q08）| 4（q07、q09、q76、q77）|

這個檢查**只驗證工具取得得到資訊**，不是回答正確率：多取回的實體不扣分；LLM 怎麼挑工具、怎麼組答案是 S5 的事。

- **SKIP 的 4 題**（q07、q09、q76、q77）：問句說的是「Volcano Manor 主線戰的 boss」「Elphael 的 boss」這類需要先理解才知道要查誰的說法，固定呼叫做不了，留給 S5 的 LLM 判斷。
- **FAIL 的 q08**（圓桌廳同時是 NPC 又是 Boss 的角色，標準答案 Ensha）：NPC 節點叫 `Ensha of the Royal Remains`，Boss 是 stub `Ensha`，圖裡沒有 SAME_AS，正規化後名稱不同，所以交集是空的。這是**圖的缺口**（`docs/graph-schema.md` 待決定），不是工具的問題，我沒有為了讓它通過而放寬檢查。同型的 q81（Godefroy）通過，因為兩個節點只差大小寫。

**第一次跑的結果是 27 PASS、9 FAIL**，逐一查過原因後：1 題是工具缺口（q75：工具不認得別名，已修）、1 題是圖的缺口（q08）、其餘 7 題是檢查腳本的限制（名稱拼法、括號、前綴、紀念品的判斷方式），已修正檢查腳本。

## 已知問題（從 S4 挖出來的 S3 資料問題，尚未處理）

- **5 個紀念品節點的名稱黏字**：`Remembrance of theBlasphemous`／`theLichdragon`／`theNaturalborn`／`theStarscourge`／`theDragonlord`，來源檔 `remembrances.csv` 的名稱本來就少了空格。工具原樣回傳，LLM 引用時會出現黏字；題庫標準答案是正確拼法。**使用者決定不修**（2026-09-28），只記錄（見 `docs/note.md`「黏字」一節）。
- **同名 Item 節點（已全部合併）**：實際是 43 組、87 個節點，合併後 44 個節點併入保留者，做法與結果見 `docs/graph-schema.md` 的「同名 Item 合併」。合併後 `get_neighbors`／`get_entity` 不再回兩個同名的物品。Larval Tear 兩份原本 `dlc` 標記不同（1 與 0），使用者確認是本篇，已修正為 0 並合併。`Lord of Blood's Favor`（浸血前後）與 `Unalloyed Gold Needle`（斷掉 → 修復 → Millicent）是同一物品的不同狀態，使用者確認後也合併了。
- **合併節點的 `usage`／`location` 只反映一個狀態**：保留節點顯示的是保留者那一列的值，其他狀態的值存在 `merged_variants`（JSON 字串）。例如問 Unalloyed Gold Needle 在哪裡取得，`location` 只會看到 Millicent 那個，斷掉的針（Swamp of Aeonia，Commander O'Neil 掉落）與修復的針（Sage Gowry）要讀 `merged_variants`。LLM 需要知道有這個屬性；S5 的工具說明要提到。
- **同一對節點之間可能有兩條同類型的邊**：例如 Malenia → Remembrance of the Rot Goddess 有兩條 `DROPS`（一條來自 `bosses.csv` 的掉落物字串、一條來自 `remembrances.csv` 的 `boss` 欄），Rykard、Lichdragon Fortissax 等也是。`get_neighbors` 會把同一個鄰居列兩次，邊上的 `source_file`、`note` 不同。這是建邊時各來源各自建一條造成的，不是節點重複；還沒處理。
- **NPC／Boss 沒有 SAME_AS**：Ensha（q08）。
- **NPC 邊的 `sources` 標得不完整**：見 `docs/graph-schema.md`。

## 還沒做

- 給 LLM 的工具定義（JSON schema、描述文字）：S5 已寫在 `src/agent/graph_rag.py`（見 `docs/agent.md`），尚未對真實 LLM 實測。
- text-to-Cypher：計畫書的延伸項目 3，不在 S4。
