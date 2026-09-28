"""S1: 評估腳本，讀 questions.jsonl，跑系統並輸出各題型分數到 results/。

計畫規定「答案正確與否」是人工判定，腳本自己不做 NLP 自動評分，所以分兩階段：

1. init   讀 questions.jsonl + 系統產出的 predictions.jsonl，
          產生一份待人工填寫的評分表（grading sheet）。
2. score  讀填好判定的評分表 + predictions.jsonl，
          算出每個題型的分數（答案正確率、檢索 recall@k、無法回答題拒答率），
          輸出到 results/。

各檔案格式
----------
questions.jsonl（已存在）：
    {"id", "type", "question", "answer", "source": [{"file", "row_id", "entity"}, ...]}

predictions.jsonl（由要被評估的系統產生，此檔不含在 repo 裡，跑評估時自備）：
    {"id": "q01",
     "predicted_answer": "...",
     "retrieved_sources": [{"file": "...", "row_id": "..."}, ...],   # 依檢索排名由高到低
     "refused": false}                                               # 系統是否主動拒答

grading_sheet.jsonl（init 產生、人工編輯後給 score 讀）：
    {"id", "type", "question", "gold_answer", "predicted_answer",
     "judgment": ""}   # 人工填入 "correct" / "partial" / "wrong"

用法
----
    python run_eval.py init  --predictions predictions.jsonl --out grading_sheet.jsonl
    # 人工把 grading_sheet.jsonl 裡每題的 "judgment" 填成 correct/partial/wrong
    python run_eval.py score --predictions predictions.jsonl --grading grading_sheet.jsonl \
                              --out results/scores.json [--k 5]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions.jsonl"

JUDGMENT_SCORE = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_init(args):
    questions = {q["id"]: q for q in load_jsonl(QUESTIONS_PATH)}
    predictions = {p["id"]: p for p in load_jsonl(args.predictions)}

    missing = set(questions) - set(predictions)
    if missing:
        print(f"警告：predictions 裡缺 {len(missing)} 題（例如 {sorted(missing)[:5]}），"
              f"評分表裡這些題的 predicted_answer 會是空字串")

    sheet = []
    for qid, q in questions.items():
        p = predictions.get(qid, {})
        sheet.append({
            "id": qid,
            "type": q["type"],
            "question": q["question"],
            "gold_answer": q["answer"],
            "predicted_answer": p.get("predicted_answer", ""),
            "judgment": "",
        })

    write_jsonl(args.out, sheet)
    print(f"寫了 {len(sheet)} 題到 {args.out}，把每題的 judgment 填成 correct/partial/wrong 後再跑 score")


def source_key(s):
    # data/raw/ 與 data/processed/ 是同一份資料的兩個版本（row_id 不變），比對時不區分
    f = s.get("file", "").replace("data/processed/", "data/").replace("data/raw/", "data/")
    return (f, str(s.get("row_id", "")))


def recall_at_k(gold_sources, retrieved_sources, k):
    if not gold_sources:
        return None  # 無法回答題沒有標準來源，不算進 recall
    gold_keys = {source_key(s) for s in gold_sources}
    retrieved_keys = {source_key(s) for s in retrieved_sources[:k]}
    hit = len(gold_keys & retrieved_keys)
    return hit / len(gold_keys)


def cmd_score(args):
    questions = {q["id"]: q for q in load_jsonl(QUESTIONS_PATH)}
    predictions = {p["id"]: p for p in load_jsonl(args.predictions)}
    grading = {g["id"]: g for g in load_jsonl(args.grading)}

    unjudged = [qid for qid, g in grading.items() if g.get("judgment") not in JUDGMENT_SCORE]
    if unjudged:
        print(f"警告：{len(unjudged)} 題還沒人工判定（judgment 是空的或不合法），"
              f"例如 {unjudged[:5]}，這些題不計入答案正確率")

    per_type = defaultdict(lambda: {
        "n": 0,
        "judged_n": 0,
        "answer_score_sum": 0.0,
        "recall_sum": 0.0,
        "recall_n": 0,
        "unanswerable_n": 0,
        "unanswerable_correct_refusal": 0,
    })

    for qid, q in questions.items():
        qtype = q["type"]
        stats = per_type[qtype]
        stats["n"] += 1

        g = grading.get(qid)
        judgment = g.get("judgment") if g else None
        if judgment in JUDGMENT_SCORE:
            stats["judged_n"] += 1
            stats["answer_score_sum"] += JUDGMENT_SCORE[judgment]

        p = predictions.get(qid, {})
        r = recall_at_k(q.get("source", []), p.get("retrieved_sources", []), args.k)
        if r is not None:
            stats["recall_sum"] += r
            stats["recall_n"] += 1

        if qtype == "unanswerable":
            stats["unanswerable_n"] += 1
            # 模型常換句話說拒答，固定句子偵測不可靠，改看人工判定（correct = 有正確拒答）
            if judgment == "correct":
                stats["unanswerable_correct_refusal"] += 1

    results = {}
    for qtype, s in sorted(per_type.items()):
        results[qtype] = {
            "n_questions": s["n"],
            "n_judged": s["judged_n"],
            "answer_accuracy": (s["answer_score_sum"] / s["judged_n"]) if s["judged_n"] else None,
            f"retrieval_recall_at_{args.k}": (s["recall_sum"] / s["recall_n"]) if s["recall_n"] else None,
            "unanswerable_refusal_rate": (
                s["unanswerable_correct_refusal"] / s["unanswerable_n"]
                if s["unanswerable_n"] else None
            ),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n寫到 {args.out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="產生待人工填寫的評分表")
    p_init.add_argument("--predictions", required=True, type=Path)
    p_init.add_argument("--out", required=True, type=Path)
    p_init.set_defaults(func=cmd_init)

    p_score = sub.add_parser("score", help="讀填好的評分表，輸出各題型分數")
    p_score.add_argument("--predictions", required=True, type=Path)
    p_score.add_argument("--grading", required=True, type=Path)
    p_score.add_argument("--out", required=True, type=Path)
    p_score.add_argument("--k", type=int, default=5, help="retrieval recall@k 的 k 值，預設 5")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
