#!/usr/bin/env bash
# 啟動 S5 需要的兩個 llama-server：embedding（port 8801）與生成（port 8802，Qwen3.5-4B，--jinja 才有工具呼叫）。
#
#   bash scripts/start_llama_servers.sh start    # 啟動並等到兩個都就緒
#   bash scripts/start_llama_servers.sh status
#   bash scripts/start_llama_servers.sh stop
#
# 路徑用環境變數覆蓋（預設是作者機器上的位置）：
#   LLAMA_SERVER  llama-server 執行檔   預設 $HOME/program/llama.cpp/build/bin/llama-server
#   MODELS_DIR    放 .gguf 的目錄       預設 $HOME/program/models（bge-large-en-v1.5-f16.gguf、Qwen3.5-4B-Q8_0.gguf）
#   GEN_CTX       生成端 context 長度   預設 8192（工具結果會佔 context，S2 的 4096 不夠）
# 兩個 server 合計約 5.5GB VRAM（RTX 3070 Laptop 8GB）。log 與 pid 放在 ${TMPDIR:-/tmp}/tarnished-rag-llama/。
set -euo pipefail

LLAMA_SERVER="${LLAMA_SERVER:-$HOME/program/llama.cpp/build/bin/llama-server}"
MODELS_DIR="${MODELS_DIR:-$HOME/program/models}"
GEN_CTX="${GEN_CTX:-8192}"
RUN_DIR="${TMPDIR:-/tmp}/tarnished-rag-llama"
mkdir -p "$RUN_DIR"

running() { [ -f "$RUN_DIR/$1.pid" ] && kill -0 "$(cat "$RUN_DIR/$1.pid")" 2>/dev/null; }

start_one() {   # start_one <名稱> <port> <llama-server 參數...>
    local name=$1 port=$2; shift 2
    if running "$name"; then echo "$name 已經在跑（pid $(cat "$RUN_DIR/$name.pid")）"; return; fi
    setsid nohup "$LLAMA_SERVER" "$@" --host 127.0.0.1 --port "$port" > "$RUN_DIR/$name.log" 2>&1 &
    echo $! > "$RUN_DIR/$name.pid"
    echo "啟動 $name（port $port，pid $!），log：$RUN_DIR/$name.log"
}

wait_ready() {  # wait_ready <名稱> <port>
    local name=$1 port=$2
    for _ in $(seq 1 120); do
        if curl -sf "http://127.0.0.1:$port/health" > /dev/null; then echo "$name 就緒（port $port）"; return 0; fi
        running "$name" || { echo "$name 已經結束了，看 $RUN_DIR/$name.log"; return 1; }
        sleep 1
    done
    echo "$name 120 秒內沒有就緒，看 $RUN_DIR/$name.log"; return 1
}

case "${1:-}" in
    start)
        [ -x "$LLAMA_SERVER" ] || { echo "找不到 llama-server：$LLAMA_SERVER（用 LLAMA_SERVER=... 指定）"; exit 1; }
        for m in bge-large-en-v1.5-f16.gguf Qwen3.5-4B-Q8_0.gguf; do
            [ -f "$MODELS_DIR/$m" ] || { echo "找不到模型：$MODELS_DIR/$m（用 MODELS_DIR=... 指定）"; exit 1; }
        done
        start_one embedding 8801 -m "$MODELS_DIR/bge-large-en-v1.5-f16.gguf" --embedding --pooling cls -c 2048 -np 4 -b 2048 -ub 2048 -ngl 99
        start_one generation 8802 -m "$MODELS_DIR/Qwen3.5-4B-Q8_0.gguf" -c "$GEN_CTX" -np 1 -ngl 99 --jinja
        wait_ready embedding 8801
        wait_ready generation 8802
        ;;
    stop)
        for name in embedding generation; do
            if running "$name"; then kill "$(cat "$RUN_DIR/$name.pid")" && echo "已停止 $name"; else echo "$name 沒在跑"; fi
            rm -f "$RUN_DIR/$name.pid"
        done
        ;;
    status)
        for spec in embedding:8801 generation:8802; do
            name=${spec%%:*}; port=${spec##*:}
            if curl -sf "http://127.0.0.1:$port/health" > /dev/null; then echo "$name：就緒（port $port）"; else echo "$name：沒有回應（port $port）"; fi
        done
        ;;
    *) echo "用法：bash scripts/start_llama_servers.sh start|stop|status"; exit 1 ;;
esac
