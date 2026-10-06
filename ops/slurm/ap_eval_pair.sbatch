#!/usr/bin/env bash
# Two scorer-like evals on one DGX node (each: vLLM TP=4 on 4×A100, max_model_len 32768, thinking on).
# Usage: sbatch ops/slurm/ap_eval_pair.sbatch <subA> <runA> <subB> <runB> [task_ids_file|all]
#   e.g. sbatch ops/slurm/ap_eval_pair.sbatch submissions/c8_anchorplus c8_s1 submissions/c9a_editfix c9a_s1
#SBATCH -J ap-eval
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:8
#SBATCH --cpus-per-task=64
#SBATCH --mem=400G
#SBATCH --time=12:00:00
#SBATCH -o results/slurm/ap_eval_%j.out
set -uo pipefail
ROOT=/home/fmr-group/24b4518/project/Gemma_RL
cd "$ROOT"
SUBSET="${5:-all}"
export TP=4 MAX_LEN=32768 GPU_UTIL=0.90 CONCURRENCY="${CONCURRENCY:-4}"
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py >/dev/null

run_one() {  # gpus port sub run
  local gpus=$1 port=$2 sub=$3 run=$4
  CUDA_VISIBLE_DEVICES=$gpus PORT=$port scripts/serve_vllm.sh "$sub" > "results/slurm/vllm_${SLURM_JOB_ID}_$run.log" 2>&1 &
  local vpid=$!
  for _ in $(seq 1 90); do curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null && break; sleep 10; done
  if ! curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null; then echo "$run: VLLM_FAILED"; kill $vpid; return 1; fi
  echo "$(date +%T) $run: server up on $port"
  PORT=$port scripts/eval_submission.sh "$sub" "$run" "$SUBSET" > "results/slurm/eval_${SLURM_JOB_ID}_$run.log" 2>&1
  echo "$(date +%T) $run: eval rc=$?"
  kill $vpid; wait $vpid 2>/dev/null
}
run_one 0,1,2,3 8021 "$1" "$2" &
run_one 4,5,6,7 8022 "$3" "$4" &
wait
echo EVAL_PAIR_DONE
