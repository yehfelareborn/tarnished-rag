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

## locations.csv（S1 出題時才發現，非 S0 原本掃到的）

- **預期問題**：Castle Ensis 的 `bosses` 欄位放了兩個掉落物名稱，真正的 boss 名稱被放進 `npcs` 欄位
- **實際改正**：`bosses=['Rellana, Twin Moon Knight']`，`npcs=[]`
- **預期問題**：Leyndell, Royal Capital / Ainsel River 的 `bosses` 欄位放的是子地點名稱，不是 boss 名稱
- **實際改正**：改用 `bosses.csv` 自己的地點欄位反查重建正確清單（Leyndell 9 隻、Ainsel River 2 隻）；查不到對應 boss 的子地點（Minor Erdtree Church、Divine Tower of West Altus）沒有強行補值
- **沒有動的**：`Sealed Tunnel` 的 `npcs` 欄位其實是道具清單，只從出題候選池剔除，資料本身還沒修；`locations.csv` 其餘 282 個地點沒做過系統性稽核

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
