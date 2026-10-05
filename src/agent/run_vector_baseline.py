"""對 eval/questions.jsonl 每一題跑純向量 RAG，存成 predictions 檔，
之後餵給 eval/run_eval.py（init → 人工判定 → score）。

需要先啟動兩個 llama-server：embedding（port 8801）與生成（port 8802）。
"""
import argparse
import json
from pathlib import Path

from vector_rag import CLOUD_MODEL, answer_question

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 題（除錯用）")
    ap.add_argument("--ids", default=None, help="只跑這些題號，逗號分隔，例如 q06,q60（給分批 runner 用）")
    ap.add_argument("--backend", choices=["local", "anthropic"], default="local")
    ap.add_argument("--model", default=CLOUD_MODEL, help="backend=anthropic 時使用的模型")
    ap.add_argument("--out", type=Path, default=None,
                    help="預設：local → vector_baseline_predictions.jsonl；anthropic → vector_baseline_anthropic_predictions.jsonl")
    args = ap.parse_args()
    if args.out is None:
        name = ("vector_baseline_predictions.jsonl" if args.backend == "local"
                else "vector_baseline_anthropic_predictions.jsonl")
        args.out = ROOT / "eval" / "results" / name

    questions = [json.loads(l) for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8") if l.strip()]
    if args.ids:
        by_id = {q["id"]: q for q in questions}
        want = [i.strip() for i in args.ids.split(",") if i.strip()]
        missing = [i for i in want if i not in by_id]
        if missing:
            raise SystemExit(f"題庫裡沒有這些題號：{missing}")
        questions = [by_id[i] for i in want]
    if args.limit:
        questions = questions[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for i, q in enumerate(questions, 1):
            r = answer_question(q["question"], k=args.k, backend=args.backend, model=args.model)
            r["id"] = q["id"]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(questions)}] {q['id']} {q['type']:<13} -> {r['predicted_answer'][:80]!r}")
    print(f"\n寫到 {args.out}")


if __name__ == "__main__":
    main()
