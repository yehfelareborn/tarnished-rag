"""S2 任務 1：把每個實體的 CSV 欄位轉成一段文字描述，輸出成
data/processed/corpus.jsonl，供 src/vector 切塊、embedding 用。

每份文件的 source 用 {file, row_id} 表示，跟 eval/questions.jsonl 的
source 格式一致，這樣 recall@k 才能直接比對。

優先讀 data/processed（已清理過的版本），沒有的話退回 data/raw。
不處理 weapons_upgrades.csv / shields_upgrades.csv（強化等級表，
不是「一個實體一段描述」的東西，S2 先不用它們）。
"""
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dlc_scrape"
PROC = ROOT / "data" / "processed" / "dlc_scrape"
OUT = ROOT / "data" / "processed" / "corpus.jsonl"


def load(rel_path):
    p = PROC / rel_path
    used_processed = p.exists()
    if not used_processed:
        p = RAW / rel_path
    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    src_root = "data/processed/dlc_scrape" if used_processed else "data/raw/dlc_scrape"
    return rows, f"{src_root}/{rel_path}"


def g(value, default=""):
    return (value or "").strip() or default


def parse_list(s):
    if not s:
        return []
    try:
        v = ast.literal_eval(s)
        return v if isinstance(v, list) else [v]
    except (ValueError, SyntaxError):
        return [s]


def parse_dict(s):
    if not s:
        return {}
    try:
        v = ast.literal_eval(s)
        return v if isinstance(v, dict) else {}
    except (ValueError, SyntaxError):
        return {}


docs = []


def add(entity, etype, text, source_file, row_id, dlc="0"):
    text = " ".join(text.split())  # 壓平多餘空白/換行
    docs.append({
        "id": f"{etype}:{row_id}:{len(docs)}",
        "entity": entity,
        "type": etype,
        "dlc": dlc,
        "text": text,
        "source": [{"file": source_file, "row_id": row_id, "entity": entity}],
    })


# ---------- weapons ----------
rows, src = load("weapons.csv")
for r in rows:
    req = parse_dict(r.get("requirements", ""))
    req_str = ", ".join(f"{k} {v}" for k, v in req.items()) if req else "none"
    text = (
        f"{g(r['name'])} is a weapon in the {g(r['category'])} category, "
        f"dealing {g(r['damage type'])} damage. It weighs {g(r['weight'])} "
        f"and requires: {req_str}. "
        f"Passive effect: {g(r['passive effect'], 'none')}. Skill: {g(r['skill'], 'none')}. "
        f"{g(r['description'])}"
    )
    add(r["name"], "weapon", text, src, r["id"], r.get("dlc", "0"))

# ---------- armors ----------
rows, src = load("armors.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is a piece of {g(r['type'])} armor weighing {g(r['weight'])}. "
        f"How to acquire: {g(r['how to acquire'], 'unknown')}. "
        f"Special effect: {g(r['special effect'], 'none')}. {g(r['description'])}"
    )
    add(r["name"], "armor", text, src, r["id"], r.get("dlc", "0"))

# ---------- talismans ----------
rows, src = load("talismans.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is a talisman weighing {g(r['weight'])}, worth {g(r['value'])} runes. "
        f"Effect: {g(r['effect'])}. {g(r['description'])}"
    )
    add(r["name"], "talisman", text, src, r["id"], r.get("dlc", "0"))

# ---------- sorceries / incantations ----------
for fname, label in (("sorceries.csv", "sorcery"), ("incantations.csv", "incantation")):
    rows, src = load(fname)
    for r in rows:
        text = (
            f"{g(r['name'])} is a {label} costing {g(r['FP'])} FP, using slot {g(r['slot'])}. "
            f"Requirements: Int {g(r.get('INT'), '-')}, Fai {g(r.get('FAI'), '-')}, "
            f"Arc {g(r.get('ARC'), '-')}. Effect: {g(r['effect'])}. "
            f"Found at: {g(r.get('location'), 'unknown')}."
        )
        add(r["name"], label, text, src, r["id"], r.get("dlc", "0"))

# ---------- ashes of war ----------
rows, src = load("ashesOfWar.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is an Ash of War with default affinity {g(r['affinity'], 'unknown')}, "
        f"granting the skill {g(r['skill'])}. {g(r['description'])}"
    )
    add(r["name"], "ash_of_war", text, src, r["id"], r.get("dlc", "0"))

# ---------- shields ----------
rows, src = load("shields.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is a shield in the {g(r['category'])} category, weighing {g(r['weight'])}. "
        f"Damage type: {g(r['damage type'], 'none')}. Passive effect: {g(r['passive effect'], 'none')}. "
        f"Skill: {g(r['skill'], 'none')}. {g(r['description'])}"
    )
    add(r["name"], "shield", text, src, r["id"], r.get("dlc", "0"))

# ---------- spirit ashes ----------
rows, src = load("spiritAshes.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is a Spirit Ash of type {g(r['type'])}, costing {g(r['FP cost'])} FP "
        f"and {g(r['HP cost'])} HP to summon. Effect: {g(r['effect'])}. {g(r['description'])}"
    )
    add(r["name"], "spirit_ash", text, src, r["id"], r.get("dlc", "0"))

# ---------- skills (weapon skills / combat arts) ----------
rows, src = load("skills.csv")
for r in rows:
    locs = ", ".join(parse_list(r.get("locations", ""))) or "unknown"
    text = (
        f"{g(r['name'])} is a skill of type {g(r['type'])}, costing {g(r['FP'])} FP. "
        f"Effect: {g(r['effect'])}. Found via: {locs}."
    )
    add(r["name"], "skill", text, src, r["id"], r.get("dlc", "0"))

# ---------- bosses ----------
rows, src = load("bosses.csv")
for r in rows:
    locations = parse_dict(r.get("Locations & Drops", ""))
    loc_bits = []
    for loc, drops in locations.items():
        if not isinstance(loc, str):
            continue
        drop_str = ", ".join(str(d) for d in drops) if isinstance(drops, list) else str(drops)
        loc_bits.append(f"at {loc.rstrip(':').strip()} (drops: {drop_str})")
    loc_text = "; ".join(loc_bits) if loc_bits else "an unrecorded location"
    text = (
        f"{g(r['name'])} is a boss with {g(r['HP'], 'unknown')} HP, fought {loc_text}. "
        f"{g(r['blockquote'])}"
    )
    add(r["name"], "boss", text, src, r["id"], r.get("dlc", "0"))

# ---------- npcs ----------
rows, src = load("npcs.csv")
for r in rows:
    text = (
        f"{g(r['name'])} is an NPC with the role: {g(r['role'], 'unspecified')}. "
        f"Found at: {g(r['location'], 'unknown')}. {g(r['description'])}"
    )
    add(r["name"], "npc", text, src, r["id"], r.get("dlc", "0"))

# ---------- locations ----------
rows, src = load("locations.csv")
for r in rows:
    npcs = ", ".join(parse_list(r.get("npcs", ""))) or "none recorded"
    bosses_ = ", ".join(parse_list(r.get("bosses", ""))) or "none recorded"
    creatures_ = ", ".join(parse_list(r.get("creatures", ""))) or "none recorded"
    text = (
        f"{g(r['name'])} is a location in the {g(r['region'], 'unknown')} region. "
        f"{g(r['description'])} NPCs found here: {npcs}. Bosses found here: {bosses_}. "
        f"Creatures found here: {creatures_}."
    )
    add(r["name"], "location", text, src, r["id"], r.get("dlc", "0"))

# ---------- creatures ----------
rows, src = load("creatures.csv")
for r in rows:
    locs = ", ".join(parse_list(r.get("locations", ""))) or "unknown"
    drops = ", ".join(parse_list(r.get("drops", ""))) or "none recorded"
    text = (
        f"{g(r['name'])} is a creature found at: {locs}. Drops: {drops}. {g(r['blockquote'])}"
    )
    add(r["name"], "creature", text, src, r["id"], r.get("dlc", "0"))

# ---------- items/* subcategories ----------
item_files = [
    "ammos.csv", "bells.csv", "consumables.csv", "cookbooks.csv", "crystalTears.csv",
    "greatRunes.csv", "keyItems.csv", "materials.csv", "multi.csv", "remembrances.csv",
    "tools.csv", "upgradeMaterials.csv", "whetblades.csv",
]
for fname in item_files:
    rows, src = load(f"items/{fname}")
    for r in rows:
        parts = [g(r['name'])]
        for field in ("type", "effect", "usage", "location", "description", "boss",
                      "option 1", "option 2", "value"):
            v = g(r.get(field, ""))
            if v:
                parts.append(f"{field}: {v}")
        text = ". ".join(parts)
        add(r["name"], "item", text, src, r["id"], r.get("dlc", "0"))

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    for d in docs:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

from collections import Counter
print(f"共 {len(docs)} 篇文件，寫到 {OUT}")
print(Counter(d["type"] for d in docs))
