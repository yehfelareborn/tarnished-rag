# 知識圖譜 Schema（S3）

狀態：**已建圖**（2026-09-28）。Neo4j Community 2026.09.0，資料來源為 `data/processed/dlc_scrape/`（沒有處理版的檔案退回 `data/raw/`）與 `data/raw/boss_stats/`。建圖腳本 `src/graph/build_graph.py`，每次執行會清空資料庫重建（約 4 秒，結果可重現）。`bosses.csv` 與 `locations.csv` 之間的 Boss↔地點對齊（A1／B4，見「建圖過程發現的資料問題」）是在資料層做的：`src/ingest/clean_raw.py` 的 `align_boss_locations()`，每一筆變更記錄在 `data/processed/alignment_changes.csv`。

原則：只用結構化欄位建圖，不用 LLM 抽取；每個節點與邊都帶 `source_file`（邊多帶來源欄位資訊）；所有節點帶 `dlc`（0／1）。所有節點另掛一個共用標籤 `Entity`，有唯一 `uid` 與 `name` 索引。

## 節點（共 3864 個，其中 233 個是 stub）

| 標籤 | 節點數 | 其中 stub | 來源 | 主要屬性 |
|---|---|---|---|---|
| `Item` | 924 | 131 | items/*.csv 的 13 個子類（同名的已合併，見下）| `item_type`（子類名）、effect、description、usage 等該子類有的欄位；合併過的另有 `merged_from`、`item_types`、`merged_variants` |
| `Armor` | 723 | 0 | armors.csv | slot、weight、damage_negation、resistance、special_effect、how_to_acquire |
| `Weapon` | 403 | 1 | weapons.csv | category、damage_type、weight、passive_effect、skill、`str/dex/int/fai/arc`（由 `requirements` 拆開）|
| `Location` | 298 | 12 | locations.csv | description |
| `Skill` | 261 | 4 | skills.csv | skill_type、equipment、charge、fp、effect |
| `Creature` | 259 | 54 | creatures.csv | blockquote |
| `Spell` | 214 | 1 | sorceries.csv、incantations.csv | school、effect、fp、slot、`int/fai/arc`、location_text |
| `Boss` | 177 | 13 | bosses.csv ＋ boss_stats | hp_raw、hp（能 parse 成單一數字才有）、`bs_*`（boss_stats 的減免、抗性、韌性等）|
| `Talisman` | 155 | 0 | talismans.csv | effect、weight、value |
| `NPC` | 126 | 17 | npcs.csv | role、voiced_by |
| `AshOfWar` | 117 | 0 | ashesOfWar.csv | affinity、skill |
| `Shield` | 100 | 0 | shields.csv | 同 Weapon |
| `SpiritAsh` | 84 | 0 | spiritAshes.csv | spirit_type、fp_cost、hp_cost、effect |
| `Region` | 23 | 0 | locations.csv 的 `region` 欄 | name |

已確認的設計選擇：
- **Item 不依子類拆標籤**，13 個子類統一為 `Item`，以 `item_type` 屬性區分
- **Boss 與 Creature 分開**
- **Region 是節點**（不是 Location 的屬性）
- **符文數放 `LOCATED_AT` 邊、掉落物在 `DROPS` 邊上標 `at_location`**：因為 boss 有多個戰鬥地點時，每個地點的符文與掉落都不同（例如 Magma Wyrm 在 4 個地點各有不同的符文與掉落物），放在節點會蓋掉差異
- **別名寫進節點的 `aliases` 屬性**（`build_graph.attach_aliases`，S4 加的）：把 `ALIAS_TEXT` 與 `LOCATION_ALIAS_TEXT` 兩張別名表寫到目標節點上（字串陣列），讓查詢工具只讀圖就認得別名，例如 Boss `Rennala Carian Queen of the Full Moon` 帶有 `aliases: ['Rennala, Queen of the Full Moon']`。不影響節點與邊的數量，只多一個屬性
- **同名 Item 合併**（`build_graph.merge_duplicate_items`，S4 加的；使用者 2026-09-28 決定）：以 `norm(name)` 分組，同名的 Item 節點合成一個，共 **41 組、41 個重複節點併入**（Item 965 → 924，全部節點 3905 → 3864）。原因是不同分類檔各記了同一個物品的一部分（例如 `consumables.csv` 記 Remembrance 的效果、`remembrances.csv` 記兌換選項與 boss），或同一個檔案把同一列寫了兩次。
  - **做法**：節點建好後、建邊之前合併，後面所有名稱比對就只會找到保留的那個，所以邊的數量不變（6598）。保留誰：依 `ITEM_PRIORITY`（remembrances、greatRunes、keyItems、tools … consumables 最後），同來源取列號最小的。
  - **不丟資料**：保留者缺的欄位用被併掉的補上（例如紀念品補上 `effect`）；兩份都有值但不同的欄位（13 組，多半是描述文字微調，例如 `zei・jyaku` 與 `zeijyaku`），保留者的值不變、另一份的值記在 `merged_variants`（JSON 字串）；被併掉的 uid 記在 `merged_from`，所有來源分類記在 `item_types`；拼法不同的名稱記在 `aliases`（共 9 個：正確拼法的 `Remembrance of the Blasphemous` 等 5 個黏字紀念品，以及引號空格或大小寫不同的 `Prattling Pate` 系列 4 個）。每個被併掉的節點一列寫到 `data/processed/graph_item_merges.csv`。
  - **不合併的 2 組**：`Lord of Blood's Favor`（keyItems 45／46：白布與染紅的布，`location`、`usage` 完全不同）、`Unalloyed Gold Needle`（keyItems 40／41／42：完整、斷掉、修復三種狀態）。同名但是不同物品／任務狀態，硬併會把它們變成一個，待使用者判斷。
  - **已查**：題庫的 `source` 沒有指到被併掉的那一列；合併後 Rot Goddess 是單一節點，同時有 `DROPS` 與 `EXCHANGES_FOR`。
  - **一開始的數字要更正**：最早用小寫名稱比對只找到 36 組、73 個節點，漏掉名稱只差空格或引號的 2 組，以及 5 個黏字紀念品（`theBlasphemous` 與 `the Blasphemous` 不同）。用建圖的正規化名稱比才是 43 組、87 個節點。

## 邊（共 6598 條）

| 關係 | 條數 | 方向 | 來源欄位 | 邊上的屬性 |
|---|---|---|---|---|
| `LOCATED_AT` | 4334 | Boss／NPC／Creature／物品類 → Location（或 Region）| bosses.csv `Locations & Drops` 的 key；locations.csv 的 `bosses`／`npcs`／`creatures`／`items` 清單 | `source_file`、`runes`（來自 bosses.csv 的邊，共 219 條有值）、`match`（exact／alias／substring／region／stub／from_location_list）、`note`、`sources`（見下）|
| `DROPS` | 1309 | Boss／Creature → 物品類 | bosses.csv 每個地點 key 底下的 list；creatures.csv `drops`；remembrances.csv 的 `boss` | `at_location`（443 條有值）、`note`（例如 `via set: X Set`、`stub`）|
| `HAS_SKILL` | 500 | Weapon／Shield → Skill | weapons.csv／shields.csv `skill` | |
| `LOCATED_IN` | 286 | Location → Region | locations.csv `region` | |
| `GRANTS` | 116 | AshOfWar → Skill | ashesOfWar.csv `skill` | |
| `EXCHANGES_FOR` | 53 | 紀念品（Item）→ Weapon／Spell／Talisman／AshOfWar／Item | remembrances.csv `option 1`／`option 2`（用型別前綴決定目標標籤）| `option`（1／2）|

**`sources` 屬性**：`LOCATED_AT` 邊上的字串陣列，記錄「這條 Boss↔地點關係是哪個檔案說的」——`['bosses.csv','locations.csv']` 表示兩邊都有寫，只有一個檔名表示只有那一邊有寫。只設在 Boss 的邊（以及依 `BOSS_ONLY_AT` 拆出的 NPC 身分的邊）上，其餘 4015 條邊沒有這個屬性。目前 Boss 邊分布：兩邊都有 183、只有 bosses.csv 67、只有 locations.csv 62（共 312）；另有 7 條掛在 NPC 節點上（Patches 的 NPC 身分）。這 7 條的 `sources` 都是 `['bosses.csv']`，其中 The Shaded Castle 與 Volcano Manor 各有兩條邊，一條來自 bosses.csv、一條來自 locations.csv 的 `npcs` 清單，後一條的 `sources` 標得不完整（只寫 bosses.csv）。這是既有的小瑕疵，NPC 邊不在 Boss↔地點稽核範圍，尚未修。用途是讓稽核與（日後 S4 的）查詢工具能依來源篩選或加權，見下方「兩個來源對 Boss↔地點的說法不一致」。

**限制**：資料層對齊（A1、B4、使用者確認清單）補出來的關係，`sources` 標的「兩邊都有」是對齊的結果——被補的那一邊是我寫進去的，**不代表兩個來源各自獨立確認**。這類關係共 37 條（B4 20 條、A1 10 條、使用者確認清單 7 條），獨立證據只有原本就有寫的那一邊，可從 `data/processed/alignment_changes.csv` 查出是哪些。要看「真正獨立兩邊都有」的關係，需要排除這 37 條，或對照 `data/raw/`。

能力需求存在 Weapon／Spell 的屬性上，不做成邊；`filter_by_attribute` 直接篩屬性。

## 名稱比對（entity resolution）

跨檔案靠名稱把 list 裡的字串接到節點。比對順序，前面命中就停：

1. **精確**：正規化後相等（小寫、去標點與撇號、去重音、修 `theBlasphemous` 這類黏字）
2. **清理後精確**：對候選字串做明確的清理再精確比對——去 HTML 實體、去頭尾數量（`12x X`、`X x5`、`x1 X`）、去尾端括號註解（`(NG Only)`、`(6)`、`(+8)`、任意長度括號）、去 `Gateway:` 這類短前綴、去 `Ashes` 後綴（召喚靈）、`+N` 補成 `+N Variant`（護符）
3. **別名表**（後備，精確比對優先）：共 19 組。前 7 組依遊戲知識判斷為同一實體，**已由使用者確認正確**（Morgott、Rennala 的 boss 全名、`Nepheli Loux`、`Count Ymir`、`War Counselor Iji`、`Shaded Castle Spirit`、`Soldier of Godrick`→`Godrick Soldier`）；其餘為 NPC 簡稱，逐一對照過 npcs.csv 的實際名稱（`Fia`、`Blaidd`、`Diallos`、`Corhyn`、`Ansbach`、`Boc`、`Alexander`、`Yura`、`Rennala`、`Ranni the Witch`、`Ensha`）。最後一組 `Perfumer Tricia`→`Perfumer Tricia and Misbegotten Warrior`（`locations.csv` 用單人名字，`bosses.csv` 是合併列）是 A1 對齊時我加的，**尚未經使用者確認**
4. **去空白**：補空白或撇號黏合的差異（`Wolf s Assault` → `Wolf's Assault`）
5. **錯字容忍**（僅在建 stub 之前，僅限 Boss／NPC／Creature／Location）：相似度 ≥ 0.93、數字完全相同、且只有一個候選。實際合併 27 次，多為單複數（`Teardrop Scarab`／`Scarabs`），加上 `Black Knight Edreed`／`Edredd`
6. **建 stub**：以上都對不上，但資料裡確實有明確提到，就建只有名稱與來源、標記 `stub=true` 的節點，全部列在 `data/processed/graph_stubs.csv`

**曾試過但拿掉的規則**：「名稱互相包含」的泛用比對，會把 `X` 連到 `Lesser X`、`Somber Smithing Stones` 連到 `Smithing Stones`、`Fire Knight Queelign`（有名字的角色）連到泛稱的 `Fire Knight`，誤連約 25 對，所以移除。

**`bosses.csv` 地點欄專用的兩張表**（`build_graph.py`）：`LOCATION_ALIASES` 是整串別名，優先於掃描（`Jagged Peak Foothills`→`Foot of the Jagged Peak`，使用者確認）；`LEFTOVER_PLACES` 是整串掃描後剩下的字串的處理方式，只收使用者確認過的（`Liurnia`→區域 `Liurnia of the Lakes`、`Specimen Storehouse`→建 Location stub）。不在表裡的殘留字串一律記到 `graph_unmatched.csv`，不無聲丟掉。

稽核用的輸出：
- `data/processed/graph_fuzzy_matches.csv`：所有靠清理／別名／去空白／錯字容忍成功的比對（145 次）
- `data/processed/graph_stubs.csv`：所有 stub（233 筆）
- `data/processed/graph_unmatched.csv`：未命中與欄位污染記錄（44 筆：`column_contaminated` 38、`boss_is_creature_here` 5、`boss_location` 1；另有 `boss_location_leftover`＝地點欄掃描後的殘留字串，目前 0 筆）
- `data/processed/alignment_changes.csv`：資料層 Boss↔地點對齊的每一筆變更（46 筆：B4 20、使用者確認清單 7、A1 新增 10、A1 跳過 9，見下）
- `data/processed/graph_item_merges.csv`：同名 Item 合併的每個被併掉的節點（41 列）：保留的 uid、被併掉的 uid、兩邊的名稱、衝突欄位的兩份值（JSON）

## 建圖過程發現的資料問題

- **`locations.csv` 的 `npcs`／`creatures` 欄位混進物品**：至少出現在 Murkwater Catacombs、Stormfoot Catacombs、Seethewater Cave、Sealed Tunnel、Bestial Sanctum、Uhl Palace Ruins 等地點（共 38 筆）。判斷方式：名稱對不上該欄位的實體，但能對到物品，或出現在別處的物品清單裡。處理：改成「該物品位於此地點」的 `LOCATED_AT`，不建假 NPC
- **曾經寫錯又移除的規則**：我原本讓「`creatures`／`npcs` 欄位裡的名字若對到同名 Boss，就升格成該 Boss 位於此地點」，結果把一般敵人誤升格成 boss（15 條來自 creatures 欄位、3 條來自 npcs 欄位）。例如 Volcano Manor 的 `Bloodhound Knight`、`Omenkiller` 在 `locations.csv` 是 **creatures**，圖卻回報它們是那裡的 boss，造成 q06 多出 2 隻。已移除，現在這兩個欄位裡的名字一律當 Creature／NPC，對不到就建 stub，不替資料做它沒說的分類
- **黏在一起的多地點字串**：`bosses.csv` 的重複出現型 boss 常把多個地點寫成一串（例如 Patches：`Murkwater Cave , Limgrave Liurnia Mt. Gelmir Volcano Manor The Shaded Castle`），而且有些地點名稱本身含逗號（`Leyndell, Royal Capital`、`Sellia, Town of Sorcery`）。第一版解析碰到逗號就切段，只處理第一個對得上的段落，其餘丟掉；第二版改成逗號切段後每段都處理，但這會把含逗號的地點名稱切壞。**現行版本先對整個字串掃描已知的地點／區域名**（由長到短，名稱至少 6 個字元，命中的部分換成佔位再掃下一個），掃不到才退回逗號切段、逐段精確比對。掉落物對每個解析出的地點各建一條 `DROPS` 邊。靠掃描推得的邊 `match` 為 `substring`（Location）或 `region`（Region）
- **整串掃描命中後，剩下沒對上的字串被無聲丟掉（已調查並修正）**：`resolve_location` 只要掃到任何一個已知地點就直接回傳，剩下的字串不會建 stub、也不會記錄，沒做到計畫書「對不上的要記錄」的要求。2026-09-28 唯讀重現解析後的結果：`bosses.csv` 共 164 列、241 個地點欄 key，解析路徑分布為整串精確 170、區域精確 42、掃描 10、都沒對上而建 stub 19、逗號切段 0。**只有 4 個 key、3 種殘留文字受影響**；這 4 個 key 底下共 15 項掉落物，掉落物仍掛在解析出的地點上，沒有消失，只是少了被丟掉的那個地點：

  | boss（id）| 地點欄原文 | 解析出的地點 | 被丟掉的字串 |
  |---|---|---|---|
  | Messmer the Impaler（8）、Base Serpent Messmer（9）| `Shadow Keep , Specimen Storehouse` | Shadow Keep | `Specimen Storehouse` |
  | Jagged Peak Drake（34）| `Jagged Peak Foothills` | Jagged Peak（區域，`region`）| `Foothills` |
  | Patches（141）| `Murkwater Cave , Limgrave Liurnia Mt. Gelmir Volcano Manor The Shaded Castle` | The Shaded Castle、Murkwater Cave、Volcano Manor、Mt. Gelmir、Limgrave | `Liurnia` |

  **處理**（三種殘留文字都由使用者確認後修正）：
  - `Specimen Storehouse`：使用者確認是獨立地點。`locations.csv` 沒有它，所以建 Location stub（`LEFTOVER_PLACES`），Messmer 兩隻各連一條邊；那個 key 底下的 2 項掉落物也各多掛一份 `at_location='Specimen Storehouse'`。Base Serpent Messmer 這條邊的 `match` 是 `substring` 而不是 `stub`，因為 stub 已由前一列建立，後一列直接掃描命中，無害
  - `Jagged Peak Foothills`：使用者確認就是 `Foot of the Jagged Peak`。整串別名（`LOCATION_ALIASES`）優先於掃描，Drake 現在連到 Foot of the Jagged Peak（`match=alias`），不再因為先掃到 `Jagged Peak` 而連到較上層。`Jagged Peak` 只是區域、不是地點（上一版文件寫成 `substring` 是錯的）。`locations.csv` 本來就獨立列了 Drake 在 Foot of the Jagged Peak，所以這條由「只有 locations.csv」變成兩邊都有，資料自己支持這個裁決；Drake 另一個地點欄 `Jagged Peak` 仍連到 Jagged Peak 區域
  - `Liurnia`：使用者確認 Patches 在 Liurnia 也是 NPC。對到區域 `Liurnia of the Lakes`（區域節點的全名，`match=region`），依 `BOSS_ONLY_AT` 掛在 Patches 的 **NPC** 節點上，掉落物 9 項也跟著掛（Patches 的 NPC 現在 5 個地點各 9 條 `DROPS`）
  - 之後任何新的殘留字串都會記到 `graph_unmatched.csv`（`boss_location_leftover`），目前 0 筆
  - 調查只涵蓋 `bosses.csv` 的地點欄，因為在我讀過的 `build_graph.py` 裡只有這一處呼叫 `resolve_location`；`locations.csv` 各清單走的是 `resolve()`，對不上會建 stub，不受這個問題影響
- **兩個來源對 Boss↔地點的說法不一致**：`locations.csv` 每個地點有一欄 `bosses`，`bosses.csv` 每隻 boss 有一段地點文字，理論上是同一份關係的兩個方向，實際上並不一致。圖取聯集，並在 Boss 的 `LOCATED_AT` 邊上用 `sources` 標出哪個檔案有寫。唯讀稽核腳本 `src/graph/audit_boss_locations.py` 依 `sources` 分類（需先建圖）。

  **現況**：Boss 的 `LOCATED_AT` 共 312 條，其中 47 條指向 Region（312 − 265；只有 `bosses.csv` 會寫到區域層級，`locations.csv` 的 boss 清單沒有，所以不在比對範圍），其餘 **265 條**指向 Location。265 條的分類（有不一致的地點共 53 個）：

  | 類型 | 條數 | 意思 | 處理 | 例子 |
  |---|---|---|---|---|
  | 兩邊都有 | 183 | | | 對齊前是 143；現在 183 條中有 37 條是對齊補出來的（見上方 `sources` 的限制）。143 + 37 = 180，差 3 條：其中 1 條是 Jagged Peak Drake（`Foothills` 別名後兩邊都有），另外 2 條我沒有逐條追查 |
  | A2 | 54 | 只在 locations 清單；`bosses.csv` 有這隻 boss，但它的地點文字沒寫這個地點 | **未動**，待使用者檢視 | Gatefront Ruins ← Tree Sentinel |
  | 地點是 stub | 19 | 只在 bosses.csv；那個地點在 locations.csv 根本不存在（見下方 Location stub），所以必然單邊 | 不算真的不一致 | Ancient Ruins of Rauh ← Divine Beast Dancing Lion |
  | A1 剩餘 | 8 | 只在 locations 清單；`bosses.csv` 沒有這隻 boss 的列（建了 Boss stub）| 見下，**故意不補列** | Church of the Crusade ← Fire Knight Queelign |
  | B3 | 0 | 原本 5 條：只在 bosses.csv，地點是從黏在一起的多地點字串（或錯字容忍）推得 | 使用者逐條確認正確，已對齊（見下）| |
  | B4 剩餘 | 1 | 只在 bosses.csv；地點精確對上，但 locations 的 boss 清單沒列 | 見 B2 | Moorth Ruins ← Dryleaf Dane |

  **已套用的決定**（A1、B4、B3、B1、B2 是使用者的裁決；A1 的兩條例外規則是我延伸的，見下，使用者尚未逐一確認）：
  - **A1、B4：讓兩邊對齊**（資料層，`clean_raw.py`，`data/raw` 不動）。B4：`bosses.csv` 的地點 key 精確對上某個地點、但該地點的 `bosses` 清單沒列這隻 → 補進清單，共 **20 條**（例如 Magma Wyrm → Dragon's Pit、Ulcerated Tree Spirit → Belurat Tower Settlement／Leyndell 兩處）。A1：`locations.csv` 的 `bosses` 清單列了、但 `bosses.csv` 沒這隻 → 在 `bosses.csv` 補一列（`bosses.csv` 裡這一列只有名稱與地點；dlc 沿用地點的 dlc），共補 **9 列、10 條地點關係**（Swordhand of Night Anna／Jolan、Elden Beast、Elder Dragon Greyoll、Walking Mausoleum、Putrid Crystalians、Stray Mimic Tear、Lion Misbegotten Warrior、Nox Swordstress & Nox Priest）。A1 對齊後 A1 由 19 條降為 8 條
  - **B3：使用者逐條確認後，補進地點的 boss 清單**（`clean_raw.py` 的 `CONFIRMED_BOSS_LOCATIONS`，共 7 筆）。原 B3 的 5 條經使用者（玩過遊戲）確認都正確：Spiritcaller Snail @ Spiritcaller Cave（`bosses.csv` 拼成 `Spiritcaller's Cave`）、Mimic Tear @ Hidden Path to the Haligtree（我原本懷疑可能是把兩隻混在一起，使用者確認是對的）、Messmer the Impaler 與 Base Serpent Messmer（兩個階段）@ Shadow Keep。另外使用者確認 Golem 那串（`Stormhill Castle Morne Ainsel River Well Leyndell, Royal Capital Mountaintops of the Giants`）的**每個地點都有 Golem**，所以補進 Stormhill、Castle Morne、Ainsel River Well 三處的 boss 清單（Leyndell, Royal Capital 原本就有；Mountaintops of the Giants 在 locations.csv 只是區域、沒有地點列，邊本來就在）。這與 A1、B4 的補法相同；三者合計 37 條關係是對齊補出來的（「兩邊都有」由 143 變成 183，數字對不上的部分見上方現況表）
  - **A1 有 9 個名稱刻意跳過**（記在 `alignment_changes.csv`，kind 為 `A1_skipped_*`）：其中 8 個在 `npcs.csv` 或 `creatures.csv` 已有同名（或別名、或逗號前的名字）的實體——Furnace Golem、Mad Tongue Alberich、Preceptor Miriam、Chief Guardian Arghanthy、`Soldier of Godrick`（別名 Godrick Soldier）是 creature，Fire Knight Queelign、`Ensha`（別名 Ensha of the Royal Remains）、Gurranq（`Gurranq, Beast Clergyman`）是 NPC。這是我把使用者對 B1、B2 的裁決（creature 分類是對的；同時是 NPC 又是 boss 屬特例）延伸過來的判斷：不替它們新增 Boss 列，所以圖裡仍是 Boss stub。若使用者認為其中某幾個應該補 Boss 列，要在 `clean_raw.py` 的 `align_boss_locations()` 為它們開例外（目前是依名稱規則判斷，沒有可編輯的清單）。另 1 個是 `Perfumer Tricia`，它是 `bosses.csv` 合併列 `Perfumer Tricia and Misbegotten Warrior` 的一員，補列會重複，改用別名指到那一列（因為那一列的地點文字沒寫 Unsightly Catacombs，這條落在 A2）
  - **B1：`locations.csv` 列為 creature 的，不建 Boss 邊**（使用者確認 creature 分類是對的）。建圖時，若 `bosses.csv` 說某 boss 在某地點，但該地點的 `creatures` 清單有它的名字、`bosses` 清單沒有，就略過這條 Boss 邊，記為 `boss_is_creature_here`，共 **5 條**：Valiant Gargoyle @ Leyndell, Ashen Capital（2 列）、Lion Guardian @ Castle Sol、Putrid Avatar @ Elphael Brace of the Haligtree、Putrid Tree Spirit @ Grand Cloister。這些名稱在 `bosses.csv` 有自己的列，所以仍是 Boss 節點，只是不再連到這 5 個地點。**Golem 是使用者確認的例外**：原本 Golem @ Stormhill、Golem @ Ainsel River Well 也在略過清單（`locations.csv` 把 Golem 列在這兩處的 creatures），共 7 條；使用者確認那串每個地點都有 Golem，所以把 Golem 補進這兩處的 boss 清單（見 B3 那條），B1 的條件（「bosses 清單沒有它」）不再成立，兩條邊與它們的掉落物（`DROPS` +10）恢復。這兩處的地點列現在 Golem 同時出現在 creatures 與 bosses 兩欄
  - **B2：Dryleaf Dane 維持原樣**（使用者確認屬特例）：`bosses.csv` 把它當 boss 記在 Moorth Ruins，`locations.csv` 把它列成 npc，兩邊都留著，稽核顯示為剩下的那 1 條 B4，與 Patches 同屬「同一角色雙重身分」

  **注意**：A2 中有一部分不是真的矛盾。以固定隨機種子抽樣 10 條，4 條是 `bosses.csv` 的地點欄本來就是空的（資料缺漏），5 條依我的判斷是上下層級關係（區域對地點、大地點對子區域，例如 Astel 在 `bosses.csv` 寫 Grand Cloister、`locations.csv` 寫 Lake of Rot；Godfrey 在 `bosses.csv` 寫 Leyndell, Ashen Capital、`locations.csv` 寫 Elden Throne），1 條不確定（Regal Ancestor Spirit 的 Hallowhorn Grounds／Nokron），沒有看到真正互相矛盾的。全部 54 條尚未逐一檢視

  **對題庫的影響**：題庫裡 7 題「某地點有哪些 boss」（q06、q59–q64），對齊後在圖上實測：6 題與標準答案一致，只有 **q60**（Belurat Tower Settlement）不同——標準答案只有 Divine Beast Dancing Lion，圖多回傳 Ulcerated Tree Spirit。這條的獨立證據只有 `bosses.csv`（B4 對齊才把它補進 `locations.csv` 的清單，見上方 `sources` 的限制），而題庫標準答案是取自對齊前的 `locations.csv`。**使用者依遊戲知識確認 Belurat Tower Settlement 確實有 Ulcerated Tree Spirit，所以 q60 的標準答案已改為兩隻**（`eval/questions.jsonl`），現在 7 題都與圖一致。兩個向量基準線對 q60 已重判為 partial（原 correct，重判者為 Claude、非人工），分數見 `docs/local_run.md`、`docs/run_haiku.md`。另外逐題掃描其他提到被動過實體的 9 題（q06、q53、q65、q69、q78、q90、q96、q97、q99），標準答案都沒有被波及
- **同一個角色依地點有不同身分（Patches）**：`bosses.csv` 把 Patches 當 boss（HP 1,191），並把他在多個地點的資料黏成一串；`locations.csv` 則只在 Murkwater Cave 的 `bosses` 欄位列他，在 Volcano Manor、The Shaded Castle 只列在 `npcs`。經使用者（玩過遊戲）確認：**Patches 在 Murkwater Cave 是 boss，在其他地點是 NPC**。處理：`build_graph.py` 的 `BOSS_ONLY_AT` 設定，讓該列的 boss 身分（HP、地點、掉落）只保留在 Murkwater Cave，其他地點（Volcano Manor、The Shaded Castle、Limgrave、Mt. Gelmir）改掛在同名的 NPC 節點上。因此 q06（Volcano Manor 有哪些 boss）圖回傳的就是標準答案 5 隻。這是逐案確認的特例，沒有套用到其他角色
- **`bosses.csv` 缺列**：`Elden Beast`、`Hoarah Loux, Warrior`、`Fire Knight Queelign`、`Swordhand of Night Anna` 等在 locations.csv 或 remembrances.csv 被明確列為 boss，卻沒有自己的列。建圖第一版共建了 23 個 Boss stub；A1 對齊在 `bosses.csv` 補了 9 列後，**剩 13 個 Boss stub**：4 個是 boss_stats 有數值、bosses.csv 沒有的（`Beast Clergyman`、`Elder Lion`、`Ghostflame Dragon`、`Leda and Allies Boss`），建 stub 並掛上數值，標 `dlc_unknown`（boss_stats 沒有 dlc 欄位）；8 個是 A1 刻意跳過的（`npcs.csv`／`creatures.csv` 已有同名實體，見上）；1 個是 remembrances.csv 來的 `Hoarah Loux, Warrior`。A1 補的那 9 列 `hp` 都是空的（bosses.csv 沒有這些欄位）；其中 `Elden Beast`、`Putrid Crystalians` 有對上 boss_stats（掛 `bs_*`），其餘 7 列沒有任何數值
- **掉落物欄位混有雜訊**：符文範圍（`40 - 1020 Runes`）、表格殘渣（`Stormveil Castle : 1,176`）、`Map Link`、`NPCs`、`???`、`To be added`、`N/A` 等，共 251 筆被略過（符文範圍 150、其餘雜訊 101）
- **`locations.csv` 缺少 boss 資料引用的地點**：共 12 個，建了 Location stub：`Ancient Ruins of Rauh`、`Church District`、`Church of the Bud`、`Crumbling Farum Azula`、`Ellac River`、`Hinterland`、`Recluses' River`、`Scadutree Base`、`Scenic Isle`、`Specimen Storehouse`（Shadow Keep 內的獨立地點，使用者確認）、`Stone Platform`、`Three Sisters`

## 孤立節點（807 個，21%）

沒有任何邊的節點。這不是 bug，是來源資料本來就沒有結構化的關係：

| 標籤 | 孤立數 | 原因 |
|---|---|---|
| Item | 316 | 沒有任何 boss／creature 掉落、也沒出現在任何地點的物品清單。同名 Item 合併前是 356，少的 40 個是被併掉的孤立重複節點（總數 847 → 807，被併掉的 41 個裡只有 1 個原本有邊；其他標籤沒有變，所以這格是推算，沒有逐標籤重數）|
| Armor | 288 | 取得方式在 `how_to_acquire` 自由文字裡，沒有結構化 |
| Spell | 93 | 取得地點在 `location_text` 自由文字裡 |
| Talisman | 42 | 同上，沒有結構化的取得關係 |
| NPC | 42 | 不在任何地點的 `npcs` 清單裡（npcs.csv 的 `location` 是自由文字，沒採用）|
| 其他 | 26 | SpiritAsh 13、Boss 4、Creature 4、Skill 3、Shield 1、AshOfWar 1 |

日後若要提升覆蓋率，可以解析 `how_to_acquire`／`location_text` 這兩個自由文字欄位，但這需要文字抽取，超出「只用結構化欄位」的範圍。

## 已驗證的路徑（在 Neo4j 用 Cypher 實查）

| 題 | 查詢 | 結果 |
|---|---|---|
| q07 | Volcano Manor ← Boss → DROPS → greatRunes | `Rykard's Great Rune` ✓ |
| q72 | Malenia → DROPS → 紀念品 → EXCHANGES_FOR | `Hand of Malenia`（Weapon）、`Scarlet Aeonia`（Spell）✓ |
| q09 | Rykard、Malenia 的 `hp` | 89613、33251 ✓ |
| q08 | 圓桌廳同時是 NPC 又是 Boss | `Ensha of the Royal Remains` ✓ |
| q96 | Sir Gideon Ofnir 的戰鬥地點 | `Leyndell, Ashen Capital` ✓ |
| Magma Wyrm | 各地點的符文與掉落 | Fort Laiedd 19000／Gael Tunnel 7500（掉 Moonveil）／Dragon's Pit 7718／Volcano Manor 5044 ✓ |
| q06 | Volcano Manor 的 boss | Abductor Virgins、God-Devouring Serpent、Godskin Noble、Magma Wyrm、Rykard，共 5 隻，與標準答案一致 ✓ |
| q60 | Belurat Tower Settlement ← Boss | Divine Beast Dancing Lion、Ulcerated Tree Spirit（兩者 `sources` 都是兩邊都有）；標準答案已更新為兩隻，與圖一致 ✓（見上方「對題庫的影響」）|
| q59、q61–q64 | 各地點的 Boss | Death Knight、Beastman of Farum Azula、Erdtree Burial Watchdog（Impaler's／Cliffbottom 各一）、Demi-Human Queen Gilika，皆與標準答案一致 ✓ |
| Stray Mimic Tear | A1 新增列的地點 | Forbidden Lands、Hidden Path to the Haligtree，兩者都是兩邊都有 ✓（初版 A1 只記到第一個地點，已修）|
| 被丟字串的三隻 boss | Messmer 兩隻、Jagged Peak Drake、Patches | Messmer 各連 Shadow Keep 與 Specimen Storehouse（stub）；Drake 連 Foot of the Jagged Peak（兩邊都有）與 Jagged Peak 區域；Patches 的 NPC 連 Liurnia of the Lakes 等 5 處，各 9 條掉落 ✓ |
| Patches | `bosses.csv` 多地點字串解析＋依地點分身分 | Boss：僅 Murkwater Cave（HP 1,191、含掉落）；NPC：Murkwater Cave、Volcano Manor、The Shaded Castle、Limgrave、Mt. Gelmir、Liurnia of the Lakes ✓ |

## 待決定

1. **stub 節點去留**：232 個 stub 沒有屬性，只有名稱與來源；優點是讓題庫的標準答案（取自 locations.csv 清單）在圖裡有對應節點，缺點是稀釋了「資料實際知道的實體」。建議保留，需要時用 `stub` 屬性過濾
2. **Boss↔地點剩下的不一致**：A1、B4、B3、B1、B2 已依使用者裁決處理（見上）。**A2（55 條）等使用者逐條檢視**，目前未動。S4 的查詢工具是否要提供依 `sources` 篩選（例如只信兩邊都有的）待決定
3. **向量索引與基準線與現在的資料不同步**：資料對齊後語料庫已重建為 3649 篇（原 3640 篇，A1 新增 9 篇 boss 文件，且 17 個地點的 boss 清單因 B4 而變了），但 `data/processed/vector_index/` 是用舊語料建的，兩個向量基準線（Qwen3.5-4B、Claude Haiku 4.5）的結果也是用舊索引跑的（q60 的判分已依新標準答案重判，其他題沒動）。要在 S6 公平比較圖檢索與向量檢索，需要重啟 bge 服務、重建索引，並決定是否重跑兩個基準線
4. `Rellana's Twinblade`（remembrances.csv）與 `Rellana's Twin Blades`（weapons.csv）拼法不同，目前是一個 Weapon stub 加一個真實節點，尚未處理
5. 177 個 `Boss` 中只有 105 個的 `hp` 能 parse 成單一數字（含空值、多階段、約略值加註記等格式的保留在 `hp_raw`）；148 個有掛上 boss_stats 的數值
6. 同一個角色在不同檔案分屬不同類別（例如 `Ensha` 既是 NPC 也是 boss stub、`Godefroy the Grafted` 同時有 NPC 與 Boss），目前是各自獨立的節點，沒有 `SAME_AS` 關係。A1 刻意跳過的 8 個名稱（Ensha、Fire Knight Queelign、Gurranq、Furnace Golem 等）也是這種情況
7. 別名 `Perfumer Tricia`→`Perfumer Tricia and Misbegotten Warrior` 是我判斷的，未經使用者確認
8. **5 個紀念品節點的名稱黏字**（S4 挖出來的）：`Remembrance of theBlasphemous`、`theLichdragon`、`theNaturalborn`、`theStarscourge`、`theDragonlord`，來源檔 `remembrances.csv` 的名稱本來就少了空格。建圖的 `norm()` 會修這類黏字所以比對沒問題，但節點名稱保留原樣，查詢工具會原樣回傳。**使用者決定不修**（2026-09-28），只記錄；同一次掃描的其他黏字與修正見 `docs/note.md`「黏字」一節
9. **同名 Item 節點（已合併 41 組，2 組待決定）**（S4 挖出來的）：實際是 43 組、87 個節點（見上方「同名 Item 合併」）。使用者決定合併，已實作；`Lord of Blood's Favor`（2 份）與 `Unalloyed Gold Needle`（3 份）是同名但不同任務狀態的物品，**沒有合併，待使用者判斷**。原本的重複主要在 `consumables.csv` 與 `remembrances.csv`（9 組）、`tools.csv` 之間。抽看的一組中，`consumables.csv` 的那份沒有任何邊，關係都在 `remembrances.csv` 那份，多半是孤立的重複節點。Larval Tear 兩份的 `dlc` 標記不一致（1 與 0），使用者確認它是本篇（`dlc=0`），已在 `clean_raw.py` 把 `keyItems.csv` id=6 改為 0（見 `docs/note.md`）；已合併。詳見 `docs/graph-tools.md`
10. **語料庫還沒去重**（同名 Item 合併的後續）：語料庫 `corpus.jsonl` 是每個 CSV 列一篇文件，這次合併只動了圖，向量索引裡同名的仍是兩篇（41 篇重複）。題庫的 `source` 沒有指到會被去掉的那一列，所以去重不影響 recall 的比對。要不要去重、被去掉的文件的欄位（例如 `consumables.csv` 那份的 `effect`）要不要併進保留的文件，待決定。向量索引本來就要重建，同時做最省事
11. **同一對節點之間有兩條同類型的邊**（S4 挖出來的）：例如 Malenia → Remembrance of the Rot Goddess 有兩條 `DROPS`，一條來自 bosses.csv 的掉落物字串、一條來自 remembrances.csv 的 `boss` 欄。`get_neighbors` 會把同一個鄰居列兩次。是否合併成一條（`sources` 記兩個來源，與 Boss↔地點的做法一致）待決定