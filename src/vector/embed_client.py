"""透過 llama.cpp server 的 embedding endpoint 把文字轉成向量。

先跑：
    llama-server -m <bge-large-en-v1.5.gguf> --embedding --pooling cls \
        -c 2048 -np 4 -b 2048 -ub 2048 -ngl 99 --host 127.0.0.1 --port 8801

BGE 系列用 CLS pooling（不是 mean）。每個 slot 的上限是 512 token，
超過的文件會被 server 拒絕（HTTP 400），這裡改成逐步截短到放得進去，
並回報被截斷的篇數。
"""
import requests

DEFAULT_URL = "http://127.0.0.1:8801/v1/embeddings"

# BGE v1.5 官方建議：檢索時，查詢（短）前面加這段指令，文件端不加
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _post(texts, url, timeout):
    resp = requests.post(url, json={"input": texts}, timeout=timeout)
    return resp


def _embed_one_with_truncation(text, url, timeout):
    """單篇嵌入；超過 token 上限就每次砍掉 15% 的字再試。回傳 (向量, 是否被截斷)。"""
    words = text.split()
    truncated = False
    while True:
        resp = _post([" ".join(words)], url, timeout)
        if resp.status_code == 200:
            return resp.json()["data"][0]["embedding"], truncated
        if resp.status_code != 400 or len(words) <= 8:
            resp.raise_for_status()
        words = words[: max(8, int(len(words) * 0.85))]
        truncated = True


def embed_texts(texts, url=DEFAULT_URL, batch_size=32, timeout=120, return_stats=False):
    """回傳跟 texts 等長的向量 list（每個是 list[float]）。

    return_stats=True 時回傳 (vectors, n_truncated)。
    """
    vectors = []
    n_truncated = 0
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = _post(batch, url, timeout)
        if resp.status_code == 200:
            data = resp.json()["data"]
            # /v1/embeddings 的回傳不保證跟輸入順序一致，用 index 排回去
            data.sort(key=lambda d: d["index"])
            vectors.extend(d["embedding"] for d in data)
        elif resp.status_code == 400:
            for t in batch:
                vec, was_truncated = _embed_one_with_truncation(t, url, timeout)
                vectors.append(vec)
                n_truncated += int(was_truncated)
        else:
            resp.raise_for_status()
    return (vectors, n_truncated) if return_stats else vectors
