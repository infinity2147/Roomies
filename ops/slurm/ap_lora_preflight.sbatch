#!/usr/bin/env bash
# LoRA training preflight (D10): memory/throughput at 32k context on 1×A100-80GB, random tokens, 2 steps.
#SBATCH -J ap-lora-preflight
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=01:00:00
#SBATCH -o results/slurm/ap_lora_preflight_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
.venv-harness/bin/python -m src.sft.train_lora --preflight --seq-len 32768
echo "PREFLIGHT_RC=$?"
