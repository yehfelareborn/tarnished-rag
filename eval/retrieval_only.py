"""只跑檢索、不接生成端：對 questions.jsonl 每一題做向量檢索，
把 top-K 結果存成 predictions 格式，並印出各題型的 recall@k。

用來單獨檢查「向量檢索本身找不找得到正確來源」，之後生成端的結果
分不清是檢索問題還是模型問題時，可以回頭對照這份。

需要先啟動 embedding server（見 src/vector/embed_client.py）。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src" / "vector"))
sys.path.insert(0, str(HERE))

from run_eval import load_jsonl, recall_at_k, write_jsonl  # noqa: E402
from search import vector_search  # noqa: E402

TOP_K = 10
KS = (1, 3, 5, 10)


def main():
    questions = load_jsonl(HERE / "questions.jsonl")
    preds = []
    for q in questions:
        hits = vector_search(q["question"], k=TOP_K)
        preds.append({
            "id": q["id"],
            "predicted_answer": "",
            "retrieved_sources": [
                {"file": s["file"], "row_id": s["row_id"]}
                for h in hits for s in h["source"]
            ],
            "retrieved_entities": [h["entity"] for h in hits],
            "refused": False,
        })

    out = HERE / "results" / "retrieval_only_predictions.jsonl"
    write_jsonl(out, preds)

    by_type = defaultdict(lambda: {k: [] for k in KS})
    for q, p in zip(questions, preds):
        for k in KS:
            r = recall_at_k(q.get("source", []), p["retrieved_sources"], k)
            if r is not None:
                by_type[q["type"]][k].append(r)

    print(f"{'題型':<14}{'n':>4}" + "".join(f"{'R@'+str(k):>8}" for k in KS))
    for t in sorted(by_type):
        n = len(by_type[t][KS[0]])
        print(f"{t:<14}{n:>4}" + "".join(f"{sum(by_type[t][k])/n:>8.3f}" for k in KS))
    print(f"\n寫到 {out}")


if __name__ == "__main__":
    main()
