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

---

# S1～S4 遇到的困難與實際改動（2026-09-28～29 整理）

上面是 S0 的資料清理。這一章記 S1（題庫）到 S4（圖查詢工具）過程中遇到的困難，重點是**實際改了什麼**。每項寫「困難 → 實際改動 → 結果」；細節與數字以各項標的文件為準（`docs/graph-schema.md`、`docs/graph-tools.md`、`docs/local_run.md`、`docs/run_haiku.md`）。

## S1～S2：題庫與向量基準線

**評分檔的來源與可信度**
- 困難：Qwen 基準線的評分檔不是我產生的，而是同一個 session 被兩個終端機同時 resume 時，另一個 Claude Code 行程用 `eval/draft_judgment.py`（字詞重疊自動初判）產生並自行複查，**沒有人工判定**。
- 實際改動：稽核後發現 q08 判錯（標準答案 Ensha，模型答「沒有人同時是 NPC 和 boss」卻被判 correct），改為 wrong 並寫回評分檔、重跑 `run_eval.py score`（Qwen 整體 0.934 → 0.925）。Haiku 那次的判定由 Claude 逐題對照標準答案判定，明確標「非人工」（`vector_baseline_anthropic_judgments.json`）。`docs/local_run.md` 新增「判定的可信度」一節。

**可攜性與公開 repo**
- 困難：第一次推 GitHub 前發現 `.gitignore` 不存在，`generate_questions.py` 有本機絕對路徑。
- 實際改動：補 `.gitignore`（`.env` 等）；`generate_questions.py` 改成相對路徑；`data/raw/README.md` 補資料來源與授權；`.env`（API 金鑰、Neo4j 密碼）從未進入版本控制，推送前掃描過。

## S3：建立知識圖譜

**名稱比對誤連**
- 困難：一開始有「名稱互相包含」的泛用比對，把 `X` 連到 `Lesser X`、`Fire Knight Queelign` 連到泛稱的 `Fire Knight`，誤連約 25 對。
- 實際改動：移除該規則，改成有順序的比對（精確 → 清理後精確 → 別名表 → 去空白 → 錯字容忍 → 建 stub），別名表 19 組、錯字容忍要求相似度 ≥ 0.93 且數字一致、唯一候選；所有比對與 stub 都寫進 `graph_fuzzy_matches.csv`、`graph_stubs.csv`、`graph_unmatched.csv`。

**把敵人誤升格成 boss**
- 困難：我曾寫「`creatures`／`npcs` 欄位的名字若對到同名 Boss 就升格成 Boss 位於此地點」，誤升格 18 條（15 條來自 creatures、3 條來自 npcs），Volcano Manor 的 `Bloodhound Knight`、`Omenkiller` 被當成 boss，q06 多出 2 隻。
- 實際改動：移除該規則，這兩個欄位的名字一律當 Creature／NPC，對不到就建 stub。q06 現在回傳的 5 隻與標準答案一致。

**欄位混入不該有的東西**
- `locations.csv` 的 `npcs`／`creatures` 欄位混進物品（38 筆）：改成「該物品位於此地點」的 `LOCATED_AT`，不建假 NPC。
- 掉落物欄有符文範圍、表格殘渣、`Map Link`、`N/A` 等雜訊：加過濾規則，共略過 251 筆（符文範圍 150、其餘 101）。

**多地點黏成一串、地點名稱含逗號**
- 困難：`bosses.csv` 把多個地點寫成一串（`Murkwater Cave , Limgrave Liurnia Mt. Gelmir …`），地點名稱本身又含逗號（`Leyndell, Royal Capital`）。第一版碰到逗號只處理第一段；第二版逐段處理但把含逗號的名稱切壞。
- 實際改動：`resolve_location` 改成**先對整串掃描已知的地點／區域名**，掃不到才退回逗號切段。之後發現掃描命中後剩下的字串會被無聲丟掉（`bosses.csv` 241 個地點欄 key 中有 4 個、3 種殘留文字：`Specimen Storehouse`、`Foothills`、`Liurnia`），再加 `LOCATION_ALIASES`（`Jagged Peak Foothills` → `Foot of the Jagged Peak`）、`LEFTOVER_PLACES`（`Liurnia` → 區域、`Specimen Storehouse` → 建 Location stub），其他殘留一律記到 `graph_unmatched.csv`（`boss_location_leftover`，目前 0 筆）。

**同一角色依地點有不同身分（Patches）**
- 實際改動：`build_graph.py` 的 `BOSS_ONLY_AT`，Patches 只在 Murkwater Cave 是 Boss，其他地點（Volcano Manor、The Shaded Castle、Limgrave、Mt. Gelmir、Liurnia of the Lakes）改掛在同名 NPC 節點上。

**`bosses.csv` 與 `locations.csv` 對 Boss↔地點的說法不一致**
- 困難：兩個檔案各記了一個方向，實際上對不上（分成 A1、A2、B1～B4 六類）。
- 實際改動：
  - Boss 的 `LOCATED_AT` 邊加 `sources` 屬性標明是哪個檔案說的，並寫唯讀稽核腳本 `src/graph/audit_boss_locations.py`。
  - **A1／B4 對齊**（`clean_raw.py` 的 `align_boss_locations`，使用者裁決）：B4 補 20 筆進地點的 boss 清單；A1 在 `bosses.csv` 補 9 列（10 條關係）；另有 9 個名稱刻意跳過（8 個在 `npcs.csv`／`creatures.csv` 已有同名實體、1 個是合併列的成員）。全部記在 `data/processed/alignment_changes.csv`。
  - **B1**：`locations.csv` 把它列成 creature 的，不建 Boss 邊（`boss_edge_skipped_creature_here`，7 → 5 條）；**Golem 是使用者確認的例外**。
  - **B2**：Dryleaf Dane 維持原樣（特例）。
  - **B3**：使用者逐條確認 5 條正確，連同 Golem 那串每個地點，共 7 筆放進 `CONFIRMED_BOSS_LOCATIONS`。
- 結果：兩邊都有 143 → 184；A1 19 → 8；A2 54 → 53。
- 我自己寫的 bug：A1 迴圈只記了新增列的第一個地點（`Stray Mimic Tear` 漏了第二個），已修。

**兩場戰鬥被接在同一列（Perfumer Tricia／Misbegotten Warrior）**
- 實際改動：見上方 `bosses.csv`「地點與掉落物欄位」一節。`BOSS_LOCATION_FIXES` 把兩場戰鬥各放回自己那一列，原本被當雜訊丟掉的 Perfumer Tricia（召喚灰燼）掉落進圖（`DROPS` 1309 → 1310）。

**題庫標準答案被資料對齊影響（q60）**
- 困難：B4 對齊把 Ulcerated Tree Spirit 補進 Belurat Tower Settlement 的 boss 清單，題庫標準答案（取自對齊前的 `locations.csv`）只有一隻。
- 實際改動：使用者依遊戲知識確認 Belurat 確實有這隻，`eval/questions.jsonl` q60 改為兩隻；兩個基準線對 q60 重判為 partial（原 correct，重判者為 Claude、非人工）。relational 1.000 → 0.977；Qwen 整體 0.925 → 0.920、Haiku 0.939 → 0.934。同時逐題掃描其他 9 題提到被動過實體的題目，標準答案都沒被波及。

## S4：圖查詢工具

**實體連結漏掉所有格**
- 困難：`link_entities` 把撇號去掉，`Volcano Manor's` 變成 `volcano manors`，對不到 `volcano manor`，q09 漏掉一個地點。
- 實際改動：名稱後面多一個 `s` 也算命中。單元測試拿掉這個修正時 `test_link_entities_q09` 確實失敗，證明測試抓得到。

**工具不認得別名**
- 困難：題庫 q75 用 `Rennala, Queen of the Full Moon`，圖裡 Boss 叫 `Rennala Carian Queen of the Full Moon`，只有 NPC 叫問句那個名字，別名只存在建圖腳本裡。
- 實際改動：`build_graph.py` 新增 `attach_aliases()`，把別名表寫成節點的 `aliases` 屬性，工具只讀圖；`link_entities` 把精確、別名、去括號、簡稱各層的候選合併。

**題庫檢查第一次 27 PASS、9 FAIL**
- 逐一查因：1 題是工具缺口（q75，已修）、1 題是圖的缺口（q08，Ensha 的 NPC 與 Boss stub 名稱不同，沒有 SAME_AS）、其餘 7 題是我的檢查腳本太死板（名稱拼法、括號、`Ash of War:` 前綴、用名稱判斷紀念品）。修正檢查腳本後 relational 22／22、multi_hop 13 過、1 失敗（q08）、4 跳過。q08 我保留為失敗，沒有放寬檢查去遷就。

**同名 Item 節點**
- 困難：同名 Item 有 43 組、87 個節點（一開始用小寫名稱比對只找到 36 組，漏掉名稱只差空格或引號、以及 5 個黏字紀念品）。多數是不同分類檔各記同一個物品的一部分（例如 `consumables.csv` 記 Remembrance 的效果、`remembrances.csv` 記兌換選項與 boss），造成 `get_neighbors` 回兩個同名物品，其中一個常常是沒有邊的空殼。
- 實際改動：`build_graph.py` 新增 `merge_duplicate_items()`，節點建好後、建邊之前合併，44 個節點併入保留者（Item 965 → 921，節點 3861，邊數不變）。保留誰依 `ITEM_PRIORITY`；缺的欄位補上、衝突的欄位值存進 `merged_variants`、來源分類存進 `item_types`、拼法不同的名稱存進 `aliases`、被併掉的 uid 存進 `merged_from`；稽核檔 `data/processed/graph_item_merges.csv`（44 列）。Lord of Blood's Favor（浸血前後）與 Unalloyed Gold Needle（斷掉 → 修復 → Millicent）我原本當成不同物品排除，使用者確認是同一物品的不同狀態後也合併了。
- 限制：合併節點的 `usage`／`location` 只反映保留者那個狀態，其他狀態在 `merged_variants` 的 JSON 字串裡。

**`dlc` 標記與黏字**
- Larval Tear（`keyItems.csv` id=6）`dlc` 1 → 0（使用者確認是本篇；它的地點說明開頭是 DLC 地點，被誤標）。
- 黏字掃描 `data/raw` 全部 29 個 CSV：修 3 處小字接大寫（`ofReeds`、`andQuest`、`aBanished`，`fix_glued_text()`，新增 `npcs.csv`、`skills.csv` 的 processed 版）；**5 個紀念品名稱黏字（`theBlasphemous` 等）依使用者決定不動、只記錄**；另有 2 處 `theX` 在描述文字、1247 處句號後沒空格、1 處小寫接小寫（`criticalhit`），沒動。見上方「黏字」一節。

**我寫的 `clean_raw.py` 新函式第二次執行會報錯**
- 困難：`fix_glued_text()` 讀檔規則是「processed 有就讀 processed」，`npcs.csv`、`skills.csv` 的 processed 版只是上一次執行的成品，第二次讀到已修好的版本，原字串已不存在而報錯，中斷後面的步驟。上一輪我只從乾淨狀態跑了一次，沒有發現。
- 實際改動：只有 `armors.csv`（同一次執行裡前一步剛產生）讀 processed（`PROCESSED_FIRST`），其他檔案一律從 raw 出發。用「連跑兩次比對 10 個 processed 檔案的雜湊」驗證結果完全相同。

## 流程與環境

- **Bash 工具在 auto mode 下反覆失敗**（`auto mode classifier gave no verdict`，是伺服器端安全檢查暫時沒回應，跟指令內容無關；同一支腳本失敗兩次、不改內容後又成功過）。改做法：需要跑指令時我貼 `!` 指令請使用者跑再貼回輸出；2026-09-29 使用者授權本地 `git commit` 我可以自己跑，push 與打 tag 仍先問。這個偏好存在我的記憶檔，不在 repo 裡。
- **背景建置**：我曾說背景執行的建置在退出 session 後還會繼續，實際不會，改用 `nohup setsid` 重新啟動。
- **金鑰**：API 金鑰與 Neo4j 密碼只在被 `.gitignore` 排除的 `.env`；Kaggle token 只暫時使用；推送前掃過 repo。

## 至今還沒處理的（見 `docs/graph-schema.md` 待決定）

- NPC／Boss 沒有 SAME_AS（Ensha、q08 因此失敗）。
- 同一對節點之間有兩條同類型的邊（例如 Malenia → Remembrance of the Rot Goddess 兩條 `DROPS`）。
- 「地點標題黏在掉落物後面而被當雜訊丟掉」在其他 boss 列有沒有，還沒掃。
- ~~A2 的 53 條~~：已逐條分類、處理、能修的都修完（2026-10-02～10-04，詳見 `docs/graph-schema.md`）。15 條使用者確認是真正錯誤，已從資料層移除；另一個爬蟲 bug（Crucible Knights／Night's Cavalry 地點標題遺失）也修了，救回 15 個地點、2 條因此對上；~~3 組同名 Location 重複~~（Divine Tower of Caelid 等）也合併了，解掉 Godskin Apostle 的假訊號。剩 35 條都不是真衝突（15 條真正的資料缺漏，含 Mad Pumpkin Head／Black Knife Assassin 這兩隻確認無資料可救；~21 條大區/子地點階層）。語料庫是否去重（43 組同名 Item，只有圖層合併了，corpus.jsonl 還沒）。
- ~~232 個 stub 保留與否~~：已決定保留（2026-10-01）。
- ~~向量索引與兩個基準線是舊資料~~：已重建索引（3649 篇）並重跑兩個基準線（2026-09-30），見 `docs/run_haiku.md`。

## 履歷描述（side project 版本，2026-10-05 整理）

**Elden Ring GraphRAG**（Side Project）
*Knowledge graph + LLM tool use vs. vector RAG, benchmarked on a self-built 106-question eval set*

- Built a typed knowledge graph (~3.9k nodes, ~6.6k relations, Neo4j) from wiki-scraped CSV sources, with entity resolution (aliases, typo tolerance, duplicate merging), per-case audit logs, and 80 unit tests.
- Implemented a tool-calling agent in which the LLM chooses among four graph queries and vector search, with error-tolerant retries and step limits. The same agent runs on a local 4B model (llama.cpp) and on Claude Haiku through a single provider adapter.
- Designed a 106-question benchmark over 7 question types, with ablations (vector-only, graph-only, hybrid, with/without entity hints) and failure analysis. On multi-hop relational questions, graph-based answers scored 100% (18/18) vs. 77.8% (14/18) for vector RAG under the same generator.
- Diagnosed silent tool failures and prompt gaps; targeted fixes raised false-premise accuracy from 16.7% to 58.3% on a 6-question subset.
- Built a resumable, temperature-gated batch runner after diagnosing hardware shutdowns during sustained GPU workloads.

**使用上的注意**（對應 `docs/experiments.md` 的限制）
- multi-hop 數字是單次執行、18 題，每題約 5.6 個百分點；B、C 的主表還是修正 prompt 之前的版本。
- 16.7% → 58.3% 只能寫成「on a 6-question subset」，不能寫成整體提升。
- 不要用 production、users、outperforms in general 這類說法。
- 中文查詢不支援、只有 Elden Ring 一個領域，放在 README 和面試時說明。
