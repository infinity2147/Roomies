#!/usr/bin/env bash
# Serve the competition model with the Kaggle scorer's vLLM settings
# (tool/reasoning parser gemma4, max_model_len 32768, LoRA on, thinking on).
#
# Modes (env MODE):
#   tp     (default) tensor parallel over both GPUs; needs ~21 GB free on each.
#   pp_shared  pipeline parallel with an uneven layer split, for a shared box where GPU1 is partly
#          occupied: most layers on the first visible GPU, few + lm_head on the second. KV cache is
#          a fixed size per GPU (KV_GIB) so vLLM's utilization check doesn't block startup.
# Usage: scripts/serve_vllm.sh [submission_dir_with_adapters]   (LoRA enabled only if it has adapters/)
#   env: CUDA_VISIBLE_DEVICES, PORT, TP, GPU_UTIL, MAX_LEN, PP_PARTITION (e.g. 54,6), KV_GIB, KV_GIB_PER_RANK (e.g. 4.2,1.5), MAX_SEQS, MAX_LORAS, MAX_LORA_RANK
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$ROOT/external/models/gemma-4-31b-it-qat-w4a16-ct"
SUB="${1:-}"
MODE="${MODE:-tp}"
PORT="${PORT:-8011}"
MAX_LEN="${MAX_LEN:-32768}"

LORA_ARGS=()
if [[ -n "$SUB" && -d "$SUB/adapters" ]]; then
  mods=()
  for d in "$SUB"/adapters/*/; do
    [[ -f "$d/adapter_config.json" ]] && mods+=("$(basename "$d")=$(realpath "$d")")
  done
  # MAX_LORAS defaults to the number of adapters actually served: every slot pre-allocates a full rank-128 all-linear
  # buffer (~1.9 GiB each); the old default of 8 left 5.5 GiB KV (6k tokens) on an A40 at TP=1 and made LoRA evals
  # queue/preempt into 60-min timeouts (reports/lora_forensics_20261010.md).
  ((${#mods[@]})) && LORA_ARGS=(--enable-lora --max-loras "${MAX_LORAS:-${#mods[@]}}" --max-lora-rank "${MAX_LORA_RANK:-128}"
                                  --lora-modules "${mods[@]}")
fi

PAR_ARGS=()
if [[ "$MODE" == "pp_shared" ]]; then
  export VLLM_PP_LAYER_PARTITION="${PP_PARTITION:-54,6}"
  [[ -n "${KV_GIB_PER_RANK:-}" ]] && export GEMMA_RL_KV_GIB_PER_RANK="$KV_GIB_PER_RANK"  # needs scripts/patch_vllm_gemma4_pp.py
  kv_bytes=$(python3 -c "print(int(${KV_GIB:-3} * 2**30))")
  [[ -n "${MAX_BATCHED:-}" ]] && EXTRA_BATCH=(--max-num-batched-tokens "$MAX_BATCHED") || EXTRA_BATCH=()
  PAR_ARGS=(--pipeline-parallel-size 2 --gpu-memory-utilization "${GPU_UTIL:-0.30}"
            --kv-cache-memory-bytes "$kv_bytes" --max-num-seqs "${MAX_SEQS:-4}"
            --language-model-only --enforce-eager "${EXTRA_BATCH[@]}")
  [[ -n "${KV_DTYPE:-}" ]] && PAR_ARGS+=(--kv-cache-dtype "$KV_DTYPE")
else
  PAR_ARGS=(--tensor-parallel-size "${TP:-2}" --gpu-memory-utilization "${GPU_UTIL:-0.90}")
fi

export VLLM_WORKER_MULTIPROC_METHOD=spawn VLLM_NO_USAGE_STATS=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
exec "$ROOT/.venv-harness/bin/vllm" serve "$MODEL" \
  --served-model-name gemma-4-31b-it-qat-w4a16-ct \
  --host 127.0.0.1 --port "$PORT" \
  --max-model-len "$MAX_LEN" \
  --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
  --reasoning-config '{"reasoning_start_str": "<|channel>", "reasoning_end_str": "<channel|>"}' \
  --default-chat-template-kwargs '{"enable_thinking": true}' \
  --enable-prefix-caching \
  "${PAR_ARGS[@]}" "${LORA_ARGS[@]}"
