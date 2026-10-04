"""互動式問答：自己在終端機裡輸入問題，重用 S5 的 Agent（跟 run_agent.py 同一套，沒有新邏輯）。

不是服務，只是本機 CLI；要先用 scripts/start_llama_servers.sh start 啟動兩個 llama-server，
Neo4j 也要在跑（mode=vector 不需要 Neo4j）。

    python3 src/agent/ask.py                 # 預設 mode=all（向量＋圖）
    python3 src/agent/ask.py --mode graph    # 只用圖工具
    python3 src/agent/ask.py --mode vector   # 只用向量搜尋

輸入空白行或 exit/quit 結束。
"""
import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_rag import CLOUD_MODEL, GEN_URL, Agent, build_registry, build_system_prompt, chat_anthropic, chat_local, make_hint  # noqa: E402

EMBED_HEALTH_URL = "http://127.0.0.1:8801/health"
GEN_HEALTH_URL = "http://127.0.0.1:8802/health"


def preflight(mode):
    problems = []
    if mode in ("all", "graph"):
        try:
            import socket
            socket.create_connection(("127.0.0.1", 7687), timeout=3).close()
        except OSError:
            problems.append("Neo4j（7687）沒回應，先用 <neo4j 安裝目錄>/bin/neo4j start 啟動")
    if mode in ("all", "vector"):
        try:
            requests.get(EMBED_HEALTH_URL, timeout=3).raise_for_status()
        except Exception:
            problems.append("embedding server（8801）沒回應")
    try:
        requests.get(GEN_HEALTH_URL, timeout=3).raise_for_status()
    except Exception:
        problems.append("generation server（8802）沒回應")
    if problems:
        print("有服務沒就緒：")
        for p in problems:
            print(" -", p)
        print("都需要先用 scripts/start_llama_servers.sh start 啟動（Neo4j 另外啟動）。")
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["all", "graph", "vector"], default="all",
                     help="all＝向量＋圖；graph＝只用圖；vector＝只用向量搜尋")
    ap.add_argument("--no-hint", action="store_true", help="不把偵測到的實體名稱放進使用者訊息")
    ap.add_argument("--max-steps", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--gen-url", default=GEN_URL)
    ap.add_argument("--backend", choices=["local", "anthropic"], default="local",
                     help="local＝本機 Qwen3.5-4B；anthropic＝雲端 Claude Haiku（要花 API 費用）")
    ap.add_argument("--model", default=CLOUD_MODEL, help="backend=anthropic 時用的模型")
    args = ap.parse_args()

    if args.backend == "local":
        preflight(args.mode)
    elif args.mode in ("all", "graph"):
        import socket
        try:
            socket.create_connection(("127.0.0.1", 7687), timeout=3).close()
        except OSError:
            raise SystemExit("Neo4j（7687）沒回應，先用 <neo4j 安裝目錄>/bin/neo4j start 啟動")
        if args.mode == "all":
            try:
                requests.get(EMBED_HEALTH_URL, timeout=3).raise_for_status()
            except Exception:
                raise SystemExit("embedding server（8801）沒回應，先用 scripts/start_llama_servers.sh start 啟動")

    gt = None
    if args.mode in ("all", "graph"):
        from tools import GraphTools
        gt = GraphTools()
    registry = build_registry(args.mode, gt)
    chat = chat_anthropic(args.model, args.max_tokens) if args.backend == "anthropic" else chat_local(args.gen_url, args.max_tokens)
    agent = Agent(chat, registry, build_system_prompt(args.mode), args.max_steps)

    print(f"準備好了（mode={args.mode}）。輸入問題，空白行或 exit 結束。\n")
    try:
        while True:
            try:
                question = input("> ").strip()
            except EOFError:
                break
            if not question or question.lower() in ("exit", "quit"):
                break

            hint = ""
            if gt and not args.no_hint:
                hint, _ = make_hint(gt, question)

            t0 = time.time()
            r = agent.run(question, hint)
            elapsed = time.time() - t0

            print(f"\n{r['predicted_answer']}\n")
            calls = r["tool_calls"]
            seq = " → ".join(c["tool"] + ("!" if c["error"] else "") for c in calls) or "(沒呼叫工具)"
            print(f"[{elapsed:.1f}s｜工具：{seq}]\n")
    finally:
        if gt:
            gt.close()


if __name__ == "__main__":
    main()
