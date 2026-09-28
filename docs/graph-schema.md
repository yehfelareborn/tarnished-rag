# 知識圖譜 Schema（S3）

狀態：**已建圖**（2026-09-28）。Neo4j Community 2026.09.0，資料來源為 `data/processed/dlc_scrape/`（沒有處理版的檔案退回 `data/raw/`）與 `data/raw/boss_stats/`。建圖腳本 `src/graph/build_graph.py`，每次執行會清空資料庫重建（約 4 秒，結果可重現）。

原則：只用結構化欄位建圖，不用 LLM 抽取；每個節點與邊都帶 `source_file`（邊多帶來源欄位資訊）；所有節點帶 `dlc`（0／1）。所有節點另掛一個共用標籤 `Entity`，有唯一 `uid` 與 `name` 索引。

## 節點（共 3891 個，其中 228 個是 stub）

| 標籤 | 節點數 | 其中 stub | 來源 | 主要屬性 |
|---|---|---|---|---|
| `Item` | 965 | 131 | items/*.csv 的 13 個子類 | `item_type`（子類名）、effect、description、usage 等該子類有的欄位 |
| `Armor` | 723 | 0 | armors.csv | slot、weight、damage_negation、resistance、special_effect、how_to_acquire |
| `Weapon` | 403 | 1 | weapons.csv | category、damage_type、weight、passive_effect、skill、`str/dex/int/fai/arc`（由 `requirements` 拆開）|
| `Location` | 298 | 12 | locations.csv | description |
| `Skill` | 261 | 4 | skills.csv | skill_type、equipment、charge、fp、effect |
| `Creature` | 249 | 44 | creatures.csv | blockquote |
| `Spell` | 214 | 1 | sorceries.csv、incantations.csv | school、effect、fp、slot、`int/fai/arc`、location_text |
| `Boss` | 178 | 23 | bosses.csv ＋ boss_stats | hp_raw、hp（能 parse 成單一數字才有）、`bs_*`（boss_stats 的減免、抗性、韌性等）|
| `Talisman` | 155 | 0 | talismans.csv | effect、weight、value |
| `NPC` | 121 | 12 | npcs.csv | role、voiced_by |
| `AshOfWar` | 117 | 0 | ashesOfWar.csv | affinity、skill |
| `Shield` | 100 | 0 | shields.csv | 同 Weapon |
| `SpiritAsh` | 84 | 0 | spiritAshes.csv | spirit_type、fp_cost、hp_cost、effect |
| `Region` | 23 | 0 | locations.csv 的 `region` 欄 | name |

已確認的設計選擇：
- **Item 不依子類拆標籤**，13 個子類統一為 `Item`，以 `item_type` 屬性區分
- **Boss 與 Creature 分開**
- **Region 是節點**（不是 Location 的屬性）
- **符文數放 `LOCATED_AT` 邊、掉落物在 `DROPS` 邊上標 `at_location`**：因為 boss 有多個戰鬥地點時，每個地點的符文與掉落都不同（例如 Magma Wyrm 在 4 個地點各有不同的符文與掉落物），放在節點會蓋掉差異

## 邊（共 6503 條）

| 關係 | 條數 | 方向 | 來源欄位 | 邊上的屬性 |
|---|---|---|---|---|
| `LOCATED_AT` | 4328 | Boss／NPC／Creature／物品類 → Location（或 Region）| bosses.csv `Locations & Drops` 的 key；locations.csv 的 `bosses`／`npcs`／`creatures`／`items` 清單 | `source_file`、`runes`（僅 Boss，共 215 條有值）、`match`（exact／part／substring／region／stub／from_location_list）、`note` |
| `DROPS` | 1220 | Boss／Creature → 物品類 | bosses.csv 每個地點 key 底下的 list；creatures.csv `drops`；remembrances.csv 的 `boss` | `at_location`（354 條有值）、`note`（例如 `via set: X Set`、`stub`）|
| `HAS_SKILL` | 500 | Weapon／Shield → Skill | weapons.csv／shields.csv `skill` | |
| `LOCATED_IN` | 286 | Location → Region | locations.csv `region` | |
| `GRANTS` | 116 | AshOfWar → Skill | ashesOfWar.csv `skill` | |
| `EXCHANGES_FOR` | 53 | 紀念品（Item）→ Weapon／Spell／Talisman／AshOfWar／Item | remembrances.csv `option 1`／`option 2`（用型別前綴決定目標標籤）| `option`（1／2）|

能力需求存在 Weapon／Spell 的屬性上，不做成邊；`filter_by_attribute` 直接篩屬性。

## 名稱比對（entity resolution）

跨檔案靠名稱把 list 裡的字串接到節點。比對順序，前面命中就停：

1. **精確**：正規化後相等（小寫、去標點與撇號、去重音、修 `theBlasphemous` 這類黏字）
2. **清理後精確**：對候選字串做明確的清理再精確比對——去 HTML 實體、去頭尾數量（`12x X`、`X x5`、`x1 X`）、去尾端括號註解（`(NG Only)`、`(6)`、`(+8)`、任意長度括號）、去 `Gateway:` 這類短前綴、去 `Ashes` 後綴（召喚靈）、`+N` 補成 `+N Variant`（護符）
3. **別名表**（後備，精確比對優先）：共 18 組。前 7 組依遊戲知識判斷為同一實體（Morgott、Rennala 的 boss 全名、`Nepheli Loux`、`Count Ymir`、`War Counselor Iji`、`Shaded Castle Spirit`、`Soldier of Godrick`，**待你確認**）；其餘為 NPC 簡稱，逐一對照過 npcs.csv 的實際名稱（`Fia`、`Blaidd`、`Diallos`、`Corhyn`、`Ansbach`、`Boc`、`Alexander`、`Yura`、`Rennala`、`Ranni the Witch`、`Ensha`）
4. **去空白**：補空白或撇號黏合的差異（`Wolf s Assault` → `Wolf's Assault`）
5. **錯字容忍**（僅在建 stub 之前，僅限 Boss／NPC／Creature／Location）：相似度 ≥ 0.93、數字完全相同、且只有一個候選。實際合併 26 次，多為單複數（`Teardrop Scarab`／`Scarabs`），加上 `Black Knight Edreed`／`Edredd`
6. **建 stub**：以上都對不上，但資料裡確實有明確提到，就建只有名稱與來源、標記 `stub=true` 的節點，全部列在 `data/processed/graph_stubs.csv`

**曾試過但拿掉的規則**：「名稱互相包含」的泛用比對，會把 `X` 連到 `Lesser X`、`Somber Smithing Stones` 連到 `Smithing Stones`、`Fire Knight Queelign`（有名字的角色）連到泛稱的 `Fire Knight`，誤連約 25 對，所以移除。

稽核用的輸出：
- `data/processed/graph_fuzzy_matches.csv`：所有靠清理／別名／去空白／錯字容忍成功的比對（142 次）
- `data/processed/graph_stubs.csv`：所有 stub
- `data/processed/graph_unmatched.csv`：未命中與欄位污染記錄（38 筆）

## 建圖過程發現的資料問題

- **`locations.csv` 的 `npcs`／`creatures` 欄位混進物品**：至少出現在 Murkwater Catacombs、Stormfoot Catacombs、Seethewater Cave、Sealed Tunnel、Bestial Sanctum、Uhl Palace Ruins 等地點（共 37 筆）。判斷方式：名稱對不上該欄位的實體，但能對到物品，或出現在別處的物品清單裡。處理：改成「該物品位於此地點」的 `LOCATED_AT`，不建假 NPC。另有 22 筆是實體放錯欄位（例如 creatures 欄位裡的 NPC），改連到正確的實體
- **兩個來源對 Boss↔地點的說法不一致**：兩邊都有 133 條、只在 bosses.csv 36 條、只在 locations.csv 的 boss 清單 77 條，172 個有 boss 資料的地點中 79 個不一致。圖取聯集並在邊上標來源。**會影響題庫**：q06（Volcano Manor 有哪些 boss）圖回傳 7 隻，標準答案只有 5 隻（多出 `Bloodhound Knight`、`Omenkiller`，只在 bosses.csv 寫）
- **`bosses.csv` 缺列**：`Elden Beast`、`Hoarah Loux, Warrior`、`Fire Knight Queelign`、`Swordhand of Night Anna` 等在 locations.csv 或 remembrances.csv 被明確列為 boss，卻沒有自己的列，共建了 23 個 Boss stub。其中 4 個是 boss_stats 有數值、bosses.csv 沒有的（`Elder Lion`、`Ghostflame Dragon` 等），建 stub 並掛上數值，這幾個標 `dlc_unknown`（boss_stats 沒有 dlc 欄位）
- **掉落物欄位混有雜訊**：符文範圍（`40 - 1020 Runes`）、表格殘渣（`Stormveil Castle : 1,176`）、`Map Link`、`NPCs`、`???`、`To be added`、`N/A` 等，共 251 筆被略過（符文範圍 150、其餘雜訊 101）
- **`locations.csv` 缺少 boss 資料引用的地點**：`Crumbling Farum Azula`、`Ancient Ruins of Rauh`、`Recluses' River`、`Church of the Bud`、`Stone Platform`、`Three Sisters` 等 12 個，建了 Location stub

## 孤立節點（847 個，22%）

沒有任何邊的節點。這不是 bug，是來源資料本來就沒有結構化的關係：

| 標籤 | 孤立數 | 原因 |
|---|---|---|
| Item | 356 | 沒有任何 boss／creature 掉落、也沒出現在任何地點的物品清單 |
| Armor | 288 | 取得方式在 `how_to_acquire` 自由文字裡，沒有結構化 |
| Spell | 93 | 取得地點在 `location_text` 自由文字裡 |
| Talisman | 42 | 同上，沒有結構化的取得關係 |
| NPC | 41 | 不在任何地點的 `npcs` 清單裡（npcs.csv 的 `location` 是自由文字，沒採用）|
| 其他 | 27 | SpiritAsh 13、Boss 5、Creature 4、Skill 3、Shield 1、AshOfWar 1 |

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
| q06 | Volcano Manor 的 boss | **7 隻，標準答案 5 隻**（見上方資料問題）|

## 待決定

1. **別名表前 7 組**是否正確（依遊戲知識判斷）
2. **stub 節點去留**：228 個 stub 沒有屬性，只有名稱與來源；優點是讓題庫的標準答案（取自 locations.csv 清單）在圖裡有對應節點，缺點是稀釋了「資料實際知道的實體」
3. **Boss↔地點不一致怎麼算**：以哪個來源為準，或題庫 q06 這類標準答案是否要補上 bosses.csv 才有的 boss
4. `Rellana's Twinblade`（remembrances.csv）與 `Rellana's Twin Blades`（weapons.csv）拼法不同，目前是一個 Weapon stub 加一個真實節點，尚未處理
5. 178 個 `Boss` 中只有 105 個的 `hp` 能 parse 成單一數字（含空值、多階段、約略值加註記等格式的保留在 `hp_raw`）；148 個有掛上 boss_stats 的數值
