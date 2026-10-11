#!/usr/bin/env bash
# Edit-call replay micro-benchmark: serve the base model on 1 GPU and replay captured edit requests under variants.
#SBATCH -J ap-edit-replay
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=03:00:00
#SBATCH -o results/slurm/ap_edit_replay_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
export TP=1 MAX_LEN=32768 GPU_UTIL=0.92 PORT=8100
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py >/dev/null
scripts/serve_vllm.sh > results/slurm/vllm_edit_replay_$SLURM_JOB_ID.log 2>&1 &
for _ in $(seq 1 120); do curl -sf http://127.0.0.1:8100/v1/models >/dev/null && break; sleep 10; done
M=$(curl -s http://127.0.0.1:8100/v1/models | python3 -c "import sys,json;print(json.load(sys.stdin)['data'][0]['id'])")
echo "server up, model $M"
S=results/edit_replay/set.jsonl; V=results/edit_replay/variants; O=results/edit_replay
R() { .venv/bin/python -m src.analysis.edit_replay run --set $S --api http://127.0.0.1:8100/v1 --model "$M" --n ${N:-4} --workers 12 "$@"; }
R --variant v0_base --out $O/v0_base.jsonl
R --variant v1_format --append $V/v1_format.md --out $O/v1_format.jsonl
R --variant v2_loopbreak --append $V/v2_loopbreak.md --out $O/v2_loopbreak.jsonl
R --variant v3_small --append $V/v3_small.md --out $O/v3_small.jsonl
R --variant v4_all --append $V/v4_all.md --out $O/v4_all.jsonl
R --variant v5_temp0 --temperature 0 --out $O/v5_temp0.jsonl
R --variant v6_temp07 --temperature 0.7 --out $O/v6_temp07.jsonl
.venv/bin/python -m src.analysis.edit_replay report $O/v*.jsonl
echo REPLAY_DONE
