"""唯讀稽核：bosses.csv 與 locations.csv 對 Boss↔地點 的說法一不一致，依 LOCATED_AT 邊的 `sources` 屬性分類。

需要先跑過 build_graph.py。不修改資料庫。
    python3 src/graph/audit_boss_locations.py [--show N]
"""
import argparse
import os
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=3, help="每一類顯示幾個例子")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    d = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    with d.session() as s:
        rows = s.run("MATCH (b:Boss)-[e:LOCATED_AT]->(l:Location) "
                     "RETURN l.name AS loc, l.stub AS loc_stub, b.name AS boss, b.stub AS stub, e.sources AS sources, e.match AS how").data()
    d.close()
    cat, ex, locs = Counter(), defaultdict(list), set()
    for r in rows:
        src = tuple(r["sources"] or [])
        if src == ("bosses.csv", "locations.csv"):
            cat["兩邊都有"] += 1
            continue
        if src == ("bosses.csv",) and r["loc_stub"]:
            cat["只在 bosses.csv：地點是 stub（locations.csv 沒有這個地點，不算真的不一致）"] += 1
            continue
        locs.add(r["loc"])
        if src == ("bosses.csv",):
            key = ("只在 bosses.csv：地點精確對上，但 locations.csv 的 boss 清單沒列（B4）" if r["how"] == "exact"
                   else "只在 bosses.csv：地點靠字串掃描推得（B3）")
        else:
            key = ("只在 locations.csv：bosses.csv 無此列（A1，stub）" if r["stub"]
                   else "只在 locations.csv：bosses.csv 有此 boss 但沒寫這個地點（A2）")
        cat[key] += 1
        ex[key].append((r["loc"], r["boss"]))
    print(f"Boss↔地點 關係共 {len(rows)} 條；不一致的地點 {len(locs)} 個")
    for k, n in cat.most_common():
        print(f"\n{k}: {n} 條")
        for loc, b in ex[k][:args.show]:
            print(f"    {loc} ← {b}")


if __name__ == "__main__":
    main()
