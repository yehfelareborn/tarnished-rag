"""S3：從 data/processed（沒有的話退回 data/raw）的 CSV 建立 Neo4j 知識圖譜。

只用結構化欄位，不用 LLM。每個節點與邊都帶 source_file / row_id 以便追溯。
名稱比對沒對上的記錄到 data/processed/graph_unmatched.csv，不強行連。

用法：先啟動 Neo4j（連線資訊從專案根目錄 .env 讀），再
    python3 src/graph/build_graph.py
會清空資料庫後重建（可重複執行）。
"""
import ast
import csv
import difflib
import html
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dlc_scrape"
PROC = ROOT / "data" / "processed" / "dlc_scrape"
STATS_CSV = ROOT / "data" / "raw" / "boss_stats" / "elden_ring_boss_stats_clean.csv"
UNMATCHED_CSV = ROOT / "data" / "processed" / "graph_unmatched.csv"

# bosses.csv 裡的角色只在部分地點是 boss、其他地點是 NPC：row id -> {npc 名稱, boss 身分成立的地點}。
# 使用者（玩過遊戲）於 2026-09-28 確認：Patches 在 Murkwater Cave 是 boss，在其他地點（Volcano Manor、The Shaded Castle 等）是 NPC。
# 該列的 boss 身分（HP、地點、掉落）只保留在 boss_at 列出的地點，其他地點改掛在同名 NPC 節點上。
BOSS_ONLY_AT = {"141": {"npc": "Patches", "boss_at": {"Murkwater Cave"}}}


# ---------------------------------------------------------------- 讀檔／名稱正規化

def load(rel):
    p = PROC / rel
    if not p.exists():
        p = RAW / rel
    rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
    src = "data/" + ("processed" if p.is_relative_to(PROC) else "raw") + "/dlc_scrape/" + rel
    return rows, src


def norm(s):
    """比對用的正規化：修 `theBlasphemous` 這類黏字、去標點與撇號、小寫、壓空白。"""
    s = (s or "").replace("\xa0", " ")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\bthe([A-Z])", r"the \1", s)
    s = s.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def snake(k):
    return re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_list(s):
    if not s or not s.strip():
        return []
    try:
        v = ast.literal_eval(s)
        return [str(x).strip() for x in v] if isinstance(v, list) else [str(v).strip()]
    except (ValueError, SyntaxError):
        return [s.strip()]


def parse_dict(s):
    try:
        v = ast.literal_eval(s)
        return v if isinstance(v, dict) else {}
    except (ValueError, SyntaxError):
        return {}


# ---------------------------------------------------------------- 節點

nodes = defaultdict(list)          # label -> [props]
name_index = defaultdict(list)     # norm(name) -> [(label, uid)]
label_index = defaultdict(lambda: defaultdict(list))  # label -> norm(name) -> [uid]
node_props = {}                    # uid -> props
edges = defaultdict(list)          # type -> [{a, b, props}]
nospace_index = defaultdict(list)  # 去掉所有空白的名稱 -> [(label, uid)]，補空白／撇號黏合的差異
unmatched = []
stubs = []
fuzzy_log = []   # 靠「去空白」或「名稱包含」比對成功的記錄，供稽核
stats = Counter()
FUZZY_CSV = ROOT / "data" / "processed" / "graph_fuzzy_matches.csv"
STUBS_CSV = ROOT / "data" / "processed" / "graph_stubs.csv"


def add_node(label, stem, row, name, **props):
    uid = f"{label}:{stem}:{row['id']}"
    p = {"uid": uid, "name": name.strip(), "dlc": 1 if str(row.get("dlc", "0")).strip() == "1" else 0,
         "source_file": props.pop("_src"), "row_id": row["id"]}
    p.update({k: v for k, v in props.items() if v not in (None, "")})
    nodes[label].append(p)
    node_props[uid] = p
    key = norm(name)
    name_index[key].append((label, uid))
    nospace_index[key.replace(" ", "")].append((label, uid))
    label_index[label][key].append(uid)
    return uid


def add_edge(etype, a, b, source, **props):
    edges[etype].append({"a": a, "b": b, "props": {"source_file": source, **{k: v for k, v in props.items() if v not in (None, "")}}})


def log_unmatched(kind, context, text, source):
    unmatched.append({"kind": kind, "context": context, "text": text, "source_file": source})


def build_nodes():
    # Weapon / Shield
    for fname, label in (("weapons.csv", "Weapon"), ("shields.csv", "Shield")):
        rows, src = load(fname)
        for r in rows:
            req = parse_dict(r.get("requirements", ""))
            add_node(label, fname[:-4], r, r["name"], _src=src, category=r["category"], damage_type=r["damage type"],
                     weight=num(r["weight"]), passive_effect=r["passive effect"], skill=r["skill"],
                     fp_cost=r["FP cost"], description=r["description"],
                     str=req.get("Str"), dex=req.get("Dex"), int=req.get("Int"), fai=req.get("Fai"), arc=req.get("Arc"))
    # Armor
    rows, src = load("armors.csv")
    for r in rows:
        add_node("Armor", "armors", r, r["name"], _src=src, slot=r["type"], weight=num(r["weight"]),
                 damage_negation=r["damage negation"], resistance=r["resistance"],
                 special_effect=r["special effect"], how_to_acquire=r["how to acquire"],
                 in_game_section=r["in-game section"], description=r["description"])
    # Talisman
    rows, src = load("talismans.csv")
    for r in rows:
        add_node("Talisman", "talismans", r, r["name"], _src=src, effect=r["effect"], weight=num(r["weight"]),
                 value=num(r["value"]), description=r["description"])
    # Spell
    for fname, school in (("sorceries.csv", "sorcery"), ("incantations.csv", "incantation")):
        rows, src = load(fname)
        for r in rows:
            add_node("Spell", fname[:-4], r, r["name"], _src=src, school=school, effect=r["effect"], fp=r["FP"],
                     slot=r["slot"], int=num(r["INT"]), fai=num(r["FAI"]), arc=num(r["ARC"]),
                     stamina_cost=r["stamina cost"], location_text=r["location"], description=r["description"])
    # AshOfWar / Skill / SpiritAsh
    rows, src = load("ashesOfWar.csv")
    for r in rows:
        add_node("AshOfWar", "ashesOfWar", r, r["name"], _src=src, affinity=r["affinity"], skill=r["skill"],
                 description=r["description"])
    rows, src = load("skills.csv")
    for r in rows:
        add_node("Skill", "skills", r, r["name"], _src=src, skill_type=r["type"], equipment=r["equipament"],
                 charge=r["charge"], fp=r["FP"], effect=r["effect"])
    rows, src = load("spiritAshes.csv")
    for r in rows:
        add_node("SpiritAsh", "spiritAshes", r, r["name"], _src=src, spirit_type=r["type"], fp_cost=r["FP cost"],
                 hp_cost=r["HP cost"], effect=r["effect"], description=r["description"])
    # Item：13 個子類統一成 Item，item_type 記錄來源子類
    for fname in ["ammos", "bells", "consumables", "cookbooks", "crystalTears", "greatRunes", "keyItems",
                  "materials", "multi", "remembrances", "tools", "upgradeMaterials", "whetblades"]:
        rows, src = load(f"items/{fname}.csv")
        for r in rows:
            extra = {snake(k): v.strip() for k, v in r.items()
                     if k not in ("id", "name", "image", "dlc") and v and v.strip()}
            extra.pop("type", None)
            add_node("Item", fname, r, r["name"], _src=src, item_type=fname, **extra)
    # Boss（HP 盡量 parse；多階段／註記格式保留原字串）
    rows, src = load("bosses.csv")
    for r in rows:
        raw = r["HP"].strip()
        hp = None
        m = re.fullmatch(r"≈?\s*([\d,]+)(?:\s*\(.*\))?", raw)
        if m:
            hp = num(m.group(1))
        add_node("Boss", "bosses", r, r["name"], _src=src, hp_raw=raw, hp=hp, blockquote=r["blockquote"])
    # Creature / NPC / Location
    rows, src = load("creatures.csv")
    for r in rows:
        add_node("Creature", "creatures", r, r["name"], _src=src, blockquote=r["blockquote"])
    rows, src = load("npcs.csv")
    for r in rows:
        add_node("NPC", "npcs", r, r["name"], _src=src, role=r["role"], voiced_by=r["voiced by"],
                 description=r["description"])
    rows, src = load("locations.csv")
    for r in rows:
        add_node("Location", "locations", r, r["name"], _src=src, description=r["description"])
    # Region（由 locations.region 產生，沒有自己的 CSV）
    for reg in sorted({r["region"].strip() for r in rows if r["region"].strip()}):
        uid = f"Region:locations:{reg}"
        p = {"uid": uid, "name": reg, "dlc": 0, "source_file": src, "row_id": reg}
        nodes["Region"].append(p)
        node_props[uid] = p
        name_index[norm(reg)].append(("Region", uid))
        label_index["Region"][norm(reg)].append(uid)
    return rows


# ---------------------------------------------------------------- 名稱比對

ITEM_LIKE = ["Item", "Weapon", "Armor", "Talisman", "Spell", "AshOfWar", "Shield", "SpiritAsh"]
NON_CREATURE_ITEM_LIKE = [l for l in ITEM_LIKE if l != "SpiritAsh"]   # 判斷欄位污染用
ITEM_PRIORITY = ["remembrances", "greatRunes", "keyItems", "tools", "bells", "cookbooks", "crystalTears",
                 "upgradeMaterials", "whetblades", "multi", "ammos", "materials", "consumables"]


def pick(cands):
    """同名多個候選時，Item 依來源子類優先序挑一個；其餘取第一個。"""
    if len(cands) == 1:
        return cands[0]
    stats["ambiguous_name"] += 1
    def rank(uid):
        t = node_props[uid].get("item_type")
        return ITEM_PRIORITY.index(t) if t in ITEM_PRIORITY else 99
    return sorted(cands, key=rank)[0]


# 同名 Item 合併（S4 查詢工具發現，使用者 2026-09-28 決定合併）。
# 以 norm(name) 分組，同一組只留一個節點。不合併的組：同名但其實是不同任務狀態的物品，
# 硬併會把不同物品變成一個（Lord of Blood's Favor 是白布與染紅的布；Unalloyed Gold Needle 有完整、斷掉、修復三種），
# 留給使用者用遊戲知識決定。
MERGE_EXCLUDE = {norm("Lord of Blood's Favor"), norm("Unalloyed Gold Needle")}
MERGED = {}                 # 被併掉的 uid -> 保留的 uid
MERGE_LOG = []              # 稽核：每個被併掉的節點一列
ITEM_MERGE_CSV = ROOT / "data" / "processed" / "graph_item_merges.csv"
MERGE_SKIP_KEYS = {"uid", "row_id", "source_file", "name", "item_type", "dlc", "stub"}


def merge_duplicate_items():
    """把同名（norm 後相同）的 Item 節點合成一個，在建邊之前做，後面所有名稱比對就只會找到保留的那個。

    保留誰：依 ITEM_PRIORITY（與 pick() 同一張表），同來源取列號最小的。
    不丟資料：保留者缺的欄位用被併掉的補上；兩份都有值但不同的欄位，保留者的值不變，另一份的值記在
    merged_variants（JSON 字串）；被併掉的 uid 記在 merged_from，所有來源分類記在 item_types，
    拼法不同的名稱記在 aliases。每個被併掉的節點另寫一列到 graph_item_merges.csv。"""
    groups = defaultdict(list)
    for p in nodes["Item"]:
        groups[norm(p["name"])].append(p["uid"])
    for key, uids in groups.items():
        if len(uids) < 2 or key in MERGE_EXCLUDE:
            continue
        if len({node_props[u]["dlc"] for u in uids}) > 1:          # 不該發生；dlc 不同就不自動合併
            log_unmatched("item_merge_skipped_dlc_differs", norm(key), ", ".join(uids), "")
            continue
        uids = sorted(uids, key=lambda u: (ITEM_PRIORITY.index(node_props[u]["item_type"])
                                           if node_props[u].get("item_type") in ITEM_PRIORITY else 99,
                                           int(node_props[u]["row_id"])))
        keep, rest = uids[0], uids[1:]
        kp = node_props[keep]
        variants, aliases, types = [], list(kp.get("aliases", [])), [kp.get("item_type")]
        for u in rest:
            op = node_props[u]
            differs = {}
            for k, v in op.items():
                if k in MERGE_SKIP_KEYS:
                    continue
                if kp.get(k) in (None, ""):
                    kp[k] = v                                        # 補上保留者沒有的欄位
                elif str(kp[k]).strip() != str(v).strip():
                    differs[k] = v
            if op["name"] != kp["name"] and op["name"] not in aliases:
                aliases.append(op["name"])                           # 拼法不同的名稱（如黏字與正確拼法）
            if op.get("item_type") not in types:
                types.append(op.get("item_type"))
            if differs:
                variants.append({"uid": u, "source_file": op["source_file"], "row_id": op["row_id"], "differs": differs})
            MERGE_LOG.append({"kept": keep, "merged": u, "name": kp["name"], "merged_name": op["name"],
                              "conflicts": json.dumps({k: [kp[k], v] for k, v in differs.items()}, ensure_ascii=False)})
        kp["merged_from"] = rest
        kp["item_types"] = types
        if aliases:
            kp["aliases"] = aliases
        if variants:
            kp["merged_variants"] = json.dumps(variants, ensure_ascii=False)
        gone = set(rest)
        nodes["Item"] = [p for p in nodes["Item"] if p["uid"] not in gone]
        for u in rest:
            del node_props[u]
            MERGED[u] = keep
        name_index[key] = [(l, u) for l, u in name_index[key] if u not in gone]
        nospace_index[key.replace(" ", "")] = [(l, u) for l, u in nospace_index[key.replace(" ", "")] if u not in gone]
        label_index["Item"][key] = [u for u in label_index["Item"][key] if u not in gone]
        stats["items_merged"] += len(rest)


NOISE_STR =re.compile(r"^(map link|elden ring map link|npcs?|spirit npc|\?+|to be added|n/a|-+|none|"
                       r"other drops:?|used to duplicate.*)$", re.I)


TABLE_JUNK = re.compile(r"^.*\s:\s*[\d,.\s]*$")                          # 'Volcano Manor :'、'Stormveil Castle : 1,176'
RUNE_RANGE = re.compile(r"^[-\u2013\s\d,.?]*\d[-\u2013\s\d,.?]*\s*runes?\b(.*)$", re.I)   # '40 - 1020 Runes'、'52 - 1390 Runes Thin Beast Bones'
RUNES_FIRST = re.compile(r"^runes?\s*[\d,.\s]+(?:\(.*\))?$", re.I)     # 'Runes 70,000 (NG)'


def is_noise(text):
    t = text.strip()
    return (not t) or bool(NOISE_STR.match(t)) or bool(TABLE_JUNK.match(t)) or bool(RUNES_FIRST.match(t))


# 依遊戲知識判斷為同一實體的不同寫法（待使用者確認）；key/value 都是 norm() 後的字串
ALIAS_TEXT = {
    "Morgott, the Omen King": "Morgott The Grace-Given Veiled Monarch Omen King",
    "Rennala, Queen of the Full Moon": "Rennala Carian Queen of the Full Moon",
    "Nepheli Loux": "Nepheli Loux, Warrior",
    "Count Ymir": "Count Ymir, High Priest",
    "War Counselor Iji": "Iji War Counselor & Carian Blacksmith",
    "Shaded Castle Spirit": "The Shaded Castle Spirit",
    "Soldier of Godrick": "Godrick Soldier",
    "Fia": "Fia, Deathbed Companion",
    "Blaidd": "Blaidd the Half-Wolf",
    "Rennala": "Rennala, Queen of the Full Moon",
    "Yura": "Bloody Finger Hunter Yura",
    "Diallos": "Knight Diallos",
    "Corhyn": "Brother Corhyn",
    "Ansbach": "Sir Ansbach",
    "Boc": "Boc the Seamster",
    "Alexander": "Iron Fist Alexander",
    "Ranni the Witch": "Ranni Witch Carian Lunar Princess",
    "Ensha": "Ensha of the Royal Remains",
    "Perfumer Tricia": "Perfumer Tricia and Misbegotten Warrior",
}
ALIASES = {norm(k): norm(v) for k, v in ALIAS_TEXT.items()}

# bosses.csv 地點欄的整串別名（使用者確認）：優先於掃描，否則會先掃到較短的名稱（Jagged Peak 區域）而誤連
LOCATION_ALIAS_TEXT = {
    "Jagged Peak Foothills": "Foot of the Jagged Peak",
}
LOCATION_ALIASES = {norm(k): v for k, v in LOCATION_ALIAS_TEXT.items()}

# 地點欄整串掃描後剩下的字串，經使用者確認的處理：對到既有區域，或建 Location stub（該地點不在 locations.csv）。
# 不在這張表裡的殘留字串一律記到 graph_unmatched.csv（kind=boss_location_leftover），不無聲丟掉。
LEFTOVER_PLACES = {norm(k): v for k, v in {
    "Liurnia": ("Region", "Liurnia of the Lakes"),               # Patches 在 Liurnia 也是 NPC
    "Specimen Storehouse": ("stub", "Specimen Storehouse"),      # Shadow Keep 內的獨立地點
}.items()}


def candidates(text):
    """只做明確的清理，不做語意猜測：去 HTML 實體、去頭尾數量、去尾端短括號註解、去『Gateway:』這類前綴、去 Ashes 後綴。"""
    t = html.unescape(text).replace("\xa0", " ").strip()
    out = [t]
    t2 = re.sub(r"^[\d.,\s]+,\s*", "", t)                                   # '4,600, Greatblade Phalanx'
    t2 = re.sub(r"^(?:\d+\s*x|x\s*\d+)\s+", "", t2, flags=re.I)               # '12x Trina's Lily'、'x1 Arteria Leaf'
    t2 = re.sub(r"\s+(?:x\s*\d+|\d+\s*x)$", "", t2, flags=re.I)               # 'Black-Key Bolt x20'
    out.append(t2)
    t3 = re.sub(r"\s*\([^()]{1,14}\)\s*$", "", t2).strip()                    # '(NG Only)'、'(6)'、'(+8)'
    out.append(t3)
    out.append(re.sub(r"\s*\([^()]*\)\s*$", "", t2).strip())                  # 'Talisman Pouch (NG only, Morgott not defeated)'
    if re.search(r"\+\d$", t3):
        out.append(t3 + " Variant")                                          # 'Stalwart Horn Charm +2' -> '... +2 Variant'
    m = re.match(r"^[A-Za-z' ]{3,20}:\s+(\S.*)$", t3)                        # 'Gateway: Lord's Rune'
    if m:
        out.append(m.group(1))
    out.append(re.sub(r"\s+(?:Spirit )?Ashes$", "", t3))                       # 'Perfumer Tricia Ashes'
    return list(dict.fromkeys(x for x in out if x))


def resolve(text, labels):
    """對每個清理後的候選字串：精確 → 別名（後備）→ 去空白。回傳 uid 或 None。"""
    for i, cand in enumerate(candidates(text)):
        key = norm(cand)
        tries = [(key, "exact" if i == 0 else "cleaned")]
        if key in ALIASES:
            tries.append((ALIASES[key], "alias"))
        tries.append((key, "nospace"))
        for k, how in tries:
            if how == "nospace":
                cs = [uid for lab, uid in nospace_index.get(k.replace(" ", ""), []) if lab in labels]
            else:
                cs = [uid for lab, uid in name_index.get(k, []) if lab in labels]
            if cs:
                u = pick(cs)
                if how != "exact":
                    stats["resolved_" + how] += 1
                    fuzzy_log.append({"how": how, "text": text, "matched_to": node_props[u]["name"], "label": u.split(":")[0]})
                return u
    return None


def stub(label, text, source, dlc=0, **props):
    """資料裡有明確提到、但沒有自己那一列的實體：建立只有名稱與來源的節點，標記 stub=true 並記錄。"""
    text = text.strip()
    key = norm(text)
    existing = [uid for lab, uid in name_index.get(key, []) if lab == label]
    if existing:
        return existing[0]
    if label in ("Boss", "NPC", "Creature", "Location"):   # 錯字容忍：非常相似、數字一致、且只有一個候選才視為同一個
        near = [k for k in difflib.get_close_matches(key, list(label_index[label]), n=3, cutoff=0.93)
                if re.findall(r"\d+", k) == re.findall(r"\d+", key)]
        if len(near) == 1:
            u = label_index[label][near[0]][0]
            stats["resolved_typo"] += 1
            fuzzy_log.append({"how": "typo", "text": text, "matched_to": node_props[u]["name"], "label": label})
            return u
    uid = f"{label}:stub:{key.replace(' ', '_')}"
    p = {"uid": uid, "name": text, "dlc": int(dlc), "source_file": source, "row_id": "stub", "stub": True}
    p.update(props)
    nodes[label].append(p)
    node_props[uid] = p
    name_index[key].append((label, uid))
    nospace_index[key.replace(" ", "")].append((label, uid))
    label_index[label][key].append(uid)
    stubs.append({"label": label, "name": text, "source_file": source})
    return uid


def _scan_places(text, min_len=6, return_rest=False):
    """在整串文字中掃描已知的地點／區域名（長的優先、互不重疊；名稱本身含逗號也能對到）。
    return_rest=True 時多回傳掃描後剩下沒對上的字串（已正規化）。"""
    rest = f" {norm(text)} "
    names = sorted([(k, "Location") for k in label_index["Location"]] + [(k, "Region") for k in label_index["Region"]],
                   key=lambda x: len(x[0]), reverse=True)
    out = []
    for n, lab in names:
        if len(n) < min_len:
            continue
        pat = f" {n} "
        if pat in rest:
            out.append((label_index[lab][n][0], "substring" if lab == "Location" else "region"))
            rest = rest.replace(pat, " # ")
    if return_rest:
        return out, re.sub(r"\s+", " ", rest.replace("#", " ")).strip()
    return out


def resolve_location(text, ctx="", src="", dlc=0):
    """別名 → 精確 → 區域 → 整串掃描（含逗號的地點名也能對到；剩下的字串依 LEFTOVER_PLACES 處理，其餘記錄）
    → 逗號切段的精確比對（後備）。回傳 [(uid, how)]。ctx／src／dlc 只用在殘留字串的記錄與建 stub。"""
    text = re.sub(r"<[^>]+>", "", html.unescape(text))
    key = norm(text)
    if key in LOCATION_ALIASES:
        target = label_index["Location"].get(norm(LOCATION_ALIASES[key]))
        if target:
            stats["resolved_alias"] += 1
            fuzzy_log.append({"how": "alias", "text": text.strip(), "matched_to": node_props[target[0]]["name"], "label": "Location"})
            return [(target[0], "alias")]
    hit = label_index["Location"].get(key)
    if hit:
        return [(hit[0], "exact")]
    reg = label_index["Region"].get(key)
    if reg:
        return [(reg[0], "region")]
    out, rest = _scan_places(text, return_rest=True)
    if out:
        for lk, (kind, target) in LEFTOVER_PLACES.items():
            if f" {lk} " in f" {rest} ":
                if kind == "Region":
                    u = label_index["Region"][norm(target)][0]
                    stats["resolved_alias"] += 1
                    fuzzy_log.append({"how": "alias", "text": lk, "matched_to": node_props[u]["name"], "label": "Region"})
                    out.append((u, "region"))
                else:
                    out.append((stub("Location", target, src, dlc), "stub"))
                rest = re.sub(r"\s+", " ", f" {rest} ".replace(f" {lk} ", " ")).strip()
        if rest:
            log_unmatched("boss_location_leftover", ctx, rest, src)   # 掃描後仍沒對上的字串，不無聲丟掉
        return out
    for p in (p for p in re.split(r"[,;]", text) if p.strip()):
        pk = norm(p)
        if label_index["Location"].get(pk):
            out.append((label_index["Location"][pk][0], "part"))
        elif label_index["Region"].get(pk):
            out.append((label_index["Region"][pk][0], "region"))
    return list(dict.fromkeys(out))


QTY = re.compile(r"\s+(?:x\s*\d+|\d+\s*x)$", re.I)
RUNE_ONLY = re.compile(r"^[\d.,]+(?:\s*runes?)?(?:\s*each)?(?:\s*\(.*\))?$", re.I)
NOISE = re.compile(r"^(other drops:?|\(?ng\)?.*|ng\b.*|drops?:?)$", re.I)


def resolve_drop(text):
    """把掉落物字串對到節點，回傳 [(uid, note)]；沒對上回傳 []。"""
    uid = resolve(text, ITEM_LIKE)
    if uid:
        return [(uid, "")]
    t = QTY.sub("", html.unescape(text).strip())
    m = re.match(r"^(.*)\bSet$", t)
    if m:  # 「X Set」→ 名稱以 X 開頭的防具
        base = norm(m.group(1))
        pieces = [u for key, uids in label_index["Armor"].items() if key.startswith(base + " ") for u in uids]
        if pieces:
            return [(u, f"via set: {t}") for u in pieces]
    return []


# ---------------------------------------------------------------- 邊

def scan_items(text):
    """把黏在一起的字串（如「Malenia's Great Rune Remembrance of the Rot Goddess」）掃描出已知物品名。"""
    rest = f" {norm(text)} "
    out = []
    names = sorted({k for lab in ITEM_LIKE for k in label_index[lab]}, key=len, reverse=True)
    for n in names:
        if len(n) < 8:
            continue
        pat = f" {n} "
        if pat in rest:
            for lab in ITEM_LIKE:
                if n in label_index[lab]:
                    out.append(label_index[lab][n][0])
                    break
            rest = rest.replace(pat, " # ")
    return out


def item_targets(text, src, dlc, allow_stub=True):
    """掉落物／地點物品字串 → [(uid, note)]。雜訊直接略過（回傳 None）；對不上時建立 Item stub。"""
    t = re.sub(r"\s+each$", "", text.strip(), flags=re.I)
    if is_noise(t):
        stats["noise_skipped"] += 1
        return None
    rr = RUNE_RANGE.match(t)
    if rr:                                              # 符文範圍；後面若黏著物品名，掃描出來
        rest = rr.group(1).strip()
        found = scan_items(rest) if rest else []
        if not found:
            stats["rune_amount_skipped"] += 1
            return None
        return [(u, "scanned from glued text") for u in found]
    targets = resolve_drop(t)
    if not targets:
        m = re.match(r"^([\d,.]+)\s+(\S.*)$", t)        # 「480,000 xxx」：符文數黏在物品名前面
        if m:
            targets = resolve_drop(m.group(2)) or [(u, "scanned from glued text") for u in scan_items(m.group(2))]
        elif re.search(r"\d[\d,]*,\s*\D", t) and len(t) > 25:   # 表格殘渣：'26,000, Godfrey Icon 78,000, Godfrey Icon'
            targets = [(u, "scanned from glued text") for u in scan_items(t)]
    if not targets and allow_stub:
        targets = [(stub("Item", QTY.sub("", t), src, dlc, item_type="unknown"), "stub")]
    return targets or []


def build_edges(loc_rows):
    # Location -LOCATED_IN-> Region
    for r in loc_rows:
        reg = r["region"].strip()
        if reg:
            luid = f"Location:locations:{r['id']}"
            add_edge("LOCATED_IN", luid, f"Region:locations:{reg}", node_props[luid]["source_file"])

    # Boss -LOCATED_AT-> Location（含符文數）、Boss -DROPS-> 物品（含 at_location）
    boss_loc = defaultdict(set)   # boss uid -> {location uid}
    rel_sources = defaultdict(set)  # (擁有者 uid, location uid) -> {'bosses.csv', 'locations.csv'}
    bnorm = lambda x: norm(re.sub(r"\s*\(.*\)$", "", x or ""))
    loc_lists = {f"Location:locations:{lr['id']}": ({bnorm(x) for x in parse_list(lr["bosses"])},
                                                    {bnorm(x) for x in parse_list(lr["creatures"])})
                 for lr in loc_rows}
    rows, src = load("bosses.csv")
    for r in rows:
        buid = f"Boss:bosses:{r['id']}"
        bdlc = node_props[buid]["dlc"]
        split = BOSS_ONLY_AT.get(r["id"])
        npc_uid = resolve(split["npc"], ["NPC"]) if split else None
        if split and not npc_uid:
            log_unmatched("npc_for_boss_row", r["name"], split["npc"], src)

        def owner(luid, buid=buid, split=split, npc_uid=npc_uid):
            """這個地點的邊掛在 Boss 還是 NPC 上（只有 BOSS_ONLY_AT 列出的角色會分開）。"""
            if split and npc_uid and node_props[luid]["name"] not in split["boss_at"]:
                return npc_uid
            return buid

        for loc_key, items in parse_dict(r["Locations & Drops"]).items():
            if not isinstance(loc_key, str):
                continue
            items = items if isinstance(items, list) else [items]
            runes = None
            drops = []
            for it in (str(x).strip() for x in items):
                if RUNE_ONLY.match(it):
                    runes = runes or num(re.sub(r"[^\d]", "", it))
                else:
                    drops.append(it)
            locs = resolve_location(loc_key, ctx=f"{r['name']} @ {loc_key.strip()}", src=src, dlc=bdlc)
            loc_name = loc_key.strip().rstrip(":").strip()
            clean_loc = re.sub(r"<[^>]+>", "", html.unescape(loc_key)).strip().rstrip(":").strip()
            if not locs and clean_loc:
                locs = [(stub("Location", clean_loc, src, bdlc), "stub")]
            elif not locs:
                log_unmatched("boss_location", r["name"], loc_key, src)
            kept = []
            for luid, how in locs:
                blist, clist = loc_lists.get(luid, (set(), set()))
                if owner(luid) == buid and bnorm(r["name"]) in clist and bnorm(r["name"]) not in blist:
                    # locations.csv 把它列成該地點的 creature（不是 boss），經使用者確認以 locations.csv 為準
                    stats["boss_edge_skipped_creature_here"] += 1
                    log_unmatched("boss_is_creature_here", f"{r['name']} @ {node_props[luid]['name']}", loc_key, src)
                    continue
                kept.append((luid, how))
            locs = kept
            for luid, how in locs:
                o = owner(luid)
                if o == buid:
                    boss_loc[buid].add(luid)
                rel_sources[(o, luid)].add("bosses.csv")
                add_edge("LOCATED_AT", o, luid, src, runes=runes, match=how)
            at_owners = [(node_props[u]["name"], owner(u)) for u, _ in locs] or [(loc_name, buid)]
            for d in drops:
                for tuid, note in (item_targets(d, src, bdlc) or []):
                    for at, o in at_owners:
                        add_edge("DROPS", o, tuid, src, at_location=at, note=note)

    # locations.csv 的 bosses / npcs / creatures / items 清單
    rows, src = load("locations.csv")
    boss_by_base = defaultdict(list)
    for uid, p in node_props.items():
        if uid.startswith("Boss:"):
            boss_by_base[norm(re.sub(r"\s*\(.*\)$", "", p["name"]))].append(uid)
    # 其他欄位裡出現過的物品字串（用來判斷 npcs／creatures 欄位裡哪些其實是物品）
    item_strings = set()
    for r in rows:
        item_strings.update(norm(x) for x in parse_list(r["items"]))
    for cr in load("creatures.csv")[0]:
        item_strings.update(norm(x) for x in parse_list(cr["drops"]))
    for r in rows:
        luid = f"Location:locations:{r['id']}"
        ldlc = node_props[luid]["dlc"]
        for b in parse_list(r["bosses"]):
            if is_noise(b):
                stats["noise_skipped"] += 1
                continue
            cands = boss_by_base.get(ALIASES.get(norm(b), norm(b)), [])
            if not cands:
                u = resolve(b, ["Boss"]) or stub("Boss", b, src, ldlc)
                cands = [u]
                boss_by_base[norm(b)] = cands
            at = [c for c in cands if luid in boss_loc[c]]
            for c in (at or cands[:1]):
                rel_sources[(c, luid)].add("locations.csv")
                if luid not in boss_loc[c]:
                    add_edge("LOCATED_AT", c, luid, src, match="from_location_list")
                    boss_loc[c].add(luid)
        for label, col in (("NPC", "npcs"), ("Creature", "creatures")):
            for n in parse_list(r[col]):
                if is_noise(n):
                    stats["noise_skipped"] += 1
                    continue
                uid = resolve(n, [label])
                if not uid and (resolve(n, NON_CREATURE_ITEM_LIKE) or norm(n) in item_strings):
                    log_unmatched("column_contaminated", f"{r['name']} [{col}]", n, src)   # 欄位裡放的其實是物品
                    for tuid, note in (item_targets(n, src, ldlc) or []):
                        add_edge("LOCATED_AT", tuid, luid, src, note=f"listed in {col} column")
                    continue
                uid = uid or stub(label, n, src, ldlc)
                add_edge("LOCATED_AT", uid, luid, src)
        for it in parse_list(r["items"]):
            for tuid, note in (item_targets(it, src, ldlc) or []):
                add_edge("LOCATED_AT", tuid, luid, src, note=note)

    # Creature -DROPS-> 物品
    rows, src = load("creatures.csv")
    for r in rows:
        cuid = f"Creature:creatures:{r['id']}"
        cdlc = node_props[cuid]["dlc"]
        for d in parse_list(r["drops"]):
            for tuid, note in (item_targets(d, src, cdlc) or []):
                add_edge("DROPS", cuid, tuid, src, note=note)

    # 紀念品：Boss -DROPS-> 紀念品（補充來源）、紀念品 -EXCHANGES_FOR-> 兌換物
    rows, src = load("items/remembrances.csv")
    LABEL_BY_PREFIX = {"Weapon": "Weapon", "Incantation": "Spell", "Sorcery": "Spell", "Talisman": "Talisman",
                       "Reusable Tool": "Item", "Ash of War": "AshOfWar"}
    for r in rows:
        ruid = f"Item:remembrances:{r['id']}"
        ruid = MERGED.get(ruid, ruid)      # 這一列的節點若被併進同名的另一個，改用保留的那個
        rdlc = node_props[ruid]["dlc"]
        bs = boss_by_base.get(ALIASES.get(norm(r["boss"]), norm(r["boss"]))) or [resolve(r["boss"], ["Boss"]) or stub("Boss", r["boss"], src, rdlc)]
        for b in bs:
            add_edge("DROPS", b, ruid, src, at_location="", note="from remembrances.csv")
        for opt in ("option 1", "option 2"):
            for piece in re.split(r"\s*/\s*", r[opt]):
                piece = piece.strip()
                if not piece:
                    continue
                m = re.match(r"^(Weapon|Incantation|Sorcery|Talisman|Reusable Tool|Ash of War)\s*:\s*(.*)$", piece)
                prefix, name = (m.group(1), m.group(2).strip()) if m else (None, piece)
                name = re.sub(r"^Ash of War:\s*", "", name)
                uid = resolve(name, ITEM_LIKE) or resolve("Ash of War: " + name, ITEM_LIKE)
                if not uid:
                    uid = stub(LABEL_BY_PREFIX.get(prefix, "Item"), name, src, rdlc)
                add_edge("EXCHANGES_FOR", ruid, uid, src, option=opt[-1])

    # Weapon/Shield -HAS_SKILL-> Skill；AshOfWar -GRANTS-> Skill
    for label in ("Weapon", "Shield", "AshOfWar"):
        rel = "GRANTS" if label == "AshOfWar" else "HAS_SKILL"
        for uid, p in list(node_props.items()):
            if uid.startswith(label + ":") and p.get("skill"):
                if is_noise(p["skill"]) or p["skill"].strip() in ("--", "-"):
                    stats["noise_skipped"] += 1
                    continue
                sk = resolve(p["skill"], ["Skill"]) or stub("Skill", p["skill"], p["source_file"], p["dlc"])
                add_edge(rel, uid, sk, p["source_file"])

    for e in edges["LOCATED_AT"]:                       # 記錄每條 Boss↔地點的關係是哪個檔案說的
        k = (e["a"], e["b"])
        if k in rel_sources:
            e["props"]["sources"] = sorted(rel_sources[k])


# ---------------------------------------------------------------- boss_stats 合併

def attach_aliases():
    """把別名表寫成目標節點的 aliases 屬性，讓查詢工具（S4）只讀圖就認得別名，
    例如問句的 'Rennala, Queen of the Full Moon' 指向 Boss 'Rennala Carian Queen of the Full Moon'。"""
    for text, target in [*ALIAS_TEXT.items(), *LOCATION_ALIAS_TEXT.items()]:
        for _, uid in name_index.get(norm(target), []):
            aliases = node_props[uid].setdefault("aliases", [])
            if text not in aliases:
                aliases.append(text)


def merge_boss_stats():
    rows = list(csv.DictReader(STATS_CSV.open(encoding="utf-8", newline="")))
    boss_keys = defaultdict(list)
    for uid, p in node_props.items():
        if uid.startswith("Boss:"):
            boss_keys[norm(p["name"])].append(uid)
            boss_keys[norm(re.sub(r"\s*\(.*\)$", "", p["name"]))].append(uid)
    for r in rows:
        variants = [norm(r["boss"]), norm(re.sub(r"\s*\(.*\)$", "", r["boss"]))]
        uids, how = None, "exact"
        for v in variants:
            if v in boss_keys:
                uids = boss_keys[v]
                break
        if not uids:
            close = difflib.get_close_matches(variants[-1], list(boss_keys), n=1, cutoff=0.92)
            if close:
                uids, how = boss_keys[close[0]], f"fuzzy:{close[0]}"
        if not uids:
            toks = set(variants[-1].split())
            subs = [k for k in boss_keys if len(toks) >= 2 and (toks <= set(k.split()) or set(k.split()) <= toks) and len(set(k.split())) >= 2]
            if len(subs) == 1:
                uids, how = boss_keys[subs[0]], f"subset:{subs[0]}"
        if not uids:
            uids = [stub("Boss", r["boss"], "data/raw/boss_stats/elden_ring_boss_stats_clean.csv", 0, dlc_unknown=True)]
            how = "stub_from_boss_stats"
        stats["boss_stats_" + how.split(":")[0]] += 1
        for uid in set(uids):
            for k, v in r.items():
                if k == "boss" or v is None or v == "":
                    continue
                f = num(v)
                node_props[uid]["bs_" + snake(k)] = f if f is not None else v
            node_props[uid]["bs_match"] = how


# ---------------------------------------------------------------- 寫入 Neo4j

def write_graph(driver):
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        s.run("CREATE CONSTRAINT entity_uid IF NOT EXISTS FOR (n:Entity) REQUIRE n.uid IS UNIQUE")
        s.run("CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)")
        for label, rows in nodes.items():
            for i in range(0, len(rows), 500):
                # 改寫過的 props（如 boss_stats 合併）以 node_props 為準
                batch = [node_props[p["uid"]] for p in rows[i:i + 500]]
                s.run(f"UNWIND $rows AS r CREATE (n:Entity:{label}) SET n = r", rows=batch)
        for etype, rows in edges.items():
            for i in range(0, len(rows), 1000):
                s.run(f"UNWIND $rows AS r MATCH (a:Entity {{uid: r.a}}), (b:Entity {{uid: r.b}}) "
                      f"CREATE (a)-[e:{etype}]->(b) SET e = r.props", rows=rows[i:i + 1000])


def main():
    load_dotenv(ROOT / ".env")
    loc_rows = build_nodes()
    merge_duplicate_items()
    build_edges(loc_rows)
    merge_boss_stats()
    attach_aliases()

    driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    write_graph(driver)
    driver.close()

    UNMATCHED_CSV.parent.mkdir(parents=True, exist_ok=True)
    with UNMATCHED_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "context", "text", "source_file"])
        w.writeheader()
        w.writerows(unmatched)

    with FUZZY_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["how", "text", "matched_to", "label"])
        w.writeheader()
        w.writerows(fuzzy_log)
    with STUBS_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "name", "source_file"])
        w.writeheader()
        w.writerows(stubs)

    with ITEM_MERGE_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kept", "merged", "name", "merged_name", "conflicts"])
        w.writeheader()
        w.writerows(MERGE_LOG)

    print("同名 Item 合併:", stats["items_merged"], "個節點併入保留的節點（稽核：graph_item_merges.csv）")
    print("stub 節點:", dict(Counter(x["label"] for x in stubs)), "合計", len(stubs))
    print("節點:", {k: len(v) for k, v in nodes.items()}, "合計", sum(len(v) for v in nodes.values()))
    print("邊:", {k: len(v) for k, v in edges.items()}, "合計", sum(len(v) for v in edges.values()))
    print("未命中:", dict(Counter(u["kind"] for u in unmatched)), "合計", len(unmatched))
    print("其他:", dict(stats))


if __name__ == "__main__":
    main()
