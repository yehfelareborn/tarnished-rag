"""S4 完成標準：用題庫的關係題與多跳題測試圖檢索工具，確認能取回標準答案需要的資訊。

不經過 LLM：每個題型家族對應一組固定的工具呼叫（由我事先定，不是模型挑的），
把工具取回的實體名稱從標準答案文字裡扣掉，若還剩下實體名稱（扣掉連接詞後仍有文字）就算漏了。
這只驗證「工具能取回資訊」，不是回答正確率；LLM 怎麼挑工具、怎麼組答案是 S5 的事。

    python3 eval/graph_tools_check.py            # 輸出每題結果與彙總，寫入 eval/results/graph_tools_check.json
需要 Neo4j 在跑且已建圖。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "graph"))
from tools import GraphTools, norm  # noqa: E402

STOP = {"and", "or", "the", "x", "from", "by", "defeating", "at", "of", "is", "other", "option", "options",
        "weapon", "sorcery", "incantation", "talisman", "ash", "war", "a", "an", "to", "in"}
# 需要先理解「主線 boss」這類說法才能決定要查什麼，留給 S5 的 LLM
NEEDS_REASONING = {"q07", "q09", "q76", "q77"}


def neighbors(t, name, relation, direction, target_label=None, label=None):
    r = t.get_neighbors(name, relation=relation, direction=direction, target_label=target_label, label=label, limit=500)
    if "error" in r:
        return None, r["error"]
    out = [n for res in r["results"] for n in res["neighbors"]]
    return out, None


def names_of(ns):
    """鄰居的名稱；DROPS 邊若是展開的套裝（note: via set: X Set），也把套裝名稱算進去。"""
    names = set()
    for n in ns:
        names.add(n["entity"]["name"])
        note = n["edge"].get("note") or ""
        if note.startswith("via set:"):
            names.add(note.split(":", 1)[1].strip())
    return names


def variants(name):
    """一個實體名稱的比對用寫法：原名、去尾端括號（'X (Belurat, ...)'）、去類別前綴（'Ash of War: X'），都做正規化。
    正規化與工具、建圖一致（去標點、修 theX 黏字、小寫），所以來源資料的黏字不會造成誤判。"""
    raw = {name, re.sub(r"\s*\([^()]*\)\s*$", "", name), re.sub(r"^[A-Za-z ]{3,20}:\s+", "", name)}
    return {norm(x) for x in raw if norm(x)}


def leftover(gold, names):
    """把工具取回的實體名稱從標準答案扣掉，回傳還剩下的字（扣掉連接詞後）。空 = 標準答案的實體都取回了。"""
    g = " " + norm(gold.replace("(", " zzopen ").replace(")", " zzclose ")) + " "
    for n in sorted({v for name in names for v in variants(name)}, key=len, reverse=True):
        g = g.replace(f" {n} ", " ")
    g = re.sub(r"zzopen.*?zzclose", " ", g)             # 括號裡是說明文字（例如 the other option is ...），實體名稱已在上一步扣掉
    return [w for w in re.findall(r"[a-z]+", g) if w not in STOP]


def first_mention(t, text, label):
    for m in t.link_entities(text)["mentions"]:
        cands = [c for c in m["candidates"] if c["label"] == label and not c["stub"]] or [c for c in m["candidates"] if c["label"] == label]
        if cands:
            return cands[0]
    return None


def run_question(t, q):
    qid, text, gold = q["id"], q["question"], q["answer"]
    if qid in NEEDS_REASONING:
        return "SKIP", "需要理解「主線 boss」等說法，交給 S5 的 LLM", set(), ""
    m = re.match(r"^What items are dropped by defeating (.+)\?$", text)
    if m:
        ns, err = neighbors(t, m.group(1), "DROPS", "out", label="Boss")
        return ("FAIL", err, set(), "Boss 的掉落物") if err else ("", "", names_of(ns), "Boss 的掉落物")
    m = re.match(r"^Which (bosses|NPCs) can be (?:fought|found) at (.+)\?$", text)
    if m:
        ns, err = neighbors(t, m.group(2), "LOCATED_AT", "in", target_label="Boss" if m.group(1) == "bosses" else "NPC")
        return ("FAIL", err, set(), "地點的 " + m.group(1)) if err else ("", "", names_of(ns), "地點的 " + m.group(1))
    if "remembrance dropped by" in text:
        boss = first_mention(t, text.split("dropped by", 1)[1], "Boss")
        if not boss:
            return "FAIL", "問句中連不到 Boss 實體", set(), "紀念品換什麼"
        drops, err = neighbors(t, boss["uid"], "DROPS", "out", target_label="Item")
        if err:
            return "FAIL", err, set(), "紀念品換什麼"
        opts = set()
        for n in drops:
            if n["entity"]["uid"].startswith("Item:remembrances:"):        # 用來源檔判斷，因為有的叫 "Elden Remembrance"
                ex, _ = neighbors(t, n["entity"]["uid"], "EXCHANGES_FOR", "out")
                opts |= names_of(ex or [])
        return "", "", opts, "紀念品換什麼"
    if "remembrance can be exchanged for" in text:
        w = first_mention(t, text.split("exchanged for", 1)[1], "Weapon")
        if not w:
            return "FAIL", "問句中連不到 Weapon 實體", set(), "武器反查 boss"
        rems, _ = neighbors(t, w["uid"], "EXCHANGES_FOR", "in")
        bosses = set()
        for n in rems or []:
            bs, _ = neighbors(t, n["entity"]["uid"], "DROPS", "in", target_label="Boss")
            bosses |= names_of(bs or [])
        return "", "", bosses, "武器反查 boss"
    m = re.match(r"^Which character at (.+?) is listed both as", text)
    if m:
        npcs, err = neighbors(t, m.group(1), "LOCATED_AT", "in", target_label="NPC")
        bosses, err2 = neighbors(t, m.group(1), "LOCATED_AT", "in", target_label="Boss")
        if err or err2:
            return "FAIL", err or err2, set(), "既是 NPC 又是 Boss"
        a, b = {norm(x): x for x in names_of(npcs)}, {norm(x): x for x in names_of(bosses)}
        return "", "", {a[k] for k in a.keys() & b.keys()}, "既是 NPC 又是 Boss"   # 正規化後名稱相同才算同一個角色（圖裡沒有 SAME_AS）
    return "SKIP", "沒有對應的固定呼叫", set(), "未分類"


def main():
    qs = [json.loads(l) for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8")]
    qs = [q for q in qs if q["type"] in ("relational", "multi_hop")]
    rows = []
    with GraphTools() as t:
        for q in qs:
            status, note, names, family = run_question(t, q)
            if status == "":
                left = leftover(q["answer"], names)
                status = "PASS" if names and not left else "FAIL"
                note = "" if status == "PASS" else (f"標準答案裡還有沒取回的字：{left}" if names else "工具沒取回任何實體")
            rows.append({"id": q["id"], "type": q["type"], "family": family, "status": status, "note": note,
                         "returned": sorted(names)[:12]})
    for r in rows:
        print(f'{r["id"]:>4} {r["status"]:<5} [{r["family"]}] {r["note"]}')
    c = Counter((r["type"], r["status"]) for r in rows)
    print("\n彙總：")
    for typ in ("relational", "multi_hop"):
        n = sum(v for (ty, _), v in c.items() if ty == typ)
        print(f'  {typ}: {n} 題；PASS {c[(typ, "PASS")]}、FAIL {c[(typ, "FAIL")]}、SKIP {c[(typ, "SKIP")]}')
    out = ROOT / "eval" / "results" / "graph_tools_check.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"寫入 {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
