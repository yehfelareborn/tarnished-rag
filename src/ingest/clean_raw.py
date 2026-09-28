"""S0 掃出的已知 raw data 問題清理，輸出到 data/processed/dlc_scrape/。

不直接改 data/raw/（保持原始下載檔案不變，方便追溯/重跑），
清理後的版本寫到 data/processed/ 供後續 ingest 使用。

已知問題來源：docs/data-sources.md「抽樣校驗」與「待辦」章節。
"""
import ast
import csv
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "dlc_scrape"
OUT = Path(__file__).resolve().parents[2] / "data" / "processed" / "dlc_scrape"


def normalize_dlc_flag(src_name: str) -> int:
    """armors.csv / incantations.csv: dlc 欄位用文字 "Base Game" 取代 "0"，改回 "0"。"""
    src = RAW / src_name
    dst = OUT / src_name
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    changed = 0
    for row in rows:
        if row["dlc"] not in ("0", "1"):
            row["dlc"] = "0"
            changed += 1

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{src_name}: normalized {changed} rows with non-binary dlc value -> '0'")


def fix_consumables() -> None:
    """items/consumables.csv 的 Golden Rune 系列問題：

    1. [1]/[2]/[10]：原始檔案裡 description 欄位中間有一個沒有跳脫的逗號，
       把句子切成兩半，後半段連同真正的 dlc 值一起被擠出、蓋掉了 dlc 欄位。
       這裡把兩段 description 用逗號接回去，dlc 依使用者確認改回 "0"。
    2. [3] 的 name 欄位多了雜訊字元 " 3"，一併清掉。
    3. [5] 整筆從原始檔案裡消失，使用者確認效果是「Use to gain 1600 runes」，
       依其他筆的規律補回一筆。description 是用同系列的固定開頭句式重建，
       不是原始爬蟲文字，之後如果找到原文要替換掉。
    """
    src = RAW / "items" / "consumables.csv"
    dst = OUT / "items" / "consumables.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)

    broken_ids = {"92", "93", "140"}  # Golden Rune [1], [2], [10]

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    fixed = 0
    for row in rows:
        if row["id"] in broken_ids:
            row["description"] = row["description"] + "," + row["dlc"]
            row["dlc"] = "0"
            fixed += 1
        if row["name"].strip() == "Golden Rune [3] 3":
            row["name"] = "Golden Rune [3]"
            fixed += 1

    next_id = str(max(int(r["id"]) for r in rows) + 1)
    rows.append({
        "id": next_id,
        "name": "Golden Rune [5]",
        "image": "http://eldenring.wiki.fextralife.com/file/Elden-Ring/golden_rune_5_elden_ring_wiki_guide_200px.png",
        "effect": "Use to gain 1600 runes",
        "FP cost": "0",
        "description": "Grace that dwells within the inhabitants of the Lands Between; "
                        "the lingering trace of gold. Use to gain 1600 runes. "
                        "[重建值，非原始爬蟲文字，待覆核]",
        "dlc": "0",
    })
    fixed += 1

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"items/consumables.csv: fixed {fixed} rows (Golden Rune column-shift + name noise + [5] restored)")


def fix_key_items() -> None:
    """items/keyItems.csv 的 Imbued Sword Key (id=18)：
    dlc 欄位原值是髒資料字串 "Base game & Shadow of the Erdtree DLC"，
    使用者確認這是本篇道具，改回 "0"。
    """
    src = RAW / "items" / "keyItems.csv"
    dst = OUT / "items" / "keyItems.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    fixed = 0
    for row in rows:
        if row["id"] == "18":
            row["dlc"] = "0"
            fixed += 1

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"items/keyItems.csv: fixed {fixed} row (Imbued Sword Key dlc -> '0')")


# id -> 使用者確認的正確 HP 字串（沿用檔案其他多階段 boss 的既有格式：
# "<數字> (phase N) <數字> (phase N+1) ..."）
HP_FIXES = {
    # Base Serpent Messmer = Messmer the Impaler 進入第二階段的蛇形態，
    # 原值是佔位字串 "TBD"。使用者：Phase 1 (Messmer the Impaler) 滿血 38,981，
    # Phase 2 (Base Serpent Messmer) 在血量掉到約 50% (≈19,490) 時開始。
    "9": "19,490 (phase 2 of Messmer the Impaler, ≈50% of 38,981 total)",
    # Rennala 原值是誤植的欄位標題文字 "Phase 1"。
    # 使用者：Phase 1 (盾牌/解謎階段) 3,493 HP，Phase 2 (真正戰鬥) 4,097 HP。
    "14": "3,493 (phase 1) 4,097 (phase 2)",
}

# 抽樣＋地點交叉驗證（拿 locations.csv 裡 dlc=1 的地點/region 名單去比對）
# 發現這些 id 的 dlc 誤標成 "0"，但地點欄位列出的地點全部都是 DLC 專屬區域
# （沒有混到任何本篇地點，跟 Death Rite Bird/Fallingstar Beast/Magma Wyrm 那種
#  本篇就有、只是也會在 DLC 重複出現的雜兵型 boss 不同，所以判定是誤標）
DLC_FLAG_FIXES = {
    "0": "1",   # Divine Beast Dancing Lion: Belurat / Ancient Ruins of Rauh
    "7": "1",   # Metyr, Mother of Fingers: Finger Ruins of Miyr
    "9": "1",   # Base Serpent Messmer: Shadow Keep
    "29": "1",  # Ancient Dragon-Man: Dragon's Pit
    "30": "1",  # Chief Bloodfiend: Rivermouth Cave
    "31": "1",  # Dancer of Ranah: Southern Nameless Mausoleum
    "33": "1",  # Golden Hippopotamus: Shadow Keep / Charo's Hidden Grave / Ancient Ruins of Rauh 等
    "34": "1",  # Jagged Peak Drake: Jagged Peak
    "52": "1",  # Black Knight Garrew: Fog Rift Fort
    "54": "1",  # Count Ymir, Mother of Fingers: Cathedral of Manus Metyr
    "56": "1",  # Death Knight: Fog Rift Catacombs / Scorpion River Catacombs（只有這筆，沒有本篇版本）
    "61": "1",  # Lamenter: Lamenter's Gaol
    "63": "1",  # Rakshasa: Eastern Nameless Mausoleum
    "64": "1",  # Red Bear: Northern Nameless Mausoleum
}

# 同一隻 boss 在 Locations & Drops 裡列了多個地點，且是玩法不同的獨立戰鬥
# （不是同一場戰鬥的多個掉落點），拆成多個 boss 節點，一個地點一筆
SPLIT_MULTI_ENCOUNTER_IDS = {
    "39",  # Margit, the Fell Omen: Stormveil Castle（選配戰）/ Capital Outskirts（強制戰，Evergaol）
    "0",   # Divine Beast Dancing Lion: Belurat, Tower Settlement（初戰）/ Ancient Ruins of Rauh（強化重戰）
}


def fix_locations() -> None:
    """locations.csv 的 bosses/npcs 欄位污染，S1 出題時抽樣才發現：

    1. Castle Ensis (id=4)：bosses 欄位放了兩個掉落物名稱（"Rellana's Cameo",
       "Spelldrake Talisman"，這兩個本來就已經在 items 欄位裡，不會遺失資料），
       真正的 boss 名稱 "Rellana, Twin Moon Knight" 反而被放進 npcs 欄位。
       修正：bosses 改成真正的 boss，npcs 清空（沒有其他 npc 資料可用）。
    2. Leyndell, Royal Capital (id=230) / Ainsel River (id=270)：bosses 欄位放的
       是子地點名稱（例如 "Sealed Tunnel"、"Nokstella, Eternal City"），不是 boss
       名稱。改用 bosses.csv 自己的 "Locations & Drops" 欄位反查——只要某隻 boss
       的地點字串包含這個地點名稱（或其子地點名稱），就算是這個地點的 boss，
       重建出正確清單。部分子地點（Minor Erdtree Church、Divine Tower of West
       Altus）在 bosses.csv 裡完全查不到對應的 boss，資料本來就沒有，不強行補。
    """
    src = RAW / "locations.csv"
    dst = OUT / "locations.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    fixed = 0
    for row in rows:
        if row["id"] == "4":  # Castle Ensis
            row["bosses"] = repr(["Rellana, Twin Moon Knight"])
            row["npcs"] = repr([])
            fixed += 1
        elif row["id"] == "230":  # Leyndell, Royal Capital
            row["bosses"] = repr([
                "Morgott, The Grace-Given Veiled Monarch Omen King",
                "Valiant Gargoyle",
                "Erdtree Avatar",
                "Golem",
                "Godfrey, First Elden Lord (Golden Shade)",
                "Lion Guardian",
                "Onyx Lord",  # 子地點 Sealed Tunnel
                "Mohg, the Omen",  # 子地點 Subterranean Shunning-Grounds
                "Esgar, Priest of Blood",  # 子地點 Leyndell Catacombs
            ])
            fixed += 1
        elif row["id"] == "270":  # Ainsel River
            row["bosses"] = repr(["Dragonkin Soldier of Nokstella", "Golem"])
            fixed += 1

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"locations.csv: fixed {fixed} rows (bosses/npcs field contamination)")


def fix_creatures() -> None:
    """creatures.csv 的 Aging Untouchable (id=12)：
    地點欄位只有 'Abyssal Woods'（DLC 專屬地點，圖檔檔名也直接寫 "sote"），
    但 dlc 誤標成 "0"，改成 "1"。
    """
    src = RAW / "creatures.csv"
    dst = OUT / "creatures.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    fixed = 0
    for row in rows:
        if row["id"] == "12":
            row["dlc"] = "1"
            fixed += 1

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"creatures.csv: fixed {fixed} row (Aging Untouchable dlc -> '1')")


def fix_bosses() -> None:
    """bosses.csv 的三個修正，讀一次寫一次：

    1. HP 佔位/誤植字串修正（見 HP_FIXES）。
    2. dlc 誤標修正（見 DLC_FLAG_FIXES）。
    3. 同一 boss、多個獨立戰鬥地點的拆分成多個節點（見 SPLIT_MULTI_ENCOUNTER_IDS）。
       拆分後每筆沒有各自的 HP 數據，先沿用同一個原始 HP 值。
       （Morgott, the Omen King 在原始資料裡本來就是獨立一列 id=16，不受影響。）
    """
    src = RAW / "bosses.csv"
    dst = OUT / "bosses.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)

    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    hp_fixed = 0
    dlc_fixed = 0
    for row in rows:
        if row["id"] in HP_FIXES:
            row["HP"] = HP_FIXES[row["id"]]
            hp_fixed += 1
        if row["id"] in DLC_FLAG_FIXES:
            row["dlc"] = DLC_FLAG_FIXES[row["id"]]
            dlc_fixed += 1
        if row["id"] == "34":  # Jagged Peak Drake: 地點欄位其中一個 key 混了 HTML 標籤
            row["Locations & Drops"] = row["Locations & Drops"].replace(
                '<a class="wiki_link" href="/Jagged+Peak" title="Elden Ring Jagged Peak">Jagged Peak</a>:',
                "Jagged Peak:",
            )

    next_id = max(int(r["id"]) for r in rows) + 1
    out_rows = []
    split_count = 0

    for row in rows:
        if row["id"] in SPLIT_MULTI_ENCOUNTER_IDS:
            locations = ast.literal_eval(row["Locations & Drops"])
            first = True
            for loc_key, drops in locations.items():
                new_row = dict(row)
                label = loc_key.rstrip(":").strip()
                new_row["name"] = f'{row["name"]} ({label})'
                new_row["Locations & Drops"] = repr({loc_key: drops})
                new_row["id"] = row["id"] if first else str(next_id)
                if not first:
                    next_id += 1
                first = False
                out_rows.append(new_row)
                split_count += 1
        else:
            out_rows.append(row)

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"bosses.csv: fixed HP on {hp_fixed} rows, dlc on {dlc_fixed} rows, "
          f"split {len(SPLIT_MULTI_ENCOUNTER_IDS)} boss(es) into {split_count} rows")


if __name__ == "__main__":
    normalize_dlc_flag("armors.csv")
    normalize_dlc_flag("incantations.csv")
    fix_consumables()
    fix_key_items()
    fix_locations()
    fix_creatures()
    fix_bosses()
