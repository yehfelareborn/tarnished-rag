"""對 eval/questions.jsonl 跑 S5 agent（LLM 自己挑工具），存成 predictions 檔，之後餵給 eval/run_eval.py。

需要：Neo4j（已建圖）、生成端 llama-server（port 8802，--jinja）、embedding server（port 8801，mode=all 才需要）。
    python3 src/agent/run_agent.py --mode all --sample-per-type 2      # 小規模試跑：每個題型前 2 題
    python3 src/agent/run_agent.py --mode all                          # 全部 106 題（C 組）
    python3 src/agent/run_agent.py --mode graph                        # 只用圖工具（B 組）

只跑一部分題目時，預設輸出到 *_smoke_predictions.jsonl，不會蓋掉完整的預測檔。
預測檔格式沿用 S2（predicted_answer、retrieved_sources、retrieved_entities、refused、latency），
多了 tool_calls（每次呼叫的工具、參數、是否出錯、耗時）、forced_final、linked（問題中偵測到的實體）。
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_rag import GEN_URL, Agent, build_registry, build_system_prompt, chat_local, make_hint  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def select_questions(questions, ids=None, sample_per_type=None, limit=None):
    if ids:
        want = [i.strip() for i in ids.split(",") if i.strip()]
        by_id = {q["id"]: q for q in questions}
        missing = [i for i in want if i not in by_id]
        if missing:
            raise SystemExit(f"題庫裡沒有這些題號：{missing}")
        return [by_id[i] for i in want]
    if sample_per_type:
        seen, out = Counter(), []
        for q in questions:
            if seen[q["type"]] < sample_per_type:
                seen[q["type"]] += 1
                out.append(q)
        return out
    return questions[:limit] if limit else questions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["all", "graph"], default="all", help="all＝向量＋圖（C 組）；graph＝只用圖（B 組）")
    ap.add_argument("--ids", default=None, help="只跑這些題號，逗號分隔，例如 q06,q60")
    ap.add_argument("--sample-per-type", type=int, default=None, help="每個題型取前 N 題（小規模試跑）")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-steps", type=int, default=6, help="最多幾輪工具呼叫，超過就強制回答")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--no-hint", action="store_true", help="不把偵測到的實體名稱放進使用者訊息（對照用）")
    ap.add_argument("--gen-url", default=GEN_URL)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    questions = [json.loads(l) for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") if l.strip()]
    questions = select_questions(questions, args.ids, args.sample_per_type, args.limit)
    partial = bool(args.ids or args.sample_per_type or args.limit)
    if args.out is None:
        args.out = ROOT / "eval" / "results" / f"agent_{args.mode}{'_smoke' if partial else ''}_predictions.jsonl"

    from tools import GraphTools
    gt = GraphTools()
    registry = build_registry(args.mode, gt)
    agent = Agent(chat_local(args.gen_url, args.max_tokens), registry, build_system_prompt(args.mode), args.max_steps)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    first_tool, usage, n_err, n_forced, n_none, n_fail = Counter(), Counter(), 0, 0, 0, 0
    with open(args.out, "w", encoding="utf-8") as f:
        for i, q in enumerate(questions, 1):
            hint, mentions = ("", []) if args.no_hint else make_hint(gt, q["question"])
            try:
                r = agent.run(q["question"], hint)
            except Exception as e:      # 伺服器錯誤、context 超過等：記下來，繼續下一題
                n_fail += 1
                r = {"predicted_answer": "", "retrieved_sources": [], "retrieved_entities": [], "refused": False,
                     "tool_calls": [], "forced_final": False, "latency": {}, "error": f"{type(e).__name__}: {e}"}
            r.update({"id": q["id"], "backend": f"local-agent:{args.mode}",
                      "linked": [m["mention"] for m in mentions]})
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            calls = r["tool_calls"]
            usage.update(c["tool"] for c in calls)
            n_err += sum(1 for c in calls if c["error"])
            n_forced += bool(r["forced_final"])
            n_none += (not calls and "error" not in r)
            first_tool[(q["type"], calls[0]["tool"] if calls else "(no tool)")] += 1
            seq = " → ".join(c["tool"] + ("!" if c["error"] else "") for c in calls) or "(no tool)"
            print(f"[{i}/{len(questions)}] {q['id']} {q['type']:<13} {seq}\n      -> {r['predicted_answer'][:110]!r}"
                  + (f"\n      !! {r['error']}" if "error" in r else ""))

    print(f"\n寫到 {args.out}")
    print(f"題數 {len(questions)}；伺服器錯誤 {n_fail}；沒呼叫任何工具就回答 {n_none}；工具呼叫出錯 {n_err} 次；用完步數被強制回答 {n_forced}")
    print("工具使用次數:", dict(usage))
    print("各題型第一個呼叫的工具:")
    for (typ, tool), n in sorted(first_tool.items()):
        print(f"   {typ:<13} {tool:<20} {n}")
    gt.close()


if __name__ == "__main__":
    main()
