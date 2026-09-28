"""S4 圖檢索工具的單元測試。

需要 Neo4j 在跑，而且已經跑過 build_graph.py；連不上時整份測試會 skip，不會失敗。
    python3 -m pytest tests/test_graph_tools.py -v

預期值來源：eval/questions.jsonl 的標準答案（q06、q09、q59–q64、q60、q72）與 docs/graph-schema.md 記錄的圖狀態。
圖重建後這些預期值仍應成立；如果改了資料而預期值變了，先確認是資料改動造成的，再更新測試。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "graph"))

import build_graph  # noqa: E402
import tools  # noqa: E402


@pytest.fixture(scope="module")
def t():
    try:
        gt = tools.GraphTools()
    except Exception as e:      # 連不上 Neo4j、缺 .env 等
        pytest.skip(f"Neo4j 不可用：{e}")
    yield gt
    gt.close()


def neighbor_names(res, index=0):
    return {n["entity"]["name"] for n in res["results"][index]["neighbors"]}


# ---------------------------------------------------------------- 名稱正規化

@pytest.mark.parametrize("s", ["Wolf's Assault", "theBlasphemous Blade", "Élan  Sword", "Ash of War: Flame Skewer",
                               "Golden Rune [5]", "Rykard, Lord of Blasphemy", "", None, "Mohg’s Great Rune"])
def test_norm_matches_build_graph(s):
    """工具的名稱正規化必須與建圖時完全一致，否則連結會對不上。"""
    assert tools.norm(s) == build_graph.norm(s)


# ---------------------------------------------------------------- resolve

def test_resolve_exact(t):
    r = t.resolve("Volcano Manor")
    assert [(m["label"], m["match"]) for m in r] == [("Location", "exact")]


def test_resolve_short_name_before_comma(t):
    uids = {m["uid"]: m["match"] for m in t.resolve("Rykard")}
    assert uids.get("Boss:bosses:17") == "partial"


def test_resolve_label_filter(t):
    r = t.resolve("Rykard", label="NPC")
    assert r and all(m["label"] == "NPC" for m in r)


def test_resolve_by_uid(t):
    r = t.resolve("Boss:bosses:17")
    assert len(r) == 1 and r[0]["match"] == "uid" and r[0]["name"] == "Rykard, Lord of Blasphemy"


def test_resolve_typo_is_fuzzy(t):
    r = t.resolve("Volcano Manorr")
    assert r and r[0]["name"] == "Volcano Manor" and r[0]["match"].startswith("fuzzy")


def test_resolve_alias(t):
    """問句（與題庫）用 'Rennala, Queen of the Full Moon'，Boss 節點叫 'Rennala Carian Queen of the Full Moon'，
    NPC 節點才叫問句那個名字。別名寫在 Boss 節點的 aliases 屬性上（build_graph.attach_aliases）。"""
    boss = t.resolve("Rennala, Queen of the Full Moon", label="Boss")
    assert [(m["name"], m["match"]) for m in boss] == [("Rennala Carian Queen of the Full Moon", "alias")]
    # 不帶 label 時精確比對優先（只回 NPC），別名是後備；要 Boss 得指定 label（link_entities 則兩種候選都列）
    assert {m["label"] for m in t.resolve("Rennala, Queen of the Full Moon")} == {"NPC"}


def test_get_entity_exposes_aliases(t):
    m = t.get_entity("Rennala Carian Queen of the Full Moon", label="Boss")["matches"][0]
    assert "Rennala, Queen of the Full Moon" in m["properties"]["aliases"]


def test_resolve_unknown(t):
    assert t.resolve("zzzz no such entity") == []


def test_resolve_same_name_different_labels(t):
    """Patches 在圖裡是 Boss 與 NPC 兩個節點（使用者確認：Murkwater Cave 是 boss，其他地點是 NPC）。"""
    assert {m["label"] for m in t.resolve("Patches")} >= {"Boss", "NPC"}


# ---------------------------------------------------------------- link_entities

def test_link_entities_q09(t):
    """q09 的問句含所有格 "Volcano Manor's"，一開始漏掉了它。"""
    q = "Between the boss found at Volcano Manor's main story fight and Malenia, Blade of Miquella, which has higher HP?"
    mentions = [m["mention"] for m in t.link_entities(q)["mentions"]]
    assert mentions == ["volcano manor", "malenia blade of miquella"]     # 依出現順序


def test_link_entities_short_names(t):
    r = t.link_entities("Which has more HP, Rykard or Malenia?")
    assert [m["mention"] for m in r["mentions"]] == ["rykard", "malenia"]
    assert "Boss:bosses:17" in {c["uid"] for c in r["mentions"][0]["candidates"]}


def test_link_entities_merges_exact_and_alias_candidates(t):
    """題庫 q75：'Rennala, Queen of the Full Moon' 精確對到 NPC、別名才對到 Boss。兩個都要在候選裡。"""
    r = t.link_entities("What sorcery can be obtained by exchanging the remembrance dropped by Rennala, Queen of the Full Moon?")
    cands = r["mentions"][0]["candidates"]
    assert {c["label"] for c in cands} == {"NPC", "Boss"}
    assert cands[0]["match"] == "exact"              # 精確的排前面


def test_link_entities_no_entities(t):
    assert t.link_entities("Which bosses can be fought at")["mentions"] == []


# ---------------------------------------------------------------- get_entity

def test_get_entity_hp_is_int_and_has_source(t):
    """q09、q87：Rykard 89,613 HP、Malenia 33,251 HP。"""
    r = t.get_entity("Rykard, Lord of Blasphemy", label="Boss")
    m = r["matches"][0]
    assert m["properties"]["hp"] == 89613 and isinstance(m["properties"]["hp"], int)
    assert m["source"] == {"file": "data/processed/dlc_scrape/bosses.csv", "row_id": "17"}
    assert "hp" not in m.get("boss_stats", {}) and "health_total" in m["boss_stats"]   # bs_* 另外分組、去掉前綴
    assert t.get_entity("Malenia", label="Boss")["matches"][0]["properties"]["hp"] == 33251


def test_get_entity_fields_filter(t):
    m = t.get_entity("Rykard, Lord of Blasphemy", label="Boss", fields=["hp"])["matches"][0]
    assert m["properties"] == {"hp": 89613} and "boss_stats" not in m


def test_get_entity_ambiguous_returns_all_with_note(t):
    r = t.get_entity("Rykard")
    assert {m["label"] for m in r["matches"]} == {"Boss", "NPC"} and "note" in r


def test_get_entity_unknown(t):
    assert "error" in t.get_entity("zzzz no such entity")


# ---------------------------------------------------------------- get_neighbors

def test_neighbors_q06_volcano_manor_bosses(t):
    r = t.get_neighbors("Volcano Manor", relation="LOCATED_AT", direction="in", target_label="Boss")
    assert neighbor_names(r) == {"Abductor Virgins", "God-Devouring Serpent", "Godskin Noble", "Magma Wyrm",
                                 "Rykard, Lord of Blasphemy"}


def test_neighbors_q60_belurat_bosses(t):
    r = t.get_neighbors("Belurat Tower Settlement", relation="LOCATED_AT", direction="in", target_label="Boss")
    assert neighbor_names(r) == {"Divine Beast Dancing Lion (Belurat, Tower Settlement)", "Ulcerated Tree Spirit"}


@pytest.mark.parametrize("location,expected", [
    ("Scorpion River Catacombs", {"Death Knight"}),                     # q59
    ("Groveside Cave", {"Beastman of Farum Azula"}),                    # q61
    ("Impaler's Catacombs", {"Erdtree Burial Watchdog"}),               # q62
    ("Cliffbottom Catacombs", {"Erdtree Burial Watchdog"}),             # q63
    ("Lux Ruins", {"Demi-Human Queen Gilika"}),                         # q64
])
def test_neighbors_relational_questions(t, location, expected):
    r = t.get_neighbors(location, relation="LOCATED_AT", direction="in", target_label="Boss")
    assert neighbor_names(r) == expected


def test_neighbors_edges_carry_provenance(t):
    """Boss↔地點的邊帶 sources；符文數放在邊上。"""
    r = t.get_neighbors("Volcano Manor", relation="LOCATED_AT", direction="in", target_label="Boss")
    edges = {n["entity"]["name"]: n["edge"] for n in r["results"][0]["neighbors"]}
    assert all(e["sources"] for e in edges.values())
    assert edges["Rykard, Lord of Blasphemy"]["runes"] == 130000
    assert edges["God-Devouring Serpent"]["sources"] == ["locations.csv"]     # 只有 locations.csv 有寫（A2）


def test_neighbors_drops_direction(t):
    r = t.get_neighbors("Malenia, Blade of Miquella", relation="DROPS", direction="out")
    assert "Remembrance of the Rot Goddess" in neighbor_names(r)
    assert all(n["direction"] == "out" for n in r["results"][0]["neighbors"])
    assert t.get_neighbors("Volcano Manor", relation="LOCATED_AT", direction="out")["results"][0]["neighbors"] == []


def test_neighbors_limit_and_truncated(t):
    r = t.get_neighbors("Volcano Manor", limit=2)["results"][0]
    assert len(r["neighbors"]) == 2 and r["truncated"] is True and r["total"] > 2


def test_neighbors_same_name_entities_listed_separately(t):
    r = t.get_neighbors("Patches", relation="LOCATED_AT", direction="out")
    by_label = {x["entity"]["label"]: x for x in r["results"]}
    assert set(by_label) >= {"Boss", "NPC"}
    assert {n["entity"]["name"] for n in by_label["Boss"]["neighbors"]} == {"Murkwater Cave"}    # 只有 Murkwater Cave 是 boss 身分
    assert "Volcano Manor" in {n["entity"]["name"] for n in by_label["NPC"]["neighbors"]}


def test_neighbors_validation(t):
    assert "error" in t.get_neighbors("Volcano Manor", relation="KILLS")
    assert "error" in t.get_neighbors("Volcano Manor", direction="sideways")
    assert "error" in t.get_neighbors("Volcano Manor", target_label="Dragon")
    assert "error" in t.get_neighbors("Volcano Manor", limit=0)
    assert "error" in t.get_neighbors("zzzz no such entity")


# ---------------------------------------------------------------- find_path

def test_find_path_remembrance_exchange(t):
    """q72：Malenia → 紀念品 → Hand of Malenia。"""
    r = t.find_path("Malenia, Blade of Miquella", "Hand of Malenia")
    p = r["paths"][0]
    assert p["length"] == 2
    assert [e["relation"] for e in p["edges"]] == ["DROPS", "EXCHANGES_FOR"]
    assert [n["name"] for n in p["nodes"]] == ["Malenia, Blade of Miquella", "Remembrance of the Rot Goddess", "Hand of Malenia"]


def test_find_path_hop_limit(t):
    r = t.find_path("Volcano Manor", "Hand of Malenia", max_hops=1)
    assert r["paths"] == [] and "note" in r


def test_find_path_excludes_located_in_by_default(t):
    default = t.find_path("Volcano Manor", "Legacy Dungeons")
    assert all(e["relation"] != "LOCATED_IN" for p in default.get("paths", []) for e in p["edges"])
    only = t.find_path("Volcano Manor", "Legacy Dungeons", relations=["LOCATED_IN"])     # Volcano Manor 位於 Legacy Dungeons
    assert only["paths"][0]["length"] == 1


def test_find_path_validation(t):
    assert "error" in t.find_path("zzzz no such entity", "Hand of Malenia")
    assert "error" in t.find_path("Volcano Manor", "zzzz no such entity")
    assert "error" in t.find_path("Volcano Manor", "Hand of Malenia", relations=["KILLS"])
    assert "error" in t.find_path("Volcano Manor", "Hand of Malenia", max_hops=99)


# ---------------------------------------------------------------- 同名 Item 合併（build_graph.merge_duplicate_items）

def test_no_duplicate_item_names_left_except_excluded(t):
    """合併後，非 stub 的 Item 只剩兩組同名：不合併的 Lord of Blood's Favor（2 份）與 Unalloyed Gold Needle（3 份）。"""
    from collections import defaultdict
    groups = defaultdict(list)
    for e in t.by_uid.values():
        if e["label"] == "Item" and not e["stub"]:
            groups[tools.norm(e["name"])].append(e["uid"])
    assert {k: len(v) for k, v in groups.items() if len(v) > 1} == {
        tools.norm("Lord of Blood's Favor"): 2, tools.norm("Unalloyed Gold Needle"): 3}


def test_merged_remembrance_has_both_halves(t):
    """Remembrance of the Rot Goddess 在 consumables.csv（效果）與 remembrances.csv（兌換選項、boss）各一列，合併後是同一個節點。"""
    assert [m["uid"] for m in t.resolve("Remembrance of the Rot Goddess", label="Item")] == ["Item:remembrances:21"]
    p = t.get_entity("Item:remembrances:21")["matches"][0]["properties"]
    assert p["merged_from"] == ["Item:consumables:185"] and p["item_types"] == ["remembrances", "consumables"]
    assert p["effect"].startswith("Take the power of its namesake")            # 補自 consumables.csv
    assert p["boss"] == "Malenia, Blade of Miquella" and p["option_1"]         # remembrances.csv 原有
    relations = {n["relation"] for n in t.get_neighbors("Item:remembrances:21")["results"][0]["neighbors"]}
    assert {"DROPS", "EXCHANGES_FOR"} <= relations


def test_malenia_drops_the_merged_remembrance_node_only(t):
    """合併前 Malenia 的掉落會同時連到兩個同名節點，其中一個沒有 EXCHANGES_FOR。"""
    ns = t.get_neighbors("Malenia, Blade of Miquella", relation="DROPS", direction="out", label="Boss")["results"][0]["neighbors"]
    assert {n["entity"]["uid"] for n in ns if n["entity"]["name"] == "Remembrance of the Rot Goddess"} == {"Item:remembrances:21"}


def test_glued_name_keeps_correct_spelling_as_alias(t):
    """名稱黏字（theBlasphemous）依使用者決定不修；合併後正確拼法留在 aliases 裡。"""
    m = t.get_entity("Remembrance of the Blasphemous", label="Item")["matches"]
    assert [x["name"] for x in m] == ["Remembrance of theBlasphemous"]
    assert "Remembrance of the Blasphemous" in m[0]["properties"]["aliases"]


def test_larval_tear_merged_and_conflicting_values_kept(t):
    m = t.get_entity("Larval Tear", label="Item")["matches"]
    assert [x["uid"] for x in m] == ["Item:keyItems:6"] and m[0]["dlc"] == 0
    assert "Item:keyItems:64" in m[0]["properties"]["merged_variants"]         # 兩份不同的欄位值（location 佔位文字）沒有丟掉


def test_excluded_groups_stay_separate(t):
    assert len(t.resolve("Lord of Blood's Favor", label="Item")) == 2
    assert len(t.resolve("Unalloyed Gold Needle", label="Item")) == 3


def test_merge_audit_file_lists_every_merged_node():
    import csv
    log = ROOT / "data" / "processed" / "graph_item_merges.csv"
    assert log.exists()
    with log.open(encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 41                     # 41 組各併掉 1 個


# ---------------------------------------------------------------- filter_by_attribute

def test_filter_order_by_hp(t):
    """q87：Rykard 的 HP 遠高於 Morgott。最高的 boss 是 Rykard。"""
    r = t.filter_by_attribute("Boss", [{"field": "hp", "op": ">", "value": 0}], order_by="hp", descending=True, limit=3)
    assert r["results"][0]["name"] == "Rykard, Lord of Blasphemy" and r["results"][0]["values"]["hp"] == 89613
    hps = [x["values"]["hp"] for x in r["results"]]
    assert hps == sorted(hps, reverse=True) and r["total"] == 105        # 177 個 Boss 中 105 個 hp 能 parse 成數字


def test_filter_string_equals_is_case_insensitive(t):
    r = t.filter_by_attribute("Boss", [{"field": "name", "op": "=", "value": "malenia, blade of miquella"}], fields=["hp"])
    assert r["total"] == 1 and r["results"][0]["values"]["hp"] == 33251


def test_filter_contains_is_case_insensitive(t):
    lo = t.filter_by_attribute("Weapon", [{"field": "category", "op": "contains", "value": "katana"}])["total"]
    up = t.filter_by_attribute("Weapon", [{"field": "category", "op": "contains", "value": "KATANA"}])["total"]
    assert lo == up > 0


def test_filter_multiple_conditions_are_anded(t):
    """太刀類的力量需求最低是 10（資料本身如此），所以 str<=8 且太刀 = 0 筆。"""
    none = t.filter_by_attribute("Weapon", [{"field": "str", "op": "<=", "value": 8},
                                            {"field": "category", "op": "contains", "value": "katana"}])
    assert none["total"] == 0 and none["results"] == []
    some = t.filter_by_attribute("Weapon", [{"field": "str", "op": "<=", "value": 12},
                                            {"field": "category", "op": "contains", "value": "katana"}], fields=["str"], limit=50)
    assert some["total"] > 0 and all(x["values"]["str"] <= 12 for x in some["results"])


def test_filter_numeric_string_field(t):
    """Weapon.fp_cost 存成字串（'25'），數值比較要轉型。"""
    r = t.filter_by_attribute("Weapon", [{"field": "fp_cost", "op": ">=", "value": 20}], fields=["fp_cost"], limit=200)
    assert r["total"] > 0 and all(float(x["values"]["fp_cost"]) >= 20 for x in r["results"])


def test_filter_excludes_stubs_by_default(t):
    """131 個 stub 不計入；同名 Item 合併（41 組各併掉 1 個）前是 834／965。"""
    assert t.filter_by_attribute("Item", [])["total"] == 793
    assert t.filter_by_attribute("Item", [], include_stubs=True)["total"] == 924


def test_filter_order_by_excludes_missing_values(t):
    r = t.filter_by_attribute("Boss", [], order_by="hp", limit=200)
    assert all(x["values"]["hp"] is not None for x in r["results"])


def test_filter_truncated_flag(t):
    r = t.filter_by_attribute("Weapon", [], limit=5)
    assert len(r["results"]) == 5 and r["truncated"] is True


def test_filter_rejects_bad_input(t):
    bad_inputs = [
        ("Dragon", []),                                                                        # 不存在的標籤
        ("Weapon", [{"field": "nope", "op": "=", "value": 1}]),                                # 不存在的欄位
        ("Weapon", [{"field": "str`) RETURN 1 //", "op": "=", "value": 1}]),                   # 注入式欄位名
        ("Weapon", [{"field": "str", "op": "LIKE", "value": 1}]),                              # 未知運算子
        ("Weapon", [{"field": "str", "op": "<", "value": "abc"}]),                             # 數值運算子配字串
        ("Weapon", [{"field": "str", "op": "<"}]),                                             # 缺 value
        ("Weapon", "str<10"),                                                                  # conditions 不是清單
    ]
    for label, conds in bad_inputs:
        assert "error" in t.filter_by_attribute(label, conds), (label, conds)
    assert "error" in t.filter_by_attribute("Weapon", [], order_by="nope")
    assert "error" in t.filter_by_attribute("Weapon", [], limit=0)
    assert "error" in t.filter_by_attribute("Weapon", [], fields=["nope"])
