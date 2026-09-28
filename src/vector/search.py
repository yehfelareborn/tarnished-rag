"""載入 build_index.py 產生的 FAISS 索引，提供 vector_search(query, k)。"""
import json
from pathlib import Path

import faiss
import numpy as np

from embed_client import QUERY_INSTRUCTION, embed_texts

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "processed" / "vector_index"

_index = None
_docs = None


def _load():
    global _index, _docs
    if _index is None:
        _index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
        _docs = [json.loads(l) for l in (INDEX_DIR / "docs.jsonl").open(encoding="utf-8")]
    return _index, _docs


def vector_search(query, k=5):
    """回傳 top-k 篇文件，附相似度分數，由高到低排序。"""
    index, docs = _load()
    vec = np.array(embed_texts([QUERY_INSTRUCTION + query]), dtype="float32")
    faiss.normalize_L2(vec)
    scores, idxs = index.search(vec, k)
    results = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx == -1:
            continue
        doc = docs[idx]
        results.append({
            "entity": doc["entity"],
            "type": doc["type"],
            "text": doc["text"],
            "source": doc["source"],
            "score": float(score),
        })
    return results


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What weapon category does Rivers of Blood belong to?"
    for r in vector_search(q, k=5):
        print(f"[{r['score']:.3f}] {r['entity']} ({r['type']}): {r['text'][:100]}")
