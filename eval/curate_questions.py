import json
from pathlib import Path
import random
from collections import defaultdict

random.seed(42)

HERE = Path(__file__).resolve().parent
pool = json.load(open(HERE / "question_pool.json", encoding="utf-8"))


def template_tag(p):
    q = p["question"]
    f = p["source"][0]["file"]
    if q.startswith("What weapon category"):
        return "weapon_category"
    if "talisman have" in q:
        return "talisman_effect"
    if q.startswith("What region is"):
        return "location_region"
    if q.startswith("What type of armor slot"):
        return "armor_slot"
    if q.startswith("What does the") and "spell do" in q:
        return "spell_effect"
    if q.startswith("What role does"):
        return "npc_role"
    if "weight of the" in q and "talisman" in q:
        return "talisman_weight"
    if q.startswith("What is the weight of") and "weapons.csv" in f:
        return "weapon_weight"
    if q.startswith("What is the weight of") and "armors.csv" in f:
        return "armor_weight"
    if q.startswith("What are the attribute requirements"):
        return "weapon_requirements"
    if "total HP" in q:
        return "boss_hp"
    if q.startswith("What is the FP cost of"):
        return "spell_fp"
    if q.startswith("What items are dropped by defeating"):
        return "boss_drops"
    if q.startswith("Which bosses can be fought at"):
        return "location_bosses"
    if q.startswith("Which NPCs can be found at"):
        return "location_npcs"
    return "other"


import re

BAD_ANSWER_SNIPPETS = ["Spirit NPC", "TBD", "N/A", "n/a", "???", "Other Drops", "(NG)", "Map Link", ":"]
LEADING_RUNE_AMOUNT = re.compile(r"^\d[\d,]*\s")  # Malenia 那種 "480,000 xxx" 格式錯誤殘留


def is_bad(p):
    ans = p["answer"].strip()
    if not ans:
        return True
    if ans == "NPCs.":
        return True
    if any(b in ans for b in BAD_ANSWER_SNIPPETS):
        return True
    if LEADING_RUNE_AMOUNT.match(ans):
        return True
    if len(ans) > 220:
        return True
    return False


for p in pool:
    p["tag"] = template_tag(p)

# S1 出題時額外發現的污染地點，還沒全面稽核，先排除避免出到壞題
KNOWN_BAD_ENTITIES = {"Sealed Tunnel"}

filtered = [p for p in pool if not is_bad(p) and p["source"][0]["entity"] not in KNOWN_BAD_ENTITIES]

by_type_tag = defaultdict(list)
for p in filtered:
    by_type_tag[(p["type"], p["tag"])].append(p)

# 每種 (type, tag) 組合想抽幾題，抽的時候故意混 dlc=0/1
TARGETS = {
    ("single_fact", "weapon_category"): 4,
    ("single_fact", "talisman_effect"): 3,
    ("single_fact", "location_region"): 3,
    ("single_fact", "armor_slot"): 3,
    ("single_fact", "spell_effect"): 4,
    ("single_fact", "npc_role"): 3,
    ("numeric", "weapon_weight"): 3,
    ("numeric", "weapon_requirements"): 4,
    ("numeric", "boss_hp"): 4,
    ("numeric", "armor_weight"): 3,
    ("numeric", "spell_fp"): 3,
    ("numeric", "talisman_weight"): 3,
    ("relational", "boss_drops"): 8,
    ("relational", "location_bosses"): 6,
    ("relational", "location_npcs"): 6,
}

selected = []
used_entities = set()

for key, n in TARGETS.items():
    candidates = by_type_tag.get(key, [])
    random.shuffle(candidates)
    dlc1 = [c for c in candidates if c["dlc"] == "1" and c["source"][0]["entity"] not in used_entities]
    dlc0 = [c for c in candidates if c["dlc"] == "0" and c["source"][0]["entity"] not in used_entities]
    # 盡量挑 1~2 題 DLC，其餘本篇
    want_dlc1 = min(2, n // 3 + 1, len(dlc1))
    picks = dlc1[:want_dlc1] + dlc0[: n - want_dlc1]
    for c in picks:
        used_entities.add(c["source"][0]["entity"])
    selected.extend(picks)

from collections import Counter
print("已選數量:", len(selected))
print(Counter(p["type"] for p in selected))
print("DLC 分布:", Counter(p["dlc"] for p in selected))

with open(HERE / "curated_60.json", "w", encoding="utf-8") as f:
    json.dump(selected, f, ensure_ascii=False, indent=2)
