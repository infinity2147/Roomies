#!/usr/bin/env bash
# CPU: gold (should pass) / empty (should fail) verification of the 152 proxy tasks in the Prajna environment.
#SBATCH -J ap-verify
#SBATCH -p a40
#SBATCH --qos=a40
#SBATCH --cpus-per-task=24
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH -o results/slurm/ap_verify_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
ids=$(python3 -c "import json;print(' '.join(json.loads(l)['instance_id'] for l in open('data/derived/proxy/valid_tasks.jsonl')))")
for m in gold empty; do
  .venv-eval/bin/python -m src.analysis.hidden.verify_proxy --mode $m --concurrency 12 --name prajna_proxy_ \
     --tasks data/derived/proxy/valid_tasks.jsonl --task-ids $ids | tail -2
done
echo VERIFY_DONE
