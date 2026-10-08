#!/usr/bin/env bash
# E2b: LoRA SFT on the external mix (Nebius verified + SWE-Hero) + own rollouts from the proxy TRAIN half only.
# Evaluate the resulting adapter on ops/queue/shards/proxy_eval_half.txt (85 tasks, repos never trained on).
#SBATCH -J ap-train-mix
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=5-00:00:00
#SBATCH -o results/slurm/ap_train_mix_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
D=data/derived/sft/mix_v1.jsonl
OWN=$(ls data/derived/sft/e1_own_*.jsonl 2>/dev/null)
.venv/bin/python -m src.sft.mix_datasets --external data/derived/sft/e2_nebius data/derived/sft/e2_swe_hero \
  --own $OWN --own-share ${OWN_SHARE:-0.3} --max-seqs ${MAX_SEQS:-1500} --out $D
.venv-harness/bin/python -m src.sft.train_lora --data $D --out runs/lora/mix_v1_r128 --rank 128 --alpha 256 \
  --epochs 1 --lr 1e-4 --grad-accum 8 --max-tokens 24576 --save-every-epoch 2>&1 | tail -40
echo TRAIN_DONE
