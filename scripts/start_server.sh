#!/usr/bin/env bash
# (Re)start the local vLLM server with the config that works on this shared box, wait until healthy,
# and send a warm-up request (first PP request initializes NCCL P2P lazily and can stall otherwise).
# Defaults: pipeline split 52/8 over GPU0/GPU1, per-rank KV 3.55/1.5 GiB, 20k context (leaves ~3.5 GB on GPU0 for a teammate), 1 running seq
# (avoids a PP scheduler stall after preemption). Override any env var of serve_vllm.sh.
# Usage: scripts/start_server.sh [submission_dir_with_adapters]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export MODE="${MODE:-pp_shared}" CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}" PORT="${PORT:-8011}"
export PP_PARTITION="${PP_PARTITION:-52,8}" KV_GIB_PER_RANK="${KV_GIB_PER_RANK:-3.55,1.5}"
export MAX_LEN="${MAX_LEN:-20480}" MAX_SEQS="${MAX_SEQS:-1}"
export GEMMA_RL_MIN_OUTPUT_RESERVE="${GEMMA_RL_MIN_OUTPUT_RESERVE:-2048}"  # clamp max_tokens instead of 400 (see patch)

scripts/stop_vllm.sh >/dev/null
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py >/dev/null
nohup scripts/serve_vllm.sh "$@" > results/vllm_server.log 2>&1 &
for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null && break
  if ! pgrep -f "^$ROOT/.venv-harness/bin/python" >/dev/null; then
    echo "VLLM_DIED"; grep -E "Error|error:" results/vllm_server.log | grep -v 'File "' | tail -5; exit 1
  fi
  sleep 10
done
curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null || { echo "VLLM_TIMEOUT"; exit 1; }
timeout 300 curl -s "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"gemma-4-31b-it-qat-w4a16-ct","messages":[{"role":"user","content":"warm up"}],"max_tokens":5}' >/dev/null \
  && echo "VLLM_UP port=$PORT" || { echo "WARMUP_FAILED"; exit 1; }
