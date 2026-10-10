#!/usr/bin/env bash
# GPU eval worker: one vLLM server per allocated GPU (TP=1, scorer flags: max_model_len 32768, thinking on,
# gemma4 tool/reasoning parsers); each GPU slot pulls items from the shared queue ops/queue/pending until empty.
# Item file content: "<submission_dir> <run_name> <task_ids_file> <public|proxy>"; claimed atomically by rename.
# Submit:  sbatch -p a40 --qos=a40 --gres=gpu:4 ops/slurm/ap_worker.sbatch      (any partition / GPU count)
#SBATCH -J ap-worker
#SBATCH --cpus-per-task=32
#SBATCH --mem=240G
#SBATCH --time=10:00:00
#SBATCH -o results/slurm/ap_worker_%j.out
set -uo pipefail
ROOT=/home/fmr-group/24b4518/project/Gemma_RL
cd "$ROOT"
Q=${APQ:-ops/queue}   # APQ=ops/queue_cap + CAPTURE=1: route LLM calls through src/sft/capture_proxy (E1 SFT data)
mkdir -p $Q/pending $Q/running $Q/done $Q/failed
NG=$(nvidia-smi -L | wc -l)
GPUS=(${CUDA_VISIBLE_DEVICES//,/ })
MEMGB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
CONC=${CONC:-$(( MEMGB > 60000 ? 10 : 6 ))}
echo "$(date +%T) node $(hostname -s) gpus=${CUDA_VISIBLE_DEVICES} conc=$CONC"
export LITELLM_LOCAL_MODEL_COST_MAP=True OTEL_SDK_DISABLED=true OPENAI_API_KEY=EMPTY
export TP=1 MAX_LEN=32768 GPU_UTIL=0.92
# The harness baseline `git commit` silently fails without a git identity (cn17-dgx: no auto-detectable email),
# which leaks harness conftest.py/pytest.ini into every patch. Set it explicitly (D18).
export GIT_AUTHOR_NAME=swegemma GIT_AUTHOR_EMAIL=swegemma@localhost GIT_COMMITTER_NAME=swegemma GIT_COMMITTER_EMAIL=swegemma@localhost

slot() {  # $1 = local gpu index
  local i=$1 port=$((8100 + $1)) tag="${SLURM_JOB_ID}_$1"
  CUDA_VISIBLE_DEVICES=${GPUS[$i]} PORT=$port scripts/serve_vllm.sh ${SERVE_SUB:-} > results/slurm/vllm_$tag.log 2>&1 &
  local vpid=$!
  for _ in $(seq 1 120); do curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null && break
    kill -0 $vpid 2>/dev/null || break; sleep 10; done
  if ! curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null; then
    echo "$(date +%T) slot $i: VLLM_FAILED"; tail -5 results/slurm/vllm_$tag.log; kill $vpid 2>/dev/null; return 1; fi
  echo "$(date +%T) slot $i: server up"
  local api=$port cpid=""
  if [[ "${CAPTURE:-0}" == 1 ]]; then
    api=$((8200 + $1)); mkdir -p results/capture
    .venv/bin/python -m src.sft.capture_proxy --listen $api --upstream "http://127.0.0.1:$port" \
      --out "results/capture/${tag}.jsonl" > results/slurm/capture_$tag.log 2>&1 &
    cpid=$!; sleep 3; echo "$(date +%T) slot $i: capture proxy :$api -> results/capture/${tag}.jsonl"
  fi
  while true; do
    local item claimed=""
    if [[ -n "${SLURM_JOB_ID:-}" ]]; then  # do not start an item the job cannot finish (gpu_filler returns orphans anyway)
      local left; left=$(squeue -h -j "$SLURM_JOB_ID" -o %L 2>/dev/null)
      if [[ "$left" =~ ^(([0-9]+)-)?(([0-9]+):)?([0-9]+):([0-9]+)$ ]]; then
        local lm=$(( ${BASH_REMATCH[2]:-0}*1440 + 10#${BASH_REMATCH[4]:-0}*60 + 10#${BASH_REMATCH[5]} ))
        (( lm < ${MIN_LEFT_MIN:-90} )) && { echo "$(date +%T) slot $i: only ${lm} min left, not claiming"; break; }
      fi
    fi
    for item in $(ls $Q/pending 2>/dev/null | sort); do
      mv "$Q/pending/$item" "$Q/running/$item.$tag" 2>/dev/null && { claimed=$item; break; }
    done
    [[ -z "$claimed" ]] && break
    read -r sub run tasks mode < "$Q/running/$claimed.$tag"
    local out="results/px/$run/$(basename "$tasks" .txt)"; mkdir -p "$out"
    local extra=(); [[ "$mode" == proxy ]] && extra=(--proxy)
    echo "$(date +%T) slot $i: start $claimed"
    [[ -n "$cpid" ]] && echo "{\"t\": $(date +%s), \"item\": \"$claimed\", \"run\": \"$run\"}" >> "results/capture/${tag}.items.jsonl"
    local t0=$(date +%s)
    .venv-eval/bin/python -m src.eval.run_eval --submission-dir "$sub" --results-dir "$out" \
      --task-ids $(cat "$tasks") --concurrency $CONC --api-base "http://127.0.0.1:$api/v1" "${extra[@]}" \
      > "$out/run_eval.log" 2>&1
    local rc=$? dt=$(( $(date +%s) - t0 ))
    echo "$(date +%T) slot $i: end $claimed rc=$rc ${dt}s $(tail -1 $out/run_eval.log | cut -c1-80)"
    if (( rc == 0 )); then mv "$Q/running/$claimed.$tag" "$Q/done/$claimed"; else mv "$Q/running/$claimed.$tag" "$Q/failed/$claimed"; fi
    kill -0 $vpid 2>/dev/null || { echo "slot $i: vllm died"; return 1; }
  done
  kill $vpid $cpid 2>/dev/null; wait $vpid 2>/dev/null
  echo "$(date +%T) slot $i: queue empty, exiting"
}
( t=$(mktemp -d) && cd "$t" && git init -q && touch x && git add -A && git commit -qm t && echo "git-commit selftest OK" \
  || echo "git-commit selftest FAILED"; rm -rf "$t" )
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py >/dev/null
for i in $(seq 0 $((NG - 1))); do slot $i & sleep 5; done
wait
echo WORKER_DONE
