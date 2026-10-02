#!/usr/bin/env bash
# Run once GPUs are free: start vLLM (TP=2) in the background, wait until healthy, then smoke-test
# the sample submission on 3 valid tasks (one per repo). Server keeps running afterwards.
# Logs: results/vllm_server.log, results/b0_smoke/
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8011}"

if ! curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null; then
  CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}" TP=2 GPU_UTIL="${GPU_UTIL:-0.88}" \
    nohup scripts/serve_vllm.sh data/sample_submission > results/vllm_server.log 2>&1 &
  echo "vllm pid $!" > results/vllm_server.pid
  for _ in $(seq 1 180); do
    curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null && break
    if ! kill -0 "$(awk '{print $3}' results/vllm_server.pid)" 2>/dev/null; then
      echo "VLLM_DIED"; tail -40 results/vllm_server.log; exit 1
    fi
    sleep 10
  done
fi
curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null || { echo "VLLM_TIMEOUT"; tail -40 results/vllm_server.log; exit 1; }
echo "VLLM_UP"

printf "requests_7309\nfastapi_14463\nrich_2725\n" > results/b0_smoke_ids.txt
CONCURRENCY=3 scripts/eval_submission.sh data/sample_submission b0_smoke results/b0_smoke_ids.txt
echo "SMOKE_DONE"; cat results/b0_smoke/summary.json 2>/dev/null
