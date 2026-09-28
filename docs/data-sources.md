# 資料來源與授權（S0）

狀態：盤點完成（2026-09-27）。已取得資料、確認授權，抽樣已達 20~30 筆門檻並由使用者（玩過本遊戲）人工核對內容正確性。

## 採用的資料來源

### 1. `dlc_scrape`（主要來源）

- **Kaggle 資料集**：[pedroaltobelli/ultimate-elden-ring-with-shadow-of-the-erdtree-dlc](https://www.kaggle.com/datasets/pedroaltobelli/ultimate-elden-ring-with-shadow-of-the-erdtree-dlc)
- **授權**：CC0 Public Domain（Kaggle 頁面 schema.org 標記明確標示）
- **原始資料出處**：uploader 自述取自 [Fextralife Elden Ring Wiki](https://eldenring.wiki.fextralife.com/)
- **取得時間**：2026-09-27，透過 Kaggle API（Bearer token，使用者提供）下載
- **資料集最後更新**：2024-07-16（DLC 上市後）
- **內容**：`data/raw/dlc_scrape/`，共 15 個頂層檔案 + `items/` 下 13 個子類別，涵蓋 armors, weapons, talismans, sorceries/incantations, bosses, npcs, locations, creatures, shields, spiritAshes, ashesOfWar, skills，以及武器/盾牌強化數值表（`weapons_upgrades.csv`、`shields_upgrades.csv`）
- **DLC 標記**：每個檔案都有 `dlc` 欄位（0/1），已確認實際涵蓋 Shadow of the Erdtree 內容（見下方 DLC 涵蓋章節）

### 2. `boss_stats`（Boss 數值補充）

- **Kaggle 資料集**：[vaibhavdhariwal11/elden-ring-ultimate-boss-dataset](https://www.kaggle.com/datasets/vaibhavdhariwal11/elden-ring-ultimate-boss-dataset)（v2）
- **授權**：CC0 Public Domain
- **原始資料出處**：uploader 自述取自 Fextralife Elden Ring Wiki
- **取得時間**：2026-09-27
- **資料集最後更新**：2025-12-15
- **內容**：`data/raw/boss_stats/elden_ring_boss_stats_clean.csv`，142 筆 boss，欄位包含分階段血量、各傷害類型抗性/減免、異常狀態抗性、韌性、是否可處決（parryable）等——比 `dlc_scrape/bosses.csv` 的數值更完整，用來補 Boss 節點的數值屬性
- 已確認涵蓋 DLC boss（比對 `dlc_scrape` 中 19 隻 dlc=1 的 boss，19 隻在此資料集都能找到對應，13 隻名稱完全一致、其餘 6 隻因標點/逗號差異需要模糊比對，見下方「名稱一致性」）

## 評估後不採用/降級的來源

| 來源 | 授權 | 不採用原因 |
|---|---|---|
| `eldenring.fanapis.com`（deliton/eldenring-api） | GitHub 無 LICENSE；官方文件自承「data was scraped from other Elden Ring fansites and wikis」，二手爬蟲來源不明 | 授權灰色地帶，且類別已被 `dlc_scrape` 完整取代（後者授權更明確、還有 DLC） |
| `EldenRingDatabase/erdb` | **MIT**（本身很乾淨） | 公開 REST API（`api.erdb.wiki`）目前無法連線（DNS 解析失敗），GitHub Releases 無預先產生的資料檔，需自己持有正版遊戲跑 CLI 產生資料，且原本就不含 Boss/NPC/Location 類別 |
| `robikscube/elden-ring-ultimate-dataset`（Kaggle） | CC0 | 資料內容等同 fanapis（同源），不含 DLC；已被 `dlc_scrape` 取代 |
| `mohit55/elden-ring-weapon-data-all-affinities`（Kaggle） | 未標示（Unknown） | 授權不明，且武器類已有更好的來源 |

## DLC 涵蓋

- [x] 已包含 DLC 內容（`dlc_scrape` 每檔皆有 `dlc` 欄位）
- DLC 筆數（原始 `data/raw/`）：bosses 19/153、weapons 94/402、locations 51/286（其餘檔案未逐一統計）
- 清理後（`data/processed/dlc_scrape/`，經拆分與 dlc 誤標修正）：bosses 34/155、creatures 27/205
- **已知缺口**：`dlc` 欄位本身不完全可信，見下方抽樣結果第 1 點——`ingest` 階段不能直接信任這個欄位，需要用 location/名稱交叉驗證
- **已知缺口 2：`dlc` 欄位編碼不一致**。掃過 `dlc_scrape/` 全部 27 個檔案的 `dlc` 欄位分布後發現：
  - `armors.csv`：204 筆用文字 `"Base Game"` 取代 `"0"`（該檔同時存在 `0`/`1`/`Base Game` 三種值）
  - `incantations.csv`：101 筆用 `"Base Game"` 取代 `"0"`，**且此檔完全沒有 `"0"` 這個值**——所有非 DLC 法術都是用文字標，不是單純混用
  - 其餘 25 個檔案的 `dlc` 欄位乾淨，只有 `"0"`/`"1"`
  - ingest 時務必先把 `"Base Game"` normalize 成 `"0"`，否則這兩個檔案的非 DLC 物件會被誤判成布林 True 或直接解析失敗

## 抽樣校驗（40+ 筆，跨類別，使用者人工核對）

**第一輪**：自身既有知識抽查 `dlc_scrape/bosses.csv` 10 個知名 boss。

| 檢查項 | 結果 |
|---|---|
| Margit / Malenia / Radahn / Mohg / Godrick / Rykard / Fire Giant 的 HP、地點 | 正確 |
| Messmer the Impaler（DLC boss）地點與血量 | 正確 |
| **Divine Beast Dancing Lion** | **DLC 標記錯誤**：`dlc=0`，但其掉落地點為「Belurat, Tower Settlement」與「Ancient Ruins of Rauh」，皆為 DLC 專屬地點，實際上是 DLC boss |
| **Radagon of the Golden Order** 的 HP 欄位 | 值為 `"≈ 13,339 (GOD)"`，混入非數值註記文字，需要清理才能當數值用 |
| Margit, the Fell Omen 的地點欄位 | 列出 `['Stormveil Castle:', 'Capital Outskirts']`，疑似與後期同一角色「Morgott, the Omen King」（在 Capital/Leyndell 出現）的資料合併在同一筆，需人工複查是否該拆成兩個實體 |
| Rennala 命名 | CSV 中為 `Rennala Carian Queen of the Full Moon`（缺逗號），與一般寫法 `Rennala, Queen of the Full Moon` 不同 |

**第二輪**：跨類別抽樣 32 筆（weapons 6、armors 4、talismans 4、npcs 3、locations 4、sorceries 2、incantations 2、materials/keyItems 4、額外 DLC boss 3），由使用者（實際玩過遊戲）逐筆核對數值與敘述——**內容全部正確，未發現事實錯誤**。過程中額外發現的技術性問題（非玩家知識可判斷，是欄位本身的 bug）：

- `dlc` 欄位編碼不一致（見上方「DLC 涵蓋」章節，`armors.csv`/`incantations.csv` 用 `"Base Game"` 文字）
- `Base Serpent Messmer`（bosses.csv 第 11 行）：HP 欄位是字串 `"TBD"`（未填值），且此 DLC boss 也被誤標 `dlc=0`——與 Divine Beast Dancing Lion 同一種誤標模式
- `items/consumables.csv` 第 94、95、142 行（`Golden Rune [1]`、`[2]`、`[10]`）：`dlc` 欄位被整段道具描述文字污染，CSV 欄位錯位（非同批的 `[3][4][6][7][8][9]` 則正常）；`Golden Rune [3]`（第 96 行）的 `name` 欄位多了一個雜訊字元 `" 3"`；`Golden Rune [5]` 整筆從檔案中消失。**使用者確認 Golden Rune 系列全部是本篇道具，正確值應為 `dlc="0"`**，欄位錯位純粹是解析問題，不是「跨版本」的意思
- `items/keyItems.csv` 第 20 行（`Imbued Sword Key`，id=18）：`dlc` 欄位值為 `"Base game &\xa0Shadow of the Erdtree DLC"`。**使用者確認 Imbued Sword Key 是本篇道具，正確值應為 `dlc="0"`**，不是「兩邊都有」——這串文字本身也是爬蟲髒資料，不能照字面解讀

**總抽樣數：10 + 32 = 42 筆，超過計畫的 20~30 筆門檻，已由玩過遊戲的使用者確認內容正確性。** 錯誤全部集中在少數「中繼資料/欄位工程」層面（dlc 標記、CSV 錯位、佔位字串），而非遊戲知識本身的事實錯誤——這點對後續 S2/S3 的 ingest 清理很重要：核心內容可信，但欄位層面需要防禦性清理。

## 名稱一致性（跨檔案 entity linking，S3 會用到）

初步觀察到的命名差異模式：
- 逗號/標點差異（`Rennala Carian Queen of the Full Moon` vs `Rennala, Queen of the Full Moon`；`Midra Lord of Frenzied Flame` vs `Midra, Lord of Frenzied Flame`）
- `boss_stats` 與 `dlc_scrape` 之間，19 個 DLC boss 中有 6 個需要模糊比對（去標點後應能大部分解決）

## 資料格式注意事項（供 S2/S3 ingest 參考）

- `dlc_scrape/bosses.csv` 的 `Locations & Drops` 欄位是字串化的 Python dict（例如 `"{'Castle Ensis': ['240,000', 'Remembrance of the Twin Moon Knight']}"`），需要用 `ast.literal_eval` 解析，不是單純 CSV 值
- HP、重量等數值欄位可能含千分位逗號（`"22,571"`）或非數值註記（`"≈ 13,339 (GOD)"`），需要清理成純數字
- `dlc` 欄位不可完全信任，需搭配地點交叉驗證（見抽樣結果）

## 授權聲明（供 README 使用）

本專案的遊戲資料整理自：
- Kaggle 資料集 *Ultimate Elden Ring with Shadow of The Erdtree DLC*（CC0，pedroaltobelli）
- Kaggle 資料集 *Elden Ring Ultimate Boss Dataset*（CC0，vaibhavdhariwal11）

兩者原始內容均取自 Fextralife Elden Ring Wiki，經社群整理為表格並以 CC0 釋出。本專案僅作教育／作品集用途，非商業使用，遊戲版權歸 FromSoftware / Bandai Namco 所有，本專案與其無關。

## S1 出題時新發現的問題（`locations.csv`）

做 S1 題庫的模板出題時（見下方「評估題庫進度」）又發現 `locations.csv` 有欄位污染，跟之前 S0 抽樣時發現的類型不同：

- **Castle Ensis（id=4）欄位對調**：`bosses` 欄位放了兩個掉落物名稱（`Rellana's Cameo`、`Spelldrake Talisman`，這兩個原本就在 `items` 欄位裡，不會遺失資料），真正的 boss 名稱 `Rellana, Twin Moon Knight` 卻被放進 `npcs` 欄位。已修正：`bosses=['Rellana, Twin Moon Knight']`，`npcs=[]`
- **Leyndell, Royal Capital（id=230）／Ainsel River（id=270）欄位內容錯誤**：`bosses` 欄位放的是子地點名稱（例如 `Sealed Tunnel`、`Nokstella, Eternal City`），不是 boss 名稱。改用 `bosses.csv` 自己的 `Locations & Drops` 欄位反查重建：
  - Leyndell, Royal Capital → `['Morgott, The Grace-Given Veiled Monarch Omen King', 'Valiant Gargoyle', 'Erdtree Avatar', 'Golem', 'Godfrey, First Elden Lord (Golden Shade)', 'Lion Guardian', 'Onyx Lord', 'Mohg, the Omen', 'Esgar, Priest of Blood']`
  - Ainsel River → `['Dragonkin Soldier of Nokstella', 'Golem']`
  - `Minor Erdtree Church`、`Divine Tower of West Altus` 兩個子地點在 `bosses.csv` 裡完全查不到對應的 boss，資料本來就沒有，沒有強行補
  - 見 `src/ingest/clean_raw.py` 的 `fix_locations()`
- **尚未處理**：`Sealed Tunnel` 的 `npcs` 欄位其實是道具清單（`Golden Rune (5)`、`Cracked Crystal` 等），不是 NPC。目前只是把它從 S1 出題候選池剔除，**沒有修正資料本身**，也還沒對全部 286 個地點做系統性稽核，不確定還有沒有其他地點也有同類污染

## 待辦

- [x] ~~補完 20~30 筆正式抽樣~~ 已完成（42 筆，跨類別，使用者人工核對）
- [x] ~~`dlc` 欄位需要用地點清單校正一次~~ 已完成。用 `locations.csv` 裡 51 個 `dlc=1` 地點名稱 + 8 個 DLC 專屬 region 名稱，交叉比對其他檔案裡 `dlc=0` 但地點欄位全部落在 DLC 清單裡的記錄：
  - `bosses.csv`：新增 12 筆誤標修正（Metyr Mother of Fingers、Ancient Dragon-Man、Chief Bloodfiend、Dancer of Ranah、Golden Hippopotamus、Jagged Peak Drake、Black Knight Garrew、Count Ymir Mother of Fingers、Death Knight、Lamenter、Rakshasa、Red Bear），加上原本已修的 Divine Beast Dancing Lion、Base Serpent Messmer，共 14 筆 `dlc` 改成 `"1"`
  - `creatures.csv`：`Aging Untouchable`（id=12）誤標修正為 `dlc="1"`
  - **判斷為誤報、未修改**：`Death Rite Bird`、`Fallingstar Beast`、`Tibia Mariner`、`Magma Wyrm`（bosses.csv）與 creatures.csv 中多筆雜兵（Crab/Giant Crab/Turtle/Lone Wolf/Demi-Human Queen/Giant Crayfish/Fingercreeper 等）——這些地點欄位混雜本篇與 DLC 地點，是本篇就存在、只是也會在 DLC 重複出現的雜兵/field boss 類型，`dlc=0` 判定為正確
  - 附帶清理：`Jagged Peak Drake` 的地點欄位有一個 key 混了 HTML 標籤（`<a class="wiki_link" ...>Jagged Peak</a>:`），已清成純文字 `Jagged Peak:`
  - 見 `src/ingest/clean_raw.py` 的 `DLC_FLAG_FIXES`、`fix_creatures()`
- [x] ~~`armors.csv`／`incantations.csv` 的 `"Base Game"` → `"0"` normalize~~ 已完成，見 `src/ingest/clean_raw.py`，輸出到 `data/processed/dlc_scrape/`
- [x] ~~`items/consumables.csv` 的 Golden Rune [1]/[2]/[10]：`dlc` 改回 `"0"`~~ 已完成（同時把被切斷的 description 接回去、清掉 `[3]` 的雜訊字元）
- [x] ~~Golden Rune `[5]` 缺筆~~ 已補回（id=209，`effect="Use to gain 1600 runes"`，使用者確認數值）。**`description` 是依同系列固定開頭句式重建，不是原始爬蟲文字**，標了 `[重建值，待覆核]`，之後找到原文要替換
- [x] ~~`items/keyItems.csv` 的 `Imbued Sword Key`：`dlc` 改回 `"0"`~~ 已完成
- [x] ~~Margit/Morgott 資料合併問題需人工複查~~ 確認不是合併問題（Morgott 原始資料裡本來就是獨立一列 id=16）；使用者確認 Margit 的 Stormveil Castle 與 Capital Outskirts 兩場戰鬥打法不同，已拆成兩個獨立 boss 節點（id=39、id=154），見 `src/ingest/clean_raw.py` 的 `fix_bosses()` / `SPLIT_MULTI_ENCOUNTER_IDS`。**待確認**：兩筆目前共用同一個 HP 值 4,174，沒有各自的數據來源
- [x] ~~`Divine Beast Dancing Lion` 的 Locations & Drops 也有兩個地點~~ 確認是同一種「同一 boss 兩場不同戰鬥」模式，已拆成兩個獨立 boss 節點（id=0：Belurat, Tower Settlement 初戰；id=153：Ancient Ruins of Rauh 強化重戰），見 `src/ingest/clean_raw.py` 的 `SPLIT_MULTI_ENCOUNTER_IDS`
- [x] ~~Divine Beast Dancing Lion / Base Serpent Messmer 的 dlc 誤標~~ 兩筆都已改成 `dlc="1"`（原本誤標 `"0"`），見 `DLC_FLAG_FIXES`
- [x] ~~`bosses.csv` 中 HP 非數字的筆數清點~~ 已全檔案掃描：153 筆中 58 筆（~38%）HP 非純數字。分三類：(a) 39 筆是空字串——多為會在地圖多處重複出現的雜兵型 mini-boss（Onyx Lord、Tree Sentinel 等），wiki 本來就沒給單一血量，暫不視為錯誤；(b) 17 筆是格式複雜但有效的資料（多階段、約略值+分類註記、雙人戰各自血量、"each"/區間表示法），之後 ingest 時需要 parse；(c) 真正的壞資料只有 2 筆，已修正：
  - `Base Serpent Messmer`（id=9，Messmer the Impaler 的第二階段/蛇形態）：`"TBD"` → `"19,490 (phase 2 of Messmer the Impaler, ≈50% of 38,981 total)"`（使用者提供正確數據）
  - `Rennala Carian Queen of the Full Moon`（id=14）：`"Phase 1"`（誤植的欄位標題文字）→ `"3,493 (phase 1) 4,097 (phase 2)"`（使用者提供正確數據）
  - 見 `src/ingest/clean_raw.py` 的 `HP_FIXES` / `fix_bosses()`
- [x] ~~Castle Ensis / Leyndell, Royal Capital / Ainsel River 的 bosses/npcs 欄位污染~~ 已修正，見上方「S1 出題時新發現的問題」與 `src/ingest/clean_raw.py` 的 `fix_locations()`
- [ ] `Sealed Tunnel` 的 `npcs` 欄位是道具清單，尚未修正；`locations.csv` 其餘 282 個地點沒做過系統性稽核，不確定還有沒有其他同類污染
