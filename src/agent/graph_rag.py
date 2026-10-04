"""S5：讓 LLM 自己挑工具（向量搜尋／圖查詢）回答問題，並記錄每題實際呼叫了哪些工具。

生成端與 S2 相同：llama-server 跑的 Qwen3.5-4B（OpenAI 相容 API，需要 --jinja 才有工具呼叫）：
    llama-server -m Qwen3.5-4B-Q8_0.gguf -c 8192 -ngl 99 --jinja --port 8802
需要 Neo4j（圖工具）與 embedding server（向量搜尋，port 8801）在跑。

兩種模式共用同一個迴圈，S6 的 B、C 兩組因此用同一個 generator：
    mode="all"    向量搜尋 ＋ 四個圖工具（C 組）
    mode="graph"  只有四個圖工具（B 組）
A 組（純向量）仍是 vector_rag.py。

實體連結不當成工具：agent 先對問題跑 GraphTools.link_entities，把偵測到的實體名稱與標籤當提示放進使用者訊息
（確定性的步驟，不需要模型判斷，也少一個工具給 4B 模型選）。--no-hint 可以關掉做對照。

給 LLM 的工具結果會先壓縮（截斷長文字、合併同一對節點之間的平行邊、限制筆數），來源（檔案＋列號）另外記在紀錄裡，不佔 context。
"""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "graph"))
sys.path.insert(0, str(ROOT / "src" / "vector"))

GEN_URL = "http://127.0.0.1:8802/v1/chat/completions"
REFUSAL_PHRASE = "I don't know based on the provided data."     # 與 vector_rag.py 相同，unanswerable 題靠它判斷拒答
MAX_TOOL_CHARS = 6000        # 單次工具結果給 LLM 的字元上限
MAX_NEIGHBORS = 40
LABELS = ["Weapon", "Shield", "Armor", "Talisman", "Spell", "AshOfWar", "Skill", "SpiritAsh", "Item",
          "Boss", "Creature", "NPC", "Location", "Region"]
RELATIONS = ["LOCATED_AT", "DROPS", "LOCATED_IN", "EXCHANGES_FOR", "HAS_SKILL", "GRANTS"]


# ---------------------------------------------------------------- 給 LLM 的工具定義

def _fn(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOL_SPECS = {
    "vector_search": _fn(
        "vector_search",
        "Free-text semantic search over short descriptions of game entities. Use it when you do not know the exact entity "
        "name, or when the question is about descriptive text (what something does, lore). Returns the top passages.",
        {"query": {"type": "string", "description": "What to search for, in English."},
         "k": {"type": "integer", "description": "Number of passages (default 5, max 8)."}},
        ["query"]),
    "get_entity": _fn(
        "get_entity",
        "Get all properties of one entity by name (HP, weight, stat requirements, description, ...). If the name matches "
        "several entities (for example a Boss and an NPC) all are returned; use 'label' to pick one.",
        {"name": {"type": "string", "description": "Entity name, e.g. 'Rykard, Lord of Blasphemy' or a short form like 'Rykard'."},
         "label": {"type": "string", "enum": LABELS, "description": "Only entities with this label."},
         "fields": {"type": "array", "items": {"type": "string"},
                    "description": "Only return these specific property names, e.g. ['hp', 'weight']. Omit this to get "
                                    "everything. Do not pass 'properties' here - that is just the wrapper key the result "
                                    "comes back under, not a property name."}},
        ["name"]),
    "get_neighbors": _fn(
        "get_neighbors",
        "List what is connected to an entity. Bosses at a location: name=<location>, relation=LOCATED_AT, direction=in, "
        "target_label=Boss. What a boss drops: name=<boss>, relation=DROPS, direction=out. What a remembrance can be "
        "exchanged for: name=<remembrance>, relation=EXCHANGES_FOR, direction=out. direction=out means edges that start "
        "at the entity, direction=in means edges that point to it.",
        {"name": {"type": "string"},
         "relation": {"type": "string", "enum": RELATIONS},
         "direction": {"type": "string", "enum": ["in", "out", "both"]},
         "target_label": {"type": "string", "enum": LABELS, "description": "Only neighbors with this label."},
         "label": {"type": "string", "enum": LABELS, "description": "Pick the starting entity when the name is ambiguous."}},
        ["name"]),
    "find_path": _fn(
        "find_path",
        "Shortest chain of relations between two entities, e.g. boss -> remembrance -> weapon.",
        {"a": {"type": "string"}, "b": {"type": "string"},
         "max_hops": {"type": "integer", "description": "1 to 6, default 4."}},
        ["a", "b"]),
    "filter_by_attribute": _fn(
        "filter_by_attribute",
        "Find entities of one label by property values, optionally sorted, e.g. weapons with str <= 12, or the boss with "
        "the highest hp. Operators: =, !=, contains (text), <, <=, >, >= (numbers).",
        {"label": {"type": "string", "enum": LABELS},
         "conditions": {"type": "array", "items": {"type": "object", "properties": {
             "field": {"type": "string"}, "op": {"type": "string", "enum": ["=", "!=", "contains", "<", "<=", ">", ">="]},
             "value": {"description": "A number for < <= > >=, text otherwise."}}, "required": ["field", "op", "value"]}},
         "order_by": {"type": "string", "description": "Numeric property to sort by."},
         "descending": {"type": "boolean"},
         "limit": {"type": "integer", "description": "Default 20."},
         "fields": {"type": "array", "items": {"type": "string"}, "description": "Extra properties to show."}},
        ["label", "conditions"]),
}
GRAPH_TOOLS = ["get_entity", "get_neighbors", "find_path", "filter_by_attribute"]

SYSTEM_PROMPT_TEMPLATE = """You answer questions about the game Elden Ring. You cannot answer from memory: use the tools, which query a knowledge base of game data.

How to use the tools:
{tool_guide}- A name can match several entities (for example a Boss and an NPC with the same name). Look at the 'label' field and use the entity the question is about.
- You may call several tools, one after another, until you have what you need. Then answer.

Rules:
1. Use only what the tools return. Do not use outside knowledge.
2. Name the entities your answer is based on. Quote numbers exactly as returned.
3. For "which / what ..." questions that ask for a list, give every item found, not only the first.
4. If the tools do not contain the information needed, reply with exactly: {refusal}
5. Before your final answer, explicitly check every specific claim in the question (a name, a place, a category, a relationship) against what the tools actually returned. If any claim is contradicted by the data, say so plainly instead of answering as if it were true.
6. Be concise: one or two sentences."""

GRAPH_GUIDE = """- Graph tools give exact facts.
  * get_neighbors lists what is connected to an entity (bosses at a location, what a boss drops, what a remembrance can be exchanged for).
  * get_entity returns all properties of one entity (HP, weight, requirements, descriptions).
  * filter_by_attribute finds entities by property values, optionally sorted (highest HP, lightest weapon).
  * find_path shows how two entities are connected.
  * Some items merge several states of the same item; the other states are in 'merged_variants'.
  * The same character sometimes exists under two different names: a longer descriptive name as an NPC, and a shorter
    base name (no title) as a Boss, or vice versa. Before concluding a character cannot be fought as a boss (or does
    not exist), also try get_entity with just the short/base form of the name.
"""
VECTOR_GUIDE = """- vector_search is a free-text search over descriptions. Use it when you do not know the exact entity name or the question is about descriptive text.
"""


def build_system_prompt(mode):
    guide = (GRAPH_GUIDE if mode in ("all", "graph") else "") + (VECTOR_GUIDE if mode in ("all", "vector") else "")
    return SYSTEM_PROMPT_TEMPLATE.format(tool_guide=guide, refusal=REFUSAL_PHRASE)


# ---------------------------------------------------------------- 工具結果壓縮（給 LLM 的版本）

def _cut(v, n=240):
    return v[:n] + "…" if isinstance(v, str) and len(v) > n else v


DROP_PROPS = {"merged_from", "item_types", "row_id", "source_file"}


def compact_entity(res):
    if "error" in res:
        return res
    matches = []
    for m in res["matches"]:
        e = {"uid": m["uid"], "label": m["label"], "name": m["name"], "dlc": m["dlc"]}
        if m.get("stub"):
            e["stub"] = True
        e["properties"] = {k: _cut(v, 400 if k == "merged_variants" else 240) for k, v in m["properties"].items() if k not in DROP_PROPS}
        if m.get("boss_stats"):
            e["boss_stats"] = m["boss_stats"]
        matches.append(e)
    out = {"matches": matches}
    if res.get("note"):
        out["note"] = res["note"]
    return out


def compact_neighbors(res, cap=MAX_NEIGHBORS):
    """同一對節點之間的平行邊（來自不同檔案）合成一筆；at_location 合併成清單。"""
    if "error" in res:
        return res
    results = []
    for r in res["results"]:
        grouped = {}
        for n in r["neighbors"]:
            ent, e = n["entity"], n["edge"]
            g = grouped.setdefault((n["relation"], n["direction"], ent["uid"]), {
                "relation": n["relation"], "direction": n["direction"], "name": ent["name"], "label": ent["label"], "uid": ent["uid"]})
            if ent.get("stub"):
                g["stub"] = True
            loc = e.get("at_location")
            if loc:
                g.setdefault("at_location", [])
                if loc not in g["at_location"]:
                    g["at_location"].append(loc)
            for k in ("runes", "option"):
                if e.get(k) is not None:
                    g[k] = e[k]
            if str(e.get("note", "")).startswith("via set"):
                g["note"] = e["note"]
        items = list(grouped.values())
        results.append({"entity": {"label": r["entity"]["label"], "name": r["entity"]["name"], "uid": r["entity"]["uid"]},
                        "total": len(items), "shown": min(len(items), cap), "neighbors": items[:cap]})
    out = {"results": results}
    if res.get("note"):
        out["note"] = res["note"]
    return out


def compact_path(res):
    if "error" in res:
        return res
    paths = []
    for p in res.get("paths", []):
        nodes = p["nodes"]
        chain = nodes[0]["name"]
        for i, e in enumerate(p["edges"]):
            arrow = f"-{e['relation']}->" if e["from"] == nodes[i]["uid"] else f"<-{e['relation']}-"
            chain += f" {arrow} {nodes[i + 1]['name']}"
        paths.append({"length": p["length"], "chain": chain})
    out = {"paths": paths}
    if res.get("note"):
        out["note"] = res["note"]
    return out


def compact_filter(res):
    if "error" in res:
        return res
    return {"label": res["label"], "total": res["total"], "truncated": res["truncated"],
            "results": [{"name": x["name"], "uid": x["uid"], **({"values": x["values"]} if x.get("values") else {})}
                        for x in res["results"]]}


def _to_text(obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= MAX_TOOL_CHARS else s[:MAX_TOOL_CHARS] + "…(truncated)"


# ---------------------------------------------------------------- 工具實作（真的去查圖／向量索引）

def _uids_in(res):
    """工具結果裡出現的所有實體 uid（給 GraphTools.source_of 用）。"""
    uids = []
    for m in res.get("matches", []):
        uids.append(m["uid"])
    for r in res.get("results", []):
        if isinstance(r, dict) and "entity" in r and "neighbors" in r:
            uids.append(r["entity"]["uid"])
            uids += [n["entity"]["uid"] for n in r["neighbors"]]
        elif isinstance(r, dict) and "uid" in r:
            uids.append(r["uid"])
    for p in res.get("paths", []):
        uids += [n["uid"] for n in p["nodes"]]
    return uids


def _coerce_numeric_values(args):
    """小模型常把數字當字串傳（"12"）。數值運算子（< <= > >=）的值若是數字字串就轉成數字；
    GraphTools 本身仍然嚴格檢查型別，這只是在 agent 這一層做寬容。"""
    conds = args.get("conditions")
    if not isinstance(conds, list):
        return args
    fixed = []
    for c in conds:
        if isinstance(c, dict) and c.get("op") in ("<", "<=", ">", ">=") and isinstance(c.get("value"), str):
            try:
                c = {**c, "value": float(c["value"].replace(",", ""))}
            except ValueError:
                pass
        fixed.append(c)
    return {**args, "conditions": fixed}


def build_registry(mode, graph_tools=None, k_default=5):
    """{工具名: {"spec", "run"}}；run(**args) 回傳 (給 LLM 的文字, 來源清單, 實體名稱清單)。"""
    registry = {}
    if mode in ("all", "graph"):
        gt = graph_tools
        if gt is None:
            from tools import GraphTools
            gt = GraphTools()

        def graph_call(method, compact):
            def run(**args):
                if method == "filter_by_attribute":
                    args = _coerce_numeric_values(args)
                res = getattr(gt, method)(**args)
                srcs = [s for s in (gt.source_of(u) for u in dict.fromkeys(_uids_in(res))) if s]
                names = [gt.by_uid[u]["name"] for u in dict.fromkeys(_uids_in(res)) if u in gt.by_uid]
                return _to_text(compact(res)), srcs, names
            return run

        registry["get_entity"] = {"spec": TOOL_SPECS["get_entity"], "run": graph_call("get_entity", compact_entity)}
        registry["get_neighbors"] = {"spec": TOOL_SPECS["get_neighbors"], "run": graph_call("get_neighbors", compact_neighbors)}
        registry["find_path"] = {"spec": TOOL_SPECS["find_path"], "run": graph_call("find_path", compact_path)}
        registry["filter_by_attribute"] = {"spec": TOOL_SPECS["filter_by_attribute"], "run": graph_call("filter_by_attribute", compact_filter)}
    if mode in ("all", "vector"):
        def run_vector(query, k=k_default):
            from search import vector_search
            hits = vector_search(query, k=max(1, min(int(k), 8)))
            payload = [{"entity": h["entity"], "type": h["type"], "text": _cut(h["text"], 500)} for h in hits]
            srcs = [{"file": s["file"], "row_id": s["row_id"]} for h in hits for s in h["source"]]
            return _to_text({"passages": payload}), srcs, [h["entity"] for h in hits]
        registry["vector_search"] = {"spec": TOOL_SPECS["vector_search"], "run": run_vector}
    return registry


def make_hint(graph_tools, question, max_mentions=6, max_cands=3):
    """問題中偵測到的實體名稱與標籤，當提示放進使用者訊息。回傳 (提示文字, 原始偵測結果)。"""
    mentions = graph_tools.link_entities(question)["mentions"][:max_mentions]
    if not mentions:
        return "", []
    parts = []
    for m in mentions:
        cands = m["candidates"][:max_cands]
        parts.append(f"'{cands[0]['name']}'" + " (" + " or ".join(dict.fromkeys(c["label"] for c in cands)) + ")")
    return "Entities detected in the question: " + "; ".join(parts) + ".", mentions


# ---------------------------------------------------------------- LLM 呼叫

def chat_local(gen_url=GEN_URL, max_tokens=512, timeout=300):
    """回傳 chat(messages, tool_specs) -> (assistant message dict, 統計)。tool_specs=None 表示不給工具。"""
    def chat(messages, tool_specs):
        body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": False}}
        if tool_specs:
            body["tools"] = tool_specs
            body["tool_choice"] = "auto"
        t = time.time()
        resp = requests.post(gen_url, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        timings = data.get("timings", {})
        return data["choices"][0]["message"], {"llm_s": round(time.time() - t, 3),
                                              "prompt_tokens": timings.get("prompt_n"),
                                              "predicted_tokens": timings.get("predicted_n")}
    return chat


CLOUD_MODEL = "claude-haiku-4-5-20251001"


def chat_anthropic(model=CLOUD_MODEL, max_tokens=512):
    """跟 chat_local 同一個介面：chat(messages, tool_specs) -> (assistant message dict, 統計)。
    Agent 本身用 OpenAI 的訊息／tool_calls 格式，這裡轉成 Anthropic 的格式呼叫，回來再轉回去，
    Agent.run() 不用知道差異、不用改。API key 從專案根目錄的 .env（ANTHROPIC_API_KEY）讀。"""
    from dotenv import load_dotenv
    import anthropic
    load_dotenv(ROOT / ".env")
    client = anthropic.Anthropic()

    def to_tools(tool_specs):
        return [{"name": t["function"]["name"], "description": t["function"]["description"],
                 "input_schema": t["function"]["parameters"]} for t in (tool_specs or [])]

    def to_anthropic_messages(messages):
        """OpenAI 格式一輪可能是：assistant(含多個 tool_calls) 接著數個 role=tool 訊息（一個呼叫一則）。
        Anthropic 要求同一輪的 tool_result 合併成一個 user 訊息的多個 block，這裡用 pending 累積、
        遇到下一個非 tool 訊息（或結尾）才整批 flush。"""
        system, out, pending = "", [], []
        def flush():
            if pending:
                out.append({"role": "user", "content": list(pending)})
                pending.clear()
        for m in messages:
            role = m["role"]
            if role == "system":
                system = m["content"]
            elif role == "tool":
                pending.append({"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": m["content"]})
            else:
                flush()
                if role == "user":
                    out.append({"role": "user", "content": m["content"]})
                elif role == "assistant":
                    content = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                    for c in (m.get("tool_calls") or []):
                        raw = c["function"].get("arguments", "{}")
                        try:
                            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                        except (ValueError, TypeError):
                            args = {}
                        content.append({"type": "tool_use", "id": c.get("id", ""), "name": c["function"]["name"], "input": args})
                    out.append({"role": "assistant", "content": content})
        flush()
        return system, out

    def chat(messages, tool_specs):
        system, amsgs = to_anthropic_messages(messages)
        kwargs = {"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system, "messages": amsgs}
        if tool_specs:
            kwargs["tools"] = to_tools(tool_specs)
        t = time.time()
        resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text")
        tool_calls = [{"id": b.id, "function": {"name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}}
                      for b in resp.content if b.type == "tool_use"]
        msg = {"content": text, "tool_calls": tool_calls or None}
        return msg, {"llm_s": round(time.time() - t, 3), "prompt_tokens": resp.usage.input_tokens,
                     "predicted_tokens": resp.usage.output_tokens}
    return chat


# ---------------------------------------------------------------- agent 迴圈

class Agent:
    def __init__(self, chat, registry, system_prompt, max_steps=6):
        self.chat, self.registry, self.system_prompt, self.max_steps = chat, registry, system_prompt, max_steps
        self.tool_specs = [t["spec"] for t in registry.values()]

    def _call_tool(self, call):
        """執行一個工具呼叫。回傳 (給 LLM 的文字, 來源, 實體名稱, 紀錄)。參數不合法或工具出錯時把錯誤文字回給模型。"""
        fn = call.get("function", {})
        name, raw = fn.get("name", ""), fn.get("arguments", "")
        rec = {"tool": name, "args": raw, "error": None}
        t = time.time()
        try:
            args = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw if isinstance(raw, dict) else {})
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
            rec["args"] = args
            if name not in self.registry:
                raise ValueError(f"unknown tool {name!r}; available: {sorted(self.registry)}")
            text, srcs, names = self.registry[name]["run"](**args)
            if text.startswith('{"error":'):       # 圖工具對不合法輸入是「回傳」{"error": ...}，不是拋例外；紀錄裡也要標出來
                rec["error"] = "tool_error: " + text[len('{"error":'):][:200].strip(' "}')
        except Exception as e:      # 錯誤回給模型，讓它有機會修正；紀錄裡留下來
            rec["error"] = f"{type(e).__name__}: {e}"
            text, srcs, names = json.dumps({"error": rec["error"]}, ensure_ascii=False), [], []
        rec["seconds"] = round(time.time() - t, 3)
        rec["result_chars"] = len(text)
        return text, srcs, names, rec

    def run(self, question, hint=""):
        user = question + (f"\n\n{hint}" if hint else "")
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user}]
        trace, sources, entities = [], [], []
        llm_s, forced, answer = 0.0, False, ""
        t0 = time.time()
        for step in range(1, self.max_steps + 1):
            msg, stats = self.chat(messages, self.tool_specs)
            llm_s += stats.get("llm_s", 0)
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                text, srcs, names, rec = self._call_tool(c)
                rec["step"] = step
                trace.append(rec)
                sources += srcs
                entities += names
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": text})
        else:
            forced = True          # 用完步數還在呼叫工具：不給工具，強制它用手上的結果回答
            messages.append({"role": "user", "content": "Stop calling tools. Answer the question now using only the tool results "
                             f"above. If they do not contain the answer, reply with exactly: {REFUSAL_PHRASE}"})
            msg, stats = self.chat(messages, None)
            llm_s += stats.get("llm_s", 0)
            answer = (msg.get("content") or "").strip()
        uniq = list({(s["file"], str(s["row_id"])): s for s in sources}.values())
        return {
            "predicted_answer": answer,
            "retrieved_sources": [{"file": s["file"], "row_id": s["row_id"]} for s in uniq],
            "retrieved_entities": list(dict.fromkeys(entities)),
            "refused": REFUSAL_PHRASE.lower() in answer.lower(),
            "tool_calls": trace,
            "forced_final": forced,
            "latency": {"total_s": round(time.time() - t0, 3), "llm_s": round(llm_s, 3), "tool_calls": len(trace)},
        }
