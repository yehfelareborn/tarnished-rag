"""S4：圖檢索工具（唯讀）。

四個預先定義的查詢工具加一個實體連結，給 S5 的 LLM 呼叫：
    get_entity(name, label=None, fields=None)
    get_neighbors(name, relation=None, direction="both", target_label=None, label=None, limit=50)
    find_path(a, b, max_hops=4, max_paths=3, relations=None, label_a=None, label_b=None)
    filter_by_attribute(label, conditions, order_by=None, descending=False, limit=20, fields=None, include_stubs=False)
    link_entities(text, min_len=5)

回傳值都是可 JSON 序列化的 dict；輸入有問題時回傳 {"error": ...}，不拋例外，讓 LLM 可以修正呼叫。
每個實體帶 source（檔案＋列號），每條邊帶建圖時記錄的來源屬性（source_file、sources 等），回答時可以引用。

需要先跑過 build_graph.py。連線資訊從專案根目錄 .env 讀。手動試用：
    python3 src/graph/tools.py get_neighbors '{"name": "Volcano Manor", "relation": "LOCATED_AT", "direction": "in", "target_label": "Boss"}'
"""
import difflib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import READ_ACCESS, GraphDatabase

ROOT = Path(__file__).resolve().parents[2]

RELATIONS = ("LOCATED_AT", "DROPS", "LOCATED_IN", "EXCHANGES_FOR", "HAS_SKILL", "GRANTS")
DIRECTIONS = ("in", "out", "both")
HOWS = ("exact", "alias", "base", "partial")     # 名稱比對類型，由嚴到寬
NUM_OPS = ("<", "<=", ">", ">=")
OPS = ("=", "!=", "contains") + NUM_OPS
INTERNAL = {"uid", "name", "dlc", "row_id", "source_file", "stub"}
FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def norm(s):
    """名稱正規化。必須與 build_graph.norm 完全一致（tests/test_graph_tools.py 有比對）。"""
    s = (s or "").replace("\xa0", " ")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\bthe([A-Z])", r"the \1", s)
    s = s.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _plain(v):
    """整數值的 float 轉成 int（89613.0 → 89613），讓輸出乾淨。"""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


class GraphTools:
    def __init__(self, driver=None):
        self._own_driver = driver is None
        if driver is None:
            load_dotenv(ROOT / ".env")
            driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                          auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
        self.driver = driver
        self._load_index()

    def close(self):
        if self._own_driver:
            self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ 內部
    def _run(self, cypher, **params):
        with self.driver.session(default_access_mode=READ_ACCESS) as s:
            return s.run(cypher, **params).data()

    def _load_index(self):
        """把所有節點的名稱載入記憶體（約 3900 個），供實體連結與名稱解析使用。"""
        rows = self._run("MATCH (n:Entity) RETURN n.uid AS uid, n.name AS name, "
                         "[x IN labels(n) WHERE x <> 'Entity'][0] AS label, n.dlc AS dlc, coalesce(n.stub, false) AS stub, "
                         "coalesce(n.aliases, []) AS aliases")
        self.by_uid = {r["uid"]: {"uid": r["uid"], "label": r["label"], "name": r["name"], "dlc": r["dlc"], "stub": r["stub"]}
                       for r in rows}
        self.index = defaultdict(lambda: defaultdict(list))     # 名稱 key -> 比對類型 -> [uid]
        for r in rows:
            name = r["name"] or ""
            full = norm(name)
            base = norm(re.sub(r"\s*\([^()]*\)\s*$", "", name))
            self.index[full]["exact"].append(r["uid"])
            for a in r["aliases"]:                  # 建圖時寫進節點的別名（build_graph.attach_aliases）
                if norm(a) and norm(a) != full:
                    self.index[norm(a)]["alias"].append(r["uid"])
            if base and base != full:
                self.index[base]["base"].append(r["uid"])
            if "," in name:
                head = norm(name.split(",")[0])
                if len(head) >= 4 and head not in (full, base):
                    self.index[head]["partial"].append(r["uid"])
        self.labels = sorted({e["label"] for e in self.by_uid.values()})
        keys = self._run("MATCH (n:Entity) WITH [x IN labels(n) WHERE x <> 'Entity'][0] AS l, n "
                         "UNWIND keys(n) AS k RETURN DISTINCT l, k")
        self.fields = defaultdict(set)
        for r in keys:
            self.fields[r["l"]].add(r["k"])

    def _sort(self, uids):
        """非 stub 排前面，其次依標籤與名稱，結果固定。"""
        return sorted(dict.fromkeys(uids), key=lambda u: (self.by_uid[u]["stub"], self.by_uid[u]["label"], self.by_uid[u]["name"]))

    def resolve(self, name, label=None):
        """名稱（或 uid）→ 候選節點清單。順序：uid → 精確 → 別名 → 去括號 → 逗號前的簡稱 → 模糊比對；每筆帶 match 類型。
        前面的比對類型若在 label 篩選後沒有結果，就繼續往後找。"""
        if name in self.by_uid:
            e = self.by_uid[name]
            return [dict(e, match="uid")] if label in (None, e["label"]) else []
        key = norm(name)
        if not key:
            return []
        for how in HOWS:
            uids = [u for u in self.index.get(key, {}).get(how, []) if label in (None, self.by_uid[u]["label"])]
            if uids:
                return [dict(self.by_uid[u], match=how) for u in self._sort(uids)]
        close = difflib.get_close_matches(key, list(self.index), n=3, cutoff=0.9)
        close = [k for k in close if re.findall(r"\d+", k) == re.findall(r"\d+", key)]
        out = []
        for k in close:
            score = difflib.SequenceMatcher(None, key, k).ratio()
            for uids in self.index[k].values():
                out += [dict(self.by_uid[u], match=f"fuzzy:{score:.2f}") for u in uids if label in (None, self.by_uid[u]["label"])]
        return out[:5]

    def _summary(self, uid):
        e = self.by_uid[uid]
        return {"uid": uid, "label": e["label"], "name": e["name"], "dlc": e["dlc"], "stub": e["stub"]}

    @staticmethod
    def _not_found(name, label):
        hint = f"（限定標籤 {label}）" if label else ""
        return {"error": f"找不到實體 {name!r}{hint}。可先用 link_entities 從問題文字找實體名稱。"}

    # ------------------------------------------------------------ 實體連結
    def link_entities(self, text, min_len=5):
        """掃描文字中的已知實體名稱（長的優先、互不重疊），回傳 [{mention, candidates}]，依出現順序。
        只做精確／去括號／逗號前簡稱的比對；名稱至少 min_len 個字元，避免短詞誤中。
        名稱後面多一個 s 也算命中（所有格 "Volcano Manor's"、複數），因為正規化會把撇號去掉，"manor's" 變成 "manors"。"""
        rest = f" {norm(text)} "
        found = []
        for key in sorted(self.index, key=len, reverse=True):
            if len(key) < min_len:
                continue
            for pat in (f" {key} ", f" {key}s "):
                pos = rest.find(pat)
                if pos >= 0:
                    break
            else:
                continue
            cands, seen = [], set()
            for how in HOWS:                        # 各比對類型的候選合併，精確的排前面（同一節點只列一次）
                for u in self._sort(self.index[key].get(how, [])):
                    if u not in seen:
                        seen.add(u)
                        cands.append(dict(self._summary(u), match=how))
            found.append((pos, {"mention": key, "candidates": cands}))
            rest = rest.replace(pat, " " + "#" * (len(pat) - 2) + " ")   # 佔位，長度不變所以位置不變
        return {"mentions": [m for _, m in sorted(found, key=lambda x: x[0])]}

    # ------------------------------------------------------------ get_entity
    def get_entity(self, name, label=None, fields=None):
        """取得實體與所有屬性。重名時回傳所有候選（可用 label 縮小）。
        fields：只回傳指定的屬性（例如 ["hp", "weight"]）。Boss 的 bs_* 抗性／傷害數值放在 boss_stats。"""
        matches = self.resolve(name, label)
        if not matches:
            return self._not_found(name, label)
        rows = self._run("MATCH (n:Entity) WHERE n.uid IN $uids RETURN n.uid AS uid, properties(n) AS p",
                         uids=[m["uid"] for m in matches])
        props = {r["uid"]: r["p"] for r in rows}
        want = set(fields) if fields else None
        out = []
        for m in matches[:5]:
            p = props[m["uid"]]
            body = {k: v for k, v in p.items() if k not in INTERNAL and not k.startswith("bs_") and (want is None or k in want)}
            stats = {k[3:]: v for k, v in p.items() if k.startswith("bs_") and (want is None or k in want or k[3:] in want)}
            e = dict(self._summary(m["uid"]), match=m["match"], properties=_plain(body),
                     source={"file": p.get("source_file"), "row_id": p.get("row_id")})
            if stats:
                e["boss_stats"] = _plain(stats)
            out.append(e)
        res = {"query": name, "matches": out}
        if len(matches) > 1:
            res["note"] = f"有 {len(matches)} 個同名或相近的實體，請依 label／uid 判斷是哪一個"
        return res

    # ------------------------------------------------------------ get_neighbors
    def get_neighbors(self, name, relation=None, direction="both", target_label=None, label=None, limit=50):
        """某實體的相鄰實體與邊。
        relation：LOCATED_AT／DROPS／LOCATED_IN／EXCHANGES_FOR／HAS_SKILL／GRANTS。direction：out＝從此實體出發，in＝指向此實體。
        例：某地點的 Boss = name=地點, relation=LOCATED_AT, direction=in, target_label=Boss；
            某 Boss 的掉落物 = name=Boss, relation=DROPS, direction=out。
        label：名稱重名時限定起點實體的標籤；target_label：只留下這種標籤的鄰居。"""
        if relation is not None and relation not in RELATIONS:
            return {"error": f"relation 必須是 {list(RELATIONS)} 其中之一，收到 {relation!r}"}
        if direction not in DIRECTIONS:
            return {"error": f"direction 必須是 {list(DIRECTIONS)} 其中之一，收到 {direction!r}"}
        if target_label is not None and target_label not in self.labels:
            return {"error": f"target_label 必須是 {self.labels} 其中之一，收到 {target_label!r}"}
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            return {"error": "limit 必須是 1～500 的整數"}
        matches = self.resolve(name, label)
        if not matches:
            return self._not_found(name, label)
        pat = {"out": "(a)-[e]->(b:Entity)", "in": "(a)<-[e]-(b:Entity)", "both": "(a)-[e]-(b:Entity)"}[direction]
        results = []
        for m in matches[:5]:
            rows = self._run(
                f"MATCH (a:Entity {{uid: $uid}}) MATCH {pat} "
                "WHERE ($rel IS NULL OR type(e) = $rel) AND ($tl IS NULL OR $tl IN labels(b)) "
                "RETURN type(e) AS relation, startNode(e).uid = a.uid AS outgoing, b.uid AS uid, properties(e) AS edge "
                "ORDER BY relation, b.name",
                uid=m["uid"], rel=relation, tl=target_label)
            neighbors = [{"relation": r["relation"], "direction": "out" if r["outgoing"] else "in",
                          "entity": self._summary(r["uid"]), "edge": _plain(r["edge"])} for r in rows]
            results.append({"entity": self._summary(m["uid"]), "match": m["match"], "total": len(neighbors),
                            "truncated": len(neighbors) > limit, "neighbors": neighbors[:limit]})
        res = {"query": name, "results": results}
        if len(matches) > 1:
            res["note"] = f"有 {len(matches)} 個同名或相近的實體，結果依實體分開列出"
        return res

    # ------------------------------------------------------------ find_path
    def find_path(self, a, b, max_hops=4, max_paths=3, relations=None, label_a=None, label_b=None):
        """兩個實體之間的最短關係路徑（不看邊的方向）。預設排除 LOCATED_IN（Region 會把同區域的一切連在一起）。
        relations：只允許這些關係。"""
        rels = list(relations) if relations else [r for r in RELATIONS if r != "LOCATED_IN"]
        bad = [r for r in rels if r not in RELATIONS]
        if bad:
            return {"error": f"relations 含未知的關係 {bad}，可用 {list(RELATIONS)}"}
        if not isinstance(max_hops, int) or not 1 <= max_hops <= 6:
            return {"error": "max_hops 必須是 1～6 的整數"}
        ma, mb = self.resolve(a, label_a), self.resolve(b, label_b)
        if not ma:
            return self._not_found(a, label_a)
        if not mb:
            return self._not_found(b, label_b)
        rows = self._run(
            f"MATCH (x:Entity), (y:Entity) WHERE x.uid IN $xs AND y.uid IN $ys AND x <> y "
            f"MATCH p = allShortestPaths((x)-[:{'|'.join(rels)}*1..{max_hops}]-(y)) "
            "RETURN [n IN nodes(p) | n.uid] AS nodes, "
            "[r IN relationships(p) | {relation: type(r), src: startNode(r).uid, dst: endNode(r).uid, edge: properties(r)}] AS edges, "
            "length(p) AS length ORDER BY length LIMIT 50",
            xs=[m["uid"] for m in ma], ys=[m["uid"] for m in mb])
        if not rows:
            return {"a": [self._summary(m["uid"]) for m in ma[:3]], "b": [self._summary(m["uid"]) for m in mb[:3]],
                    "paths": [], "note": f"在 {max_hops} 步內、關係 {rels} 之間找不到路徑"}
        shortest = rows[0]["length"]
        paths = [{"length": r["length"], "nodes": [self._summary(u) for u in r["nodes"]],
                  "edges": [{"relation": e["relation"], "from": e["src"], "to": e["dst"], "edge": _plain(e["edge"])} for e in r["edges"]]}
                 for r in rows if r["length"] == shortest][:max_paths]
        res = {"paths": paths}
        if len(ma) > 1 or len(mb) > 1:
            res["note"] = "起點或終點有重名的實體，這裡列的是所有組合中最短的路徑"
        return res

    # ------------------------------------------------------------ filter_by_attribute
    def filter_by_attribute(self, label, conditions, order_by=None, descending=False, limit=20, fields=None, include_stubs=False):
        """依屬性篩選某種標籤的實體。conditions = [{"field": "str", "op": "<=", "value": 20}, ...]，條件之間是 AND。
        op：=、!=、contains（不分大小寫）、<、<=、>、>=（數值比較，欄位若是數字字串會轉成數字，轉不了的視為不符）。
        order_by：依某數值欄位排序（沒有該欄位值的實體會被排除）。預設排除 stub。"""
        if label not in self.labels:
            return {"error": f"label 必須是 {self.labels} 其中之一，收到 {label!r}"}
        known = self.fields[label]

        def check_field(f):
            if not isinstance(f, str) or not FIELD_RE.match(f) or f not in known:
                return f"{label} 沒有欄位 {f!r}。可用欄位：{sorted(known)}"
            return None

        where, params, used = [], {}, []
        if not include_stubs:
            where.append("coalesce(n.stub, false) = false")
        if not isinstance(conditions, list):
            return {"error": "conditions 必須是清單，例如 [{'field': 'str', 'op': '<=', 'value': 20}]"}
        for i, c in enumerate(conditions):
            if not isinstance(c, dict) or not {"field", "op", "value"} <= set(c):
                return {"error": f"第 {i} 個條件必須有 field、op、value 三個鍵"}
            f, op, v = c["field"], c["op"], c["value"]
            if (err := check_field(f)):
                return {"error": err}
            if op not in OPS:
                return {"error": f"op 必須是 {list(OPS)} 其中之一，收到 {op!r}"}
            is_num = isinstance(v, (int, float)) and not isinstance(v, bool)
            if op in NUM_OPS and not is_num:
                return {"error": f"{op} 需要數值，收到 {v!r}"}
            params[f"v{i}"] = v
            col = f"n.`{f}`"
            if op in NUM_OPS:
                where.append(f"toFloatOrNull({col}) {op} $v{i}")
            elif op == "contains":
                where.append(f"toLower(toString({col})) CONTAINS toLower(toString($v{i}))")
            elif is_num:      # = 或 !=，值是數字：欄位轉成數字再比
                where.append(f"toFloatOrNull({col}) = $v{i}" if op == "=" else f"toFloatOrNull({col}) <> $v{i}")
            else:             # = 或 !=，值是字串：不分大小寫
                where.append(f"toLower(toString({col})) = toLower($v{i})" if op == "=" else
                             f"toLower(toString({col})) <> toLower($v{i})")
            used.append(f)
        order = ""
        if order_by is not None:
            if (err := check_field(order_by)):
                return {"error": err}
            where.append(f"toFloatOrNull(n.`{order_by}`) IS NOT NULL")
            order = f"ORDER BY toFloatOrNull(n.`{order_by}`) {'DESC' if descending else 'ASC'}, n.name"
            used.append(order_by)
        show = list(dict.fromkeys(used + list(fields or [])))
        for f in show:
            if (err := check_field(f)):
                return {"error": err}
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            return {"error": "limit 必須是 1～200 的整數"}
        cond = " AND ".join(where) or "true"
        base = f"MATCH (n:{label}) WHERE {cond}"
        total = self._run(f"{base} RETURN count(n) AS c", **params)[0]["c"]
        ret = ", ".join(f"n.`{f}` AS `f_{i}`" for i, f in enumerate(show))
        rows = self._run(f"{base} RETURN n.uid AS uid{', ' + ret if ret else ''} {order or 'ORDER BY n.name'} LIMIT {limit}", **params)
        items = [dict(self._summary(r["uid"]), values=_plain({f: r[f"f_{i}"] for i, f in enumerate(show)})) for r in rows]
        return {"label": label, "total": total, "truncated": total > limit, "results": items}


def main(argv):
    if len(argv) < 2 or argv[1] not in ("get_entity", "get_neighbors", "find_path", "filter_by_attribute", "link_entities"):
        print(__doc__)
        return 1
    args = json.loads(argv[2]) if len(argv) > 2 else {}
    with GraphTools() as t:
        print(json.dumps(getattr(t, argv[1])(**args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
