#!/usr/bin/env bash
# Wait until GPU0 has room for our pipeline stage (teammate jobs come and go), then start the server.
# Polls every INTERVAL seconds; exits 0 with "VLLM_UP" once healthy, non-zero on a hard failure.
# env: NEED_MIB (default 21300), INTERVAL (default 120) + any start_server.sh/serve_vllm.sh vars.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEED_MIB="${NEED_MIB:-21300}"; INTERVAL="${INTERVAL:-120}"
while true; do
  if curl -sf "http://127.0.0.1:${PORT:-8011}/v1/models" >/dev/null; then echo "VLLM_UP (already running)"; exit 0; fi
  free0=$(nvidia-smi -i 0 --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' ')
  free1=$(nvidia-smi -i 1 --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' ')
  echo "$(date '+%F %T') gpu0_free=${free0} gpu1_free=${free1}" >> "$ROOT/results/gpu_watch.log"
  if (( free0 >= NEED_MIB && free1 >= 8800 )); then
    if "$ROOT/scripts/start_server.sh"; then exit 0; fi
    echo "$(date '+%F %T') start failed; retrying later" >> "$ROOT/results/gpu_watch.log"
  fi
  sleep "$INTERVAL"
done
