"""S2 任務 2：把 data/processed/corpus.jsonl 切塊、embedding，建立 FAISS 向量索引。

每篇文件本身已經是一段完整的實體描述（中位數 58 字、p90 87 字），
不用再額外切塊——一篇文件當一個 chunk。

需要先啟動 llama.cpp 的 embedding server（見 embed_client.py 的說明）。

輸出：
    data/processed/vector_index/index.faiss   FAISS 向量索引
    data/processed/vector_index/docs.jsonl    索引位置 i 對應的文件（含 text/source）
"""
import json
from pathlib import Path

import faiss
import numpy as np

from embed_client import embed_texts

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "data" / "processed" / "corpus.jsonl"
OUT_DIR = ROOT / "data" / "processed" / "vector_index"


def main():
    docs = [json.loads(l) for l in CORPUS_PATH.open(encoding="utf-8")]
    texts = [d["text"] for d in docs]

    print(f"對 {len(texts)} 篇文件做 embedding...")
    vectors, n_truncated = embed_texts(texts, return_stats=True)
    print(f"因超過 512 token 上限被截斷的文件數: {n_truncated}")
    mat = np.array(vectors, dtype="float32")
    faiss.normalize_L2(mat)  # 正規化後用內積索引 = cosine similarity

    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(OUT_DIR / "index.faiss"))
    with (OUT_DIR / "docs.jsonl").open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"索引維度: {mat.shape[1]}, 筆數: {index.ntotal}")
    print(f"寫到 {OUT_DIR}")


if __name__ == "__main__":
    main()
