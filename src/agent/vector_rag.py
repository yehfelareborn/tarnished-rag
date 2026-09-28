"""S2 純向量 RAG：問題 → 向量檢索 top-k → 本地 LLM 生成（附來源）。

生成端是 llama-server 跑的 Qwen3.5-4B（OpenAI 相容 API）：
    llama-server -m Qwen3.5-4B-Q8_0.gguf -c 8192 -ngl 99 --jinja --port 8802

system prompt 放在最前面且固定不變，讓 llama.cpp 的 prompt cache 能重用這段前綴。
"""
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vector"))
from search import vector_search  # noqa: E402

GEN_URL = "http://127.0.0.1:8802/v1/chat/completions"
CLOUD_MODEL = "claude-haiku-4-5-20251001"

REFUSAL_PHRASE = "I don't know based on the provided data."

SYSTEM_PROMPT = f"""You answer questions about the game Elden Ring using ONLY the numbered context passages provided by the user.

Rules:
1. Use only the passages. Do not use outside knowledge.
2. Cite the passages you used as [1], [2], ... right after the claims they support.
3. If the passages do not contain the information needed, reply with exactly: {REFUSAL_PHRASE}
4. If the question assumes something the passages contradict, point out the contradiction instead of answering the false premise.
5. Be concise: one or two sentences."""


def build_context(hits):
    return "\n\n".join(
        f"[{i}] {h['entity']} ({h['type']}): {h['text']}" for i, h in enumerate(hits, 1)
    )


def _generate_local(user_msg, max_tokens, gen_url):
    body = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        # Qwen3 系列的 thinking 模式會先吐一大段思考，RAG 問答不需要
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t1 = time.time()
    resp = requests.post(gen_url, json=body, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    t_generate = time.time() - t1
    timings = data.get("timings", {})
    return data["choices"][0]["message"]["content"].strip(), {
        "generate_s": round(t_generate, 3),
        "prompt_tokens": timings.get("prompt_n"),
        "prompt_ms": timings.get("prompt_ms"),
        "predicted_tokens": timings.get("predicted_n"),
    }


def _generate_anthropic(user_msg, max_tokens, model):
    """雲端 generator。API key 從專案根目錄的 .env（ANTHROPIC_API_KEY）讀，不寫進程式。"""
    from dotenv import load_dotenv
    import anthropic

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    client = anthropic.Anthropic()
    t1 = time.time()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    t_generate = time.time() - t1
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return text, {
        "generate_s": round(t_generate, 3),
        "prompt_tokens": msg.usage.input_tokens,
        "prompt_ms": None,
        "predicted_tokens": msg.usage.output_tokens,
    }


def answer_question(question, k=5, max_tokens=256, gen_url=GEN_URL,
                    backend="local", model=CLOUD_MODEL):
    t0 = time.time()
    hits = vector_search(question, k=k)
    t_retrieve = time.time() - t0

    user_msg = f"Context passages:\n{build_context(hits)}\n\nQuestion: {question}"
    if backend == "local":
        answer, gen_stats = _generate_local(user_msg, max_tokens, gen_url)
    elif backend == "anthropic":
        answer, gen_stats = _generate_anthropic(user_msg, max_tokens, model)
    else:
        raise ValueError(f"unknown backend: {backend}")

    return {
        "predicted_answer": answer,
        "retrieved_sources": [
            {"file": s["file"], "row_id": s["row_id"]} for h in hits for s in h["source"]
        ],
        "retrieved_entities": [h["entity"] for h in hits],
        "refused": REFUSAL_PHRASE.lower() in answer.lower(),
        "backend": backend if backend == "local" else f"{backend}:{model}",
        "latency": {"retrieve_s": round(t_retrieve, 3), **gen_stats},
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What weapon category does Rivers of Blood belong to?"
    r = answer_question(q)
    print("Q:", q)
    print("A:", r["predicted_answer"])
    print("retrieved:", r["retrieved_entities"])
    print("latency:", r["latency"])
