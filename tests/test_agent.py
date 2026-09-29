"""S5 agent 的單元測試。不需要 LLM、Neo4j、向量索引：迴圈用假的 LLM 與假的工具測。

    python3 -m pytest tests/test_agent.py -v
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "agent"))

import graph_rag as g  # noqa: E402


# ---------------------------------------------------------------- 假的 LLM 與工具

def tool_call(name, args, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


class FakeChat:
    """依序回傳預先準備好的 assistant 訊息，並記錄每次收到的 messages 與 tool_specs。"""
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, tool_specs):
        self.calls.append((json.loads(json.dumps(messages)), tool_specs))
        return self.replies.pop(0), {"llm_s": 0.5}


def fake_registry(fail=False):
    def run(**args):
        if fail:
            raise RuntimeError("boom")
        return "RESULT:" + json.dumps(args), [{"file": "f.csv", "row_id": "1"}], ["Entity A"]
    return {"echo": {"spec": {"type": "function", "function": {"name": "echo"}}, "run": run}}


def make_agent(replies, registry=None, max_steps=3):
    chat = FakeChat(replies)
    return g.Agent(chat, registry or fake_registry(), "SYS", max_steps=max_steps), chat


# ---------------------------------------------------------------- 迴圈

def test_tool_call_then_answer():
    agent, chat = make_agent([{"role": "assistant", "content": None, "tool_calls": [tool_call("echo", {"x": 1})]},
                              {"role": "assistant", "content": "The answer is A."}])
    r = agent.run("Q?")
    assert r["predicted_answer"] == "The answer is A."
    assert [c["tool"] for c in r["tool_calls"]] == ["echo"] and r["tool_calls"][0]["args"] == {"x": 1}
    assert r["tool_calls"][0]["error"] is None and r["latency"]["tool_calls"] == 1
    assert r["retrieved_sources"] == [{"file": "f.csv", "row_id": "1"}] and r["retrieved_entities"] == ["Entity A"]
    assert r["forced_final"] is False and r["refused"] is False
    # 第二次呼叫 LLM 時，訊息裡要有 assistant 的工具呼叫與 tool 結果
    roles = [m["role"] for m in chat.calls[1][0]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert chat.calls[1][0][3]["tool_call_id"] == "c1" and chat.calls[1][0][3]["content"].startswith("RESULT:")


def test_no_tool_answer_directly():
    agent, _ = make_agent([{"role": "assistant", "content": "Hello"}])
    r = agent.run("Q?")
    assert r["predicted_answer"] == "Hello" and r["tool_calls"] == []


def test_hint_is_appended_to_user_message():
    agent, chat = make_agent([{"role": "assistant", "content": "ok"}])
    agent.run("Q?", hint="Entities detected in the question: 'X' (Boss).")
    assert chat.calls[0][0][1]["content"] == "Q?\n\nEntities detected in the question: 'X' (Boss)."


def test_invalid_json_arguments_go_back_to_the_model():
    agent, chat = make_agent([{"role": "assistant", "content": "", "tool_calls": [tool_call("echo", "{not json")]},
                              {"role": "assistant", "content": "recovered"}])
    r = agent.run("Q?")
    assert r["tool_calls"][0]["error"] and "JSONDecodeError" in r["tool_calls"][0]["error"]
    assert "error" in chat.calls[1][0][-1]["content"] and r["predicted_answer"] == "recovered"


def test_unknown_tool_and_tool_exception_are_reported_not_raised():
    agent, _ = make_agent([{"role": "assistant", "content": "", "tool_calls": [tool_call("nope", {}, "a"), tool_call("echo", {}, "b")]},
                           {"role": "assistant", "content": "done"}], registry=fake_registry(fail=True))
    r = agent.run("Q?")
    assert "unknown tool" in r["tool_calls"][0]["error"]
    assert "RuntimeError: boom" in r["tool_calls"][1]["error"]
    assert r["predicted_answer"] == "done"


def test_tool_level_error_result_is_flagged_in_the_trace():
    """圖工具對不合法輸入回傳 {"error": ...}（不是拋例外）；紀錄裡要標成出錯，S6 才分得出「工具用錯」。"""
    reg = {"bad": {"spec": {}, "run": lambda **a: (json.dumps({"error": "relation 必須是 [...]"}, ensure_ascii=False), [], [])}}
    agent, _ = make_agent([{"role": "assistant", "content": "", "tool_calls": [tool_call("bad", {})]},
                           {"role": "assistant", "content": "done"}], registry=reg)
    r = agent.run("Q?")
    assert r["tool_calls"][0]["error"].startswith("tool_error: relation")


def test_wrong_argument_names_are_reported():
    agent, _ = make_agent([{"role": "assistant", "content": "", "tool_calls": [tool_call("echo", {"x": 1})]},
                           {"role": "assistant", "content": "done"}],
                          registry={"echo": {"spec": {}, "run": lambda y: ("", [], [])}})     # 沒有 x 參數 → TypeError
    r = agent.run("Q?")
    assert "TypeError" in r["tool_calls"][0]["error"]


def test_step_limit_forces_a_final_answer_without_tools():
    looping = {"role": "assistant", "content": "", "tool_calls": [tool_call("echo", {})]}
    agent, chat = make_agent([looping, looping, {"role": "assistant", "content": "final"}], max_steps=2)
    r = agent.run("Q?")
    assert r["forced_final"] is True and r["predicted_answer"] == "final" and len(r["tool_calls"]) == 2
    assert chat.calls[-1][1] is None                                      # 最後一次不給工具
    assert "Stop calling tools" in chat.calls[-1][0][-1]["content"]


def test_refusal_is_detected():
    agent, _ = make_agent([{"role": "assistant", "content": g.REFUSAL_PHRASE}])
    assert agent.run("Q?")["refused"] is True


def test_sources_are_deduplicated():
    calls = [tool_call("echo", {"i": 1}, "a"), tool_call("echo", {"i": 2}, "b")]
    agent, _ = make_agent([{"role": "assistant", "content": "", "tool_calls": calls}, {"role": "assistant", "content": "x"}])
    r = agent.run("Q?")
    assert r["retrieved_sources"] == [{"file": "f.csv", "row_id": "1"}] and r["retrieved_entities"] == ["Entity A"]


# ---------------------------------------------------------------- system prompt 與工具定義

def test_system_prompt_depends_on_mode():
    assert g.REFUSAL_PHRASE in g.build_system_prompt("all")
    assert "vector_search" in g.build_system_prompt("all") and "get_neighbors" in g.build_system_prompt("all")
    graph_only = g.build_system_prompt("graph")
    assert "get_neighbors" in graph_only and "vector_search" not in graph_only


def test_tool_specs_are_valid_openai_functions():
    for name, spec in g.TOOL_SPECS.items():
        fn = spec["function"]
        assert spec["type"] == "function" and fn["name"] == name and fn["description"]
        params = fn["parameters"]
        assert params["type"] == "object" and set(params["required"]) <= set(params["properties"])
    assert set(g.GRAPH_TOOLS) <= set(g.TOOL_SPECS)


def test_registry_modes(monkeypatch):
    class Stub:
        by_uid, source_of = {}, staticmethod(lambda uid: None)
    assert sorted(g.build_registry("graph", Stub())) == sorted(g.GRAPH_TOOLS)
    assert sorted(g.build_registry("all", Stub())) == sorted(g.GRAPH_TOOLS + ["vector_search"])


# ---------------------------------------------------------------- 結果壓縮

def _nb(relation, direction, uid, name, label="Item", **edge):
    return {"relation": relation, "direction": direction, "entity": {"uid": uid, "label": label, "name": name, "dlc": 0, "stub": False},
            "edge": {"source_file": "x.csv", **edge}}


def test_compact_neighbors_merges_parallel_edges_and_locations():
    res = {"query": "Boss", "results": [{"entity": {"uid": "Boss:1", "label": "Boss", "name": "Boss"}, "match": "exact", "total": 4, "truncated": False,
           "neighbors": [_nb("DROPS", "out", "Item:1", "Remembrance", at_location="A", note="from remembrances.csv"),
                         _nb("DROPS", "out", "Item:1", "Remembrance", at_location="B"),
                         _nb("DROPS", "out", "Item:1", "Remembrance", at_location="A"),
                         _nb("DROPS", "out", "Item:2", "Armor piece", label="Armor", note="via set: X Set")]}]}
    out = g.compact_neighbors(res)["results"][0]
    assert out["total"] == 2 and len(out["neighbors"]) == 2
    rem = out["neighbors"][0]
    assert rem["name"] == "Remembrance" and rem["at_location"] == ["A", "B"] and "note" not in rem      # 平行邊合成一筆、地點合併去重
    assert out["neighbors"][1]["note"] == "via set: X Set"


def test_compact_neighbors_caps_the_list():
    ns = [_nb("LOCATED_AT", "in", f"Item:{i}", f"Item {i}") for i in range(60)]
    res = {"results": [{"entity": {"uid": "L", "label": "Location", "name": "L"}, "neighbors": ns}]}
    out = g.compact_neighbors(res)["results"][0]
    assert out["total"] == 60 and out["shown"] == g.MAX_NEIGHBORS and len(out["neighbors"]) == g.MAX_NEIGHBORS


def test_compact_path_chain_shows_direction():
    res = {"paths": [{"length": 2, "nodes": [{"uid": "B", "name": "Malenia"}, {"uid": "R", "name": "Remembrance"}, {"uid": "W", "name": "Hand"}],
                      "edges": [{"relation": "DROPS", "from": "B", "to": "R"}, {"relation": "EXCHANGES_FOR", "from": "R", "to": "W"}]}]}
    assert g.compact_path(res)["paths"][0]["chain"] == "Malenia -DROPS-> Remembrance -EXCHANGES_FOR-> Hand"
    res["paths"][0]["edges"][1] = {"relation": "EXCHANGES_FOR", "from": "W", "to": "R"}
    assert g.compact_path(res)["paths"][0]["chain"].endswith("Remembrance <-EXCHANGES_FOR- Hand")


def test_compact_entity_drops_internal_props_and_truncates():
    res = {"query": "x", "matches": [{"uid": "Item:1", "label": "Item", "name": "X", "dlc": 0, "stub": False, "match": "exact",
           "properties": {"description": "d" * 1000, "merged_from": ["a"], "item_types": ["b"], "effect": "e"}, "source": {}}]}
    p = g.compact_entity(res)["matches"][0]["properties"]
    assert set(p) == {"description", "effect"} and len(p["description"]) == 241 and p["description"].endswith("…")


def test_errors_pass_through_compaction():
    err = {"error": "nope"}
    for f in (g.compact_entity, g.compact_neighbors, g.compact_path, g.compact_filter):
        assert f(err) == err


def test_coerce_numeric_values_only_touches_numeric_operators():
    args = {"label": "Weapon", "conditions": [{"field": "str", "op": "<=", "value": "12"}, {"field": "name", "op": "=", "value": "12"},
                                              {"field": "weight", "op": ">", "value": "abc"}]}
    c = g._coerce_numeric_values(args)["conditions"]
    assert c[0]["value"] == 12.0 and c[1]["value"] == "12" and c[2]["value"] == "abc"
    assert g._coerce_numeric_values({"label": "Weapon", "conditions": "bad"}) == {"label": "Weapon", "conditions": "bad"}


def test_tool_text_is_capped():
    text = g._to_text({"x": "y" * (g.MAX_TOOL_CHARS * 2)})
    assert len(text) <= g.MAX_TOOL_CHARS + 20 and text.endswith("(truncated)")
