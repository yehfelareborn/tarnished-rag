"""產生「草稿版」評分表，減少人工判定的工作量。

這不是自動評分：計畫規定答案對錯是人工判定。這裡只做初篩——
拿標準答案的關鍵字跟系統答案比對，把把握高的先填好，其餘標成 needs_review，
人工只需要看 needs_review=true 的題目，並可推翻任何一題的草稿判定。

規則
- single_fact / numeric / relational / multi_hop / comparison：
  標準答案的內容字有多少比例出現在系統答案裡（數字的千分位逗號會先去掉）。
  >= 0.9 → correct（不需複查）；0.5～0.9 → partial（需複查）；< 0.5 → wrong（需複查，
  避免措辭不同造成誤判）。
- false_premise / unanswerable：一律需要人工判定，只附上是否偵測到拒答/否定用語當參考。

用法
    python draft_judgment.py --predictions results/vector_baseline_predictions.jsonl \
                             --out results/vector_baseline_grading.jsonl
"""
import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "is", "are", "was", "were",
    "it", "its", "by", "for", "with", "from", "as", "that", "this", "which", "be", "has", "have",
    "other", "option", "than", "both", "does", "do", "not", "no",
}

REFUSAL_HINTS = re.compile(
    r"(don't know|do not know|do not contain|does not contain|do not state|does not state|"
    r"not mention|no information|cannot be determined|not provided|not specified|"
    r"do not (?:provide|include|say|list)|does not (?:provide|include|say|list)|"
    r"contradict|not (?:a|an) (?:boss|dlc)|actually|instead)",
    re.I,
)


ABBREV = {
    "str": "strength", "dex": "dexterity", "int": "intelligence", "fai": "faith", "arc": "arcane",
    "vig": "vigor", "end": "endurance", "mnd": "mind",
}


def tokens(text):
    """小數與數字整個當一個 token（8.5 不會被切開、單位數字也保留），字母縮寫展開成全名。"""
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    out = set()
    for t in re.findall(r"\d+(?:\.\d+)?|[a-z]+", text):
        t = ABBREV.get(t, t)
        if t in STOPWORDS:
            continue
        if t[0].isdigit() or len(t) > 1:
            out.add(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    questions = [json.loads(l) for l in open(HERE / "questions.jsonl", encoding="utf-8") if l.strip()]
    preds = {}
    for l in open(args.predictions, encoding="utf-8"):
        if l.strip():
            p = json.loads(l)
            preds[p["id"]] = p

    sheet = []
    for q in questions:
        p = preds.get(q["id"], {})
        pred_text = p.get("predicted_answer", "")
        row = {
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "gold_answer": q["answer"],
            "predicted_answer": pred_text,
            "judgment": "",
            "needs_review": True,
            "draft_note": "",
        }
        if q["type"] in ("false_premise", "unanswerable"):
            hint = bool(REFUSAL_HINTS.search(pred_text))
            row["draft_note"] = f"偵測到拒答/否定用語: {hint}"
        else:
            gold = tokens(q["answer"])
            ratio = len(gold & tokens(pred_text)) / len(gold) if gold else 0.0
            row["draft_note"] = f"關鍵字命中率 {ratio:.2f}"
            if ratio >= 0.9:
                row["judgment"], row["needs_review"] = "correct", False
            elif ratio >= 0.5:
                row["judgment"] = "partial"
            else:
                row["judgment"] = "wrong"
        sheet.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in sheet:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_review = sum(r["needs_review"] for r in sheet)
    print(f"共 {len(sheet)} 題，草稿已判定且不需複查 {len(sheet) - n_review} 題，需人工複查 {n_review} 題")
    print(f"寫到 {args.out}")


if __name__ == "__main__":
    main()
