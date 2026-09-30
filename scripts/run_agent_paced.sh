#!/usr/bin/env bash
# 分批跑 S5 agent，避免這台筆電（ASUS，熱管理有 ACPI bug，過熱時似乎會直接硬斷電，見 docs/agent.md）
# 長時間跑滿 106 題導致過熱關機。做法：每批 CHUNK_SIZE 題，批次之間睡到滿 CYCLE_SECONDS，
# 而且在開始下一批前先確認 GPU／CPU 溫度降到安全值以下，沒降就再多等，不會盲目按表操課。
#
#   bash scripts/run_agent_paced.sh graph                      # 預設每批 10 題、每輪目標 300 秒
#   bash scripts/run_agent_paced.sh all 10 300
#   bash scripts/run_agent_paced.sh graph 15 240 --no-hint      # 多餘參數會原樣傳給 run_agent.py
#
# 需要先用 scripts/start_llama_servers.sh start 啟動兩個服務。
# 溫度監控用 nvidia-smi（GPU）與 /sys/class/thermal 的 TCPU／x86_pkg_temp（CPU），任一個不存在就跳過那項監控。
set -euo pipefail

MODE="${1:?用法: run_agent_paced.sh <graph|all> [chunk_size=10] [cycle_seconds=300] [--no-hint 等 run_agent.py 的其他參數...]}"
CHUNK_SIZE="${2:-10}"
CYCLE_SECONDS="${3:-300}"
shift $(( $# >= 3 ? 3 : $# ))   # 剩下的參數原樣傳給 run_agent.py（例如 --no-hint、--max-steps）
EXTRA_ARGS=("$@")

GPU_MAX_C="${GPU_MAX_C:-75}"     # 開始下一批前，GPU 溫度要降到這個以下
CPU_MAX_C="${CPU_MAX_C:-80}"     # CPU 同上
TEMP_WAIT_STEP=20                # 溫度沒降下來時，每次多等幾秒再檢查
TEMP_WAIT_MAX=600                # 最多為了降溫多等幾秒（超過就放棄等待、直接繼續，並警告）

RUN_TAG="$MODE"
for a in "${EXTRA_ARGS[@]:-}"; do [ "$a" = "--no-hint" ] && RUN_TAG="${MODE}_nohint"; done   # 避免蓋掉有提示的結果

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${TMPDIR:-/tmp}/tarnished-rag-llama"
CHUNK_DIR="$RUN_DIR/chunks_${RUN_TAG}"
TEMP_LOG="$RUN_DIR/paced_run_${RUN_TAG}_temps.log"
FINAL_OUT="$ROOT/eval/results/agent_${RUN_TAG}_predictions.jsonl"
mkdir -p "$CHUNK_DIR"

preflight() {
    local ok=1
    curl -sf http://127.0.0.1:8801/health > /dev/null || { echo "!! embedding server（8801）沒回應"; ok=0; }
    curl -sf http://127.0.0.1:8802/health > /dev/null || { echo "!! generation server（8802）沒回應"; ok=0; }
    timeout 3 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/7687" 2>/dev/null || { echo "!! Neo4j（7687）沒回應，用 <neo4j 安裝目錄>/bin/neo4j start 啟動"; ok=0; }
    [ "$ok" -eq 1 ] || { echo "有服務沒就緒，先不開始，避免整批白跑"; exit 2; }
}

gpu_temp() { nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1; }
cpu_temp() {
    for z in /sys/class/thermal/thermal_zone*/; do
        if [ "$(cat "${z}type" 2>/dev/null)" = "TCPU" ] || [ "$(cat "${z}type" 2>/dev/null)" = "x86_pkg_temp" ]; then
            awk '{printf "%.0f", $1/1000}' "${z}temp" 2>/dev/null && return
        fi
    done
}

log_temps() {
    local g c
    g="$(gpu_temp || true)"; c="$(cpu_temp || true)"
    printf "%s  GPU=%s°C  CPU=%s°C  %s\n" "$(date '+%H:%M:%S')" "${g:-?}" "${c:-?}" "$1" | tee -a "$TEMP_LOG"
}

wait_for_cooldown() {
    local waited=0 g c
    while :; do
        g="$(gpu_temp || echo 0)"; c="$(cpu_temp || echo 0)"
        if [ "${g:-0}" -le "$GPU_MAX_C" ] 2>/dev/null && [ "${c:-0}" -le "$CPU_MAX_C" ] 2>/dev/null; then
            return 0
        fi
        if [ "$waited" -ge "$TEMP_WAIT_MAX" ]; then
            log_temps "溫度還沒降到安全值以下，但已多等 ${TEMP_WAIT_MAX}s，放棄等待、繼續下一批（請留意實機狀況）"
            return 0
        fi
        log_temps "溫度偏高（門檻 GPU<=${GPU_MAX_C}°C CPU<=${CPU_MAX_C}°C），再等 ${TEMP_WAIT_STEP}s"
        sleep "$TEMP_WAIT_STEP"
        waited=$((waited + TEMP_WAIT_STEP))
    done
}

# 題號清單，依 questions.jsonl 原本順序
mapfile -t ALL_IDS < <(python3 -c "
import json
for l in open('$ROOT/eval/questions.jsonl', encoding='utf-8'):
    l = l.strip()
    if l: print(json.loads(l)['id'])
")
TOTAL=${#ALL_IDS[@]}
echo "共 $TOTAL 題，每批 $CHUNK_SIZE 題，每輪目標 ${CYCLE_SECONDS}s，溫度門檻 GPU<=${GPU_MAX_C}°C CPU<=${CPU_MAX_C}°C"
preflight
log_temps "開始前"

i=0
batch_no=0
while [ "$i" -lt "$TOTAL" ]; do
    batch_no=$((batch_no + 1))
    ids="$(IFS=,; echo "${ALL_IDS[*]:i:CHUNK_SIZE}")"
    out="$CHUNK_DIR/batch_${batch_no}.jsonl"
    if [ -s "$out" ]; then
        echo "第 $batch_no 批（$ids）已經有結果，跳過（要重跑就先刪 $out）"
    else
        t0=$(date +%s)
        echo "--- 第 $batch_no 批：$ids ---"
        python3 "$ROOT/src/agent/run_agent.py" --mode "$MODE" --ids "$ids" --out "$out" "${EXTRA_ARGS[@]}"
        elapsed=$(( $(date +%s) - t0 ))
        log_temps "第 $batch_no 批跑完，耗時 ${elapsed}s"
        remain=$((CYCLE_SECONDS - elapsed))
        [ "$remain" -gt 0 ] && { echo "睡 ${remain}s 湊滿這輪 ${CYCLE_SECONDS}s"; sleep "$remain"; }
    fi
    i=$((i + CHUNK_SIZE))
    if [ "$i" -lt "$TOTAL" ]; then
        wait_for_cooldown
    fi
done

cat "$CHUNK_DIR"/batch_*.jsonl > "$FINAL_OUT"
n=$(wc -l < "$FINAL_OUT")
echo "全部跑完，合併 $batch_no 批 -> $FINAL_OUT（$n / $TOTAL 題）"
[ "$n" -eq "$TOTAL" ] || echo "!! 題數對不上，檢查 $CHUNK_DIR 底下每批的行數"
log_temps "全部結束"
