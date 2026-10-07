#!/usr/bin/env bash
# E2 pilot: LoRA SFT of Gemma-4-31B (frozen int4 QAT base) on converted Nebius trajectories (external, CC-BY-4.0).
# Preflight at rank 128 (literature: multi-step agent skills need high rank); fall back to 64 if it does not fit.
#SBATCH -J ap-train-e2
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=4-00:00:00
#SBATCH -o results/slurm/ap_train_e2_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
D=data/derived/sft/e2_nebius_pilot.jsonl
for f in data/derived/sft/e2_nebius/shard_*.jsonl; do head -n ${PER_SHARD:-64} "$f"; done > $D; echo "sequences: $(wc -l < $D)  (first ${PER_SHARD:-64} windows per shard; pilot)"
R=128
.venv-harness/bin/python -m src.sft.train_lora --preflight --seq-len 24576 --rank 128 2>&1 | tail -3 | tee /dev/stderr | grep -q "peak" || R=64
echo "rank=$R"
.venv-harness/bin/python -m src.sft.train_lora --data $D --out runs/lora/e2_nebius_r$R --rank $R --alpha $((2*R)) \
  --epochs 1 --lr 1e-4 --grad-accum 8 --max-tokens 24576 --save-every-epoch 2>&1 | tail -40
echo TRAIN_DONE
