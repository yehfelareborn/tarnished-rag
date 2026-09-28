# S0 資料清理紀錄：預期 vs 實際改正

對應腳本：`src/ingest/clean_raw.py`（`data/raw/` 不變，輸出到 `data/processed/`）
詳細發現過程見 `docs/data-sources.md`，本篇只記重點：**改了什麼**。

## armors.csv

- **預期問題**：`dlc` 欄位混用 `"0"`/`"1"`/`"Base Game"` 三種值，204 筆是文字版
- **實際改正**：204 筆 `"Base Game"` → `"0"`

## incantations.csv

- **預期問題**：`dlc` 欄位完全沒有 `"0"`，非 DLC 法術全部用文字 `"Base Game"` 標示，101 筆
- **實際改正**：101 筆 `"Base Game"` → `"0"`

## items/consumables.csv

- **預期問題**：Golden Rune [1]/[2]/[10] 的 `description` 欄位裡有一個沒跳脫的逗號，把句子切成兩半，後半段連同真正的 `dlc` 值一起被擠出、蓋掉了 `dlc` 欄位
- **實際改正**：3 筆把被切斷的兩段 description 用逗號接回去，`dlc` 改回 `"0"`
- **預期問題**：Golden Rune [3] 的 `name` 欄位多了雜訊字元 `" 3"`
- **實際改正**：`"Golden Rune [3] 3"` → `"Golden Rune [3]"`
- **預期問題**：Golden Rune [5] 整筆從檔案消失
- **實際改正**：新增一筆（id=209），`effect="Use to gain 1600 runes"`（使用者提供數值），`description` 用同系列固定開頭句式重建並標註 `[重建值，待覆核]`（不是原始爬蟲文字）

## items/keyItems.csv

- **預期問題**：`Imbued Sword Key`（id=18）的 `dlc` 欄位是髒資料字串 `"Base game & Shadow of the Erdtree DLC"`，一開始誤判為「本篇+DLC 都有」
- **實際改正**：使用者確認是本篇道具，`dlc` 改為 `"0"`（原字串是爬蟲髒資料，不能照字面解讀成雙版本）
- **預期問題（S4 查同名 Item 時發現，2026-09-28）**：`Larval Tear` 在這個檔案有兩列：id=6（`dlc="1"`，有完整地點說明）與 id=64（`dlc="0"`，`location` 只寫 `See Larval Tear for a full list of locations`）。id=6 的 `location` 文字開頭是 DLC 地點（Prospect Town、`[See Shadow of the Erdtree Map]`），爬蟲因此把整列標成 DLC；但它是本篇就有的物品（Rennala 重生要用，圖裡掉落它的 4 個 boss 都是本篇的）
- **實際改正**：使用者確認 Larval Tear 絕對是本篇，id=6 的 `dlc` 由 `"1"` 改為 `"0"`；id=64 本來就是 `"0"`，不動。與 Imbued Sword Key、Golden Rune 同一原則：本篇就有、只是 DLC 也拿得到的物品標 `dlc=0`。這兩列是同名重複，是否合併還沒決定（見 `docs/graph-schema.md` 待決定）

## creatures.csv

- **預期問題**：`Aging Untouchable`（id=12）地點只有 `Abyssal Woods`（DLC 專屬地點，圖檔名也寫 "sote"），但 `dlc` 標 `"0"`
- **實際改正**：`dlc` 改為 `"1"`

## bosses.csv

### HP 欄位
- **預期問題**：153 筆中 58 筆（~38%）HP 非純數字；全檔案掃描分類後只有 2 筆是真正的壞資料（其餘 39 筆空字串判定為雜兵型 boss 本來就沒有單一血量、17 筆是有效但格式複雜的資料，暫不處理）
- **實際改正**：
  - `Base Serpent Messmer`（id=9）：`"TBD"` → `"19,490 (phase 2 of Messmer the Impaler, ≈50% of 38,981 total)"`（使用者提供）
  - `Rennala Carian Queen of the Full Moon`（id=14）：誤植的欄位標題文字 `"Phase 1"` → `"3,493 (phase 1) 4,097 (phase 2)"`（使用者提供）

### 實體拆分
- **預期問題**：`Margit, the Fell Omen`（id=39）的 Locations & Drops 有兩個地點（Stormveil Castle / Capital Outskirts），一開始懷疑是跟 `Morgott, the Omen King` 的資料合併錯誤
- **實際改正**：查證後 Morgott 本來就是獨立一筆（id=16），不是合併問題；使用者確認 Margit 這兩場戰鬥打法不同，**拆成兩個獨立 boss 節點**（id=39: Stormveil Castle；id=154: Capital Outskirts）。兩筆暫時共用同一個原始 HP 值 4,174（沒有各自的數據來源，待補）
- **同樣模式套用到**：`Divine Beast Dancing Lion`（id=0）也是同一 boss 兩場不同戰鬥，拆成 id=0（Belurat, Tower Settlement）與 id=153（Ancient Ruins of Rauh）

### dlc 誤標（地點交叉驗證）
- **預期問題**：用 `locations.csv` 裡 51 個 `dlc=1` 地點名稱 + 8 個 DLC 專屬 region 名稱，程式化比對其他檔案裡 `dlc=0` 但地點全部落在 DLC 清單裡的記錄
- **實際改正**：14 筆 `dlc` 從 `"0"` 改成 `"1"`：
  Divine Beast Dancing Lion、Metyr Mother of Fingers、Base Serpent Messmer、Ancient Dragon-Man、Chief Bloodfiend、Dancer of Ranah、Golden Hippopotamus、Jagged Peak Drake、Black Knight Garrew、Count Ymir Mother of Fingers、Death Knight、Lamenter、Rakshasa、Red Bear
- **判斷為誤報、沒有改**：Death Rite Bird、Fallingstar Beast、Tibia Mariner、Magma Wyrm，以及 creatures.csv 中多筆雜兵（Crab/Giant Crab/Turtle/Lone Wolf/Demi-Human Queen/Giant Crayfish/Fingercreeper 等）——這些地點欄位混雜本篇與 DLC 地點，判定是本篇就存在、只是也會在 DLC 重複出現的類型，`dlc=0` 正確，不動

### 附帶清理
- **預期問題**：`Jagged Peak Drake` 的地點欄位有一個 key 混了 HTML 標籤 `<a class="wiki_link" href="/Jagged+Peak" title="Elden Ring Jagged Peak">Jagged Peak</a>:`
- **實際改正**：清成純文字 `Jagged Peak:`

### 地點與掉落物欄位：兩場戰鬥被接在一起、另一列是空的（S4 查 Perfumer Tricia 時發現，2026-09-29）
- **預期問題**：`locations.csv` 的 Unsightly Catacombs 列出 boss `Perfumer Tricia`，但 `bosses.csv` 沒有這個名稱，只有合併列 id=97 `Perfumer Tricia and Misbegotten Warrior`。查那一列發現它**整列是空的**（`HP`、`Locations & Drops` 都空）；真正的資料在 id=137 `Misbegotten Warrior`（`HP ≈ 3560 (Field Boss)`），但它的掉落物欄把兩場戰鬥接在一起：`{'Unsightly Catacombs': ['Unsightly Catacombs :', '9400 Runes', 'Perfumer Tricia Ashes Redmane Castle :', '16000 Runes', 'Ruins Greatsword']}`。只有一個地點 key，第二個地點的標題 `Redmane Castle :` 被黏在上一個掉落物後面。建圖時它被當表格雜訊丟掉，連 `Perfumer Tricia Ashes` 一起消失，`Ruins Greatsword` 與符文則全算在 Unsightly Catacombs 頭上
- **使用者確認**：Unsightly Catacombs 是 Misbegotten Warrior 與 Perfumer Tricia 同時出現的**同一場戰鬥**，兩者各有血條；Redmane Castle 另有一隻 Misbegotten Warrior 是 boss；`Lion Misbegotten Warrior`（`locations.csv` 的 Redmane Castle 也列了）是另一隻 boss，不是這一隻；Perfumer Tricia Ashes 是 Unsightly Catacombs 那場掉的、Ruins Greatsword 是 Redmane Castle 那隻掉的；HP ≈ 3560 屬於 Redmane Castle 那隻 Misbegotten Warrior
- **實際改正**（`clean_raw.py` 的 `BOSS_LOCATION_FIXES`，原始資料不是預期的樣子會直接報錯）：
  - id=97 `Perfumer Tricia and Misbegotten Warrior`：`Locations & Drops` 由空改為 `{'Unsightly Catacombs': ['9400 Runes', 'Perfumer Tricia Ashes']}`；`HP` 維持空（雙人戰沒有 HP 資料）
  - id=137 `Misbegotten Warrior`：`Locations & Drops` 改為 `{'Redmane Castle': ['16000 Runes', 'Ruins Greatsword']}`；`HP` 維持 `≈ 3560 ( Field Boss )`
  - 名稱都不改。這跟 Margit、Dancing Lion 同一原則：兩場打法不同的戰鬥分成不同節點
- **附帶的對齊調整**：B4 對齊多了一條判斷「地點清單裡已有這隻合併列名稱的其中一員（`Perfumer Tricia`）就不再補整個合併列名稱」，避免 Unsightly Catacombs 的清單同時出現 `Perfumer Tricia` 與 `Perfumer Tricia and Misbegotten Warrior`
- **結果**：id=97 連到 Unsightly Catacombs（`bosses.csv`＋`locations.csv` 兩邊都有）、掉落 `Perfumer Tricia`（召喚灰燼）、符文 9400；id=137 連到 Redmane Castle、掉落 Ruins Greatsword、符文 16000，不再連 Unsightly Catacombs。`Perfumer Tricia` 別名（`build_graph.py`）經使用者確認是對的
- **沒有做的**：其他 boss 列是否也有「地點標題黏在掉落物後面而被當雜訊丟掉」的情形，還沒有掃描

## locations.csv（S1 出題時才發現，非 S0 原本掃到的）

- **預期問題**：Castle Ensis 的 `bosses` 欄位放了兩個掉落物名稱，真正的 boss 名稱被放進 `npcs` 欄位
- **實際改正**：`bosses=['Rellana, Twin Moon Knight']`，`npcs=[]`
- **預期問題**：Leyndell, Royal Capital / Ainsel River 的 `bosses` 欄位放的是子地點名稱，不是 boss 名稱
- **實際改正**：改用 `bosses.csv` 自己的地點欄位反查重建正確清單（Leyndell 9 隻、Ainsel River 2 隻）；查不到對應 boss 的子地點（Minor Erdtree Church、Divine Tower of West Altus）沒有強行補值
- **沒有動的**：`Sealed Tunnel` 的 `npcs` 欄位其實是道具清單，只從出題候選池剔除，資料本身還沒修；`locations.csv` 其餘 282 個地點沒做過系統性稽核

## 黏字（S4 掃描時發現，2026-09-28）

S4 的查詢工具回傳 `Remembrance of theBlasphemous` 時發現 `remembrances.csv` 的 5 個紀念品名稱少了空格，於是掃了 `data/raw/` 全部 29 個 CSV 的所有欄位，找三種黏法：`theX`（如 `theBlasphemous`）、小字接大寫（如 `ofThe`）、句號後沒空格（如 `Reader.Alternatively`）。**掃描的限制**：只抓「小寫接大寫」的邊界，小寫接小寫的抓不到（肉眼看到一個：`shields.csv` id=8 描述裡的 `criticalhit`，該是 `critical hit`），所以「沒有更多」只代表這三種樣式掃不到。

### 小字接大寫（3 處，已修）
- **預期問題**：3 處文字欄位有小字直接接大寫；名稱欄位沒有受影響
- **實際改正**（`clean_raw.py` 的 `fix_glued_text()`，每處都要求原字串在該欄位剛好出現一次，否則報錯）：
  - `armors.csv` id=168 `description`：`Land ofReeds` → `Land of Reeds`
  - `npcs.csv` id=10 `role`：`Garments Adjuster andQuest NPC` → `Garments Adjuster and Quest NPC`
  - `skills.csv` id=106 `locations`：`drop aBanished Knight's Halberd` → `drop a Banished Knight's Halberd`
- `npcs.csv`、`skills.csv` 原本沒有處理版，這次各新增一份 processed 版；`armors.csv` 的處理版本來就存在（dlc 編碼統一）。`build_graph.py` 與 `build_corpus.py` 都優先讀 processed，所以修正會流到圖與語料庫；評分的來源比對（`source_key`）不區分 raw／processed，題庫來源不受影響
- **驗證**：逐格比對 raw 與 processed——`npcs.csv`、`skills.csv` 各剛好 1 格不同，`armors.csv`（忽略 dlc 欄）剛好 1 格；`remembrances.csv` 沒有 processed 版（紀念品名稱沒被動）；修正後「小字接大寫」剩 0 處。重建語料庫（3649 篇）與圖（3905 節點、6598 邊）數量不變；51 個單元測試與題庫檢查結果不變。同一句 `Land of Reeds.Raises` 後半的句號黏字沒動（使用者只指定修小字接大寫）

### 掃到但依使用者決定沒動（只記錄）
- **5 個紀念品名稱黏字**（使用者決定不動）：`items/remembrances.csv` 的 `name` 欄，id 12、13、17、18、24：`Remembrance of theNaturalborn`（Astel）、`theLichdragon`（Lichdragon Fortissax）、`theBlasphemous`（Rykard）、`theStarscourge`（Starscourge Radahn）、`theDragonlord`（Dragonlord Placidusax），都是本篇（dlc=0）。只有 `name` 欄黏：同一列的 `image` 網址與 `description` 拼法正確，同檔案其他 20 列的名稱都有空格。影響：圖的 5 個節點名稱與查詢工具的回傳原樣帶黏字（建圖與工具的名稱正規化會修這種黏字，所以比對不受影響）
- **2 處 `theX` 在描述文字**：`incantations.csv` id=119（`burning theErdtree`）、`weapons.csv` id=97（`the power of theRune of Death`）。使用者只指定修小字接大寫那 3 處，這 2 處沒動
- **1247 處句號後沒空格**：分布在 27 個（檔案，欄位），全是描述／取得方式／效果這類自由文字（例如 `armors.csv` 描述 472 處、取得方式 178 處，`talismans.csv`、`materials.csv`、`sorceries.csv` 等也多）。是整個資料集的普遍現象，看起來是原網頁的段落換行在抓取時被直接接起來，跟紀念品那批無關。這些欄位沒有被圖解析（只是節點的屬性文字），沒動
- **`criticalhit`**（`shields.csv` id=8）：小寫接小寫，掃描樣式抓不到，肉眼發現，沒動

## 沒有動的（明確擱置）

- **Golden Rune [5] 的 `description` 原文**：目前是重建值，不是原始爬蟲文字，之後找到原文要替換
- **bosses.csv 17 筆格式複雜的 HP**（多階段、約略值+分類註記、雙人戰各自血量、"each"/區間表示法等）：留到 S2/S3 ingest 階段再 parse
- **bosses.csv 39 筆空 HP**（重複出現的雜兵型 mini-boss）：判定為資料本來就沒有，不強行補值

## 統計結果（`data/processed/dlc_scrape/`）

| 檔案 | 原始筆數 | 處理後筆數 | dlc=1 筆數變化 |
|---|---|---|---|
| bosses.csv | 153 | 155（+2 拆分） | 19 → 34 |
| creatures.csv | 205 | 205 | 26 → 27 |
| items/consumables.csv | 209 | 210（+1 補回） | — |
| armors.csv | 723 | 723 | dlc 編碼統一為 0/1 |
| incantations.csv | 129 | 129 | dlc 編碼統一為 0/1 |
| items/keyItems.csv | 121 | 121 | — |
