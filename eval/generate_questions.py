"""S1: 從已清理過的資料表模板化產生 single_fact / numeric / relational 候選題目。
直接讀 CSV 欄位當標準答案，避免手打數字/名稱打錯。
輸出一個大候選池，之後再人工挑選、去重、確保涵蓋 DLC/本篇與跨檔案類型。
"""
import ast
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dlc_scrape"
PROC = ROOT / "data" / "processed" / "dlc_scrape"

random.seed(7)


def load(rel_path):
    """優先讀 data/processed（已清理），沒有的話退回 data/raw。"""
    p = PROC / rel_path
    if not p.exists():
        p = RAW / rel_path
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f)), str(p.relative_to(p.parents[2]))


def clean_int(s):
    s = s.strip()
    if not s or not s.replace(",", "").isdigit():
        return None
    return s


pool = []


def add(qtype, question, answer, source_file, row_id, entity, dlc="0"):
    pool.append({
        "type": qtype,
        "question": question,
        "answer": answer,
        "source": [{"file": source_file, "row_id": row_id, "entity": entity}],
        "dlc": dlc,
    })


# ---------- single_fact ----------

weapons, wf = load("weapons.csv")
for r in weapons:
    if r["category"] and r["damage type"]:
        add("single_fact",
            f'What weapon category does {r["name"]} belong to, and what damage type does it deal?',
            f'{r["category"]}; deals {r["damage type"]} damage.',
            wf, r["id"], r["name"], r.get("dlc","0"))

talismans, tf = load("talismans.csv")
for r in talismans:
    if r["effect"] and len(r["effect"]) < 160:
        add("single_fact",
            f'What effect does the {r["name"]} talisman have?',
            r["effect"].replace("Effect ", "", 1).strip(),
            tf, r["id"], r["name"], r.get("dlc","0"))

locations, lf = load("locations.csv")
for r in locations:
    if r["region"]:
        add("single_fact",
            f'What region is {r["name"]} located in?',
            r["region"],
            lf, r["id"], r["name"], r.get("dlc","0"))

armors, af = load("armors.csv")
for r in armors:
    if r["type"]:
        add("single_fact",
            f'What type of armor slot does {r["name"]} occupy?',
            r["type"],
            af, r["id"], r["name"], r.get("dlc","0"))

sorceries, sof = load("sorceries.csv")
incantations, inf = load("incantations.csv")
for rows, fname in ((sorceries, sof), (incantations, inf)):
    for r in rows:
        if r["effect"] and len(r["effect"]) < 160:
            add("single_fact",
                f'What does the {r["name"]} spell do?',
                r["effect"],
                fname, r["id"], r["name"], r.get("dlc","0"))

npcs, nf = load("npcs.csv")
for r in npcs:
    if r["role"]:
        add("single_fact",
            f'What role does {r["name"]} serve?',
            r["role"],
            nf, r["id"], r["name"], r.get("dlc","0"))


# ---------- numeric ----------

for r in weapons:
    if r["weight"]:
        add("numeric",
            f'What is the weight of {r["name"]}?',
            f'{r["weight"]}',
            wf, r["id"], r["name"], r.get("dlc","0"))
    if r["requirements"]:
        try:
            req = ast.literal_eval(r["requirements"])
            parts = ", ".join(f"{k} {v}" for k, v in req.items())
            add("numeric",
                f'What are the attribute requirements to wield {r["name"]}?',
                parts,
                wf, r["id"], r["name"], r.get("dlc","0"))
        except (ValueError, SyntaxError):
            pass

bosses, bf = load("bosses.csv")
for r in bosses:
    hp = clean_int(r["HP"])
    if hp:
        add("numeric",
            f"What is {r['name']}'s total HP?",
            hp,
            bf, r["id"], r["name"], r.get("dlc","0"))

for r in armors:
    if r["weight"]:
        add("numeric",
            f'What is the weight of {r["name"]}?',
            r["weight"],
            af, r["id"], r["name"], r.get("dlc","0"))

for rows, fname in ((sorceries, sof), (incantations, inf)):
    for r in rows:
        if r["FP"]:
            add("numeric",
                f'What is the FP cost of {r["name"]}?',
                r["FP"],
                fname, r["id"], r["name"], r.get("dlc","0"))

for r in talismans:
    if r["weight"]:
        add("numeric",
            f'What is the weight of the {r["name"]} talisman?',
            r["weight"],
            tf, r["id"], r["name"], r.get("dlc","0"))


# ---------- relational ----------

for r in bosses:
    try:
        ld = ast.literal_eval(r["Locations & Drops"])
    except (ValueError, SyntaxError):
        continue
    if len(ld) == 1:
        (loc, drops), = ld.items()
        items = [d for d in drops if not d.replace(",", "").replace(" Runes", "").strip().replace(",", "").isdigit()
                  and "Runes" not in d]
        if items:
            add("relational",
                f'What items are dropped by defeating {r["name"]}?',
                ", ".join(items) + ".",
                bf, r["id"], r["name"], r.get("dlc","0"))

for r in locations:
    try:
        boss_list = ast.literal_eval(r["bosses"]) if r["bosses"] else []
    except (ValueError, SyntaxError):
        boss_list = []
    if boss_list:
        add("relational",
            f'Which bosses can be fought at {r["name"]}?',
            ", ".join(boss_list) + ".",
            lf, r["id"], r["name"], r.get("dlc","0"))
    try:
        npc_list = ast.literal_eval(r["npcs"]) if r["npcs"] else []
    except (ValueError, SyntaxError):
        npc_list = []
    if npc_list and len(npc_list) <= 8:
        add("relational",
            f'Which NPCs can be found at {r["name"]}?',
            ", ".join(npc_list) + ".",
            lf, r["id"], r["name"], r.get("dlc","0"))

print(f"候選池總數: {len(pool)}")
from collections import Counter
print(Counter(p["type"] for p in pool))

out = Path(__file__).resolve().parent / "question_pool.json"
out.write_text(json.dumps(pool, ensure_ascii=False, indent=2))
print("寫到", out)
