#!/usr/bin/env bash
# E3 thinking distillation: SFT the thinking-OFF root on resolved THINKING runs (C11t captures) rendered without reasoning.
# Then package C19 = C9ae (same root prompt as the captures) + adapter d1 and enqueue a held-out-half proxy eval.
#SBATCH -J ap-train-distill
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=2-00:00:00
#SBATCH -o results/slurm/ap_train_distill_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
.venv-harness/bin/python -m src.sft.train_lora --data data/derived/sft/e3_distill_all.jsonl --out runs/lora/e3_distill_r128 \
  --rank 128 --alpha 256 --epochs 2 --lr 1e-4 --grad-accum 8 --max-tokens 24576 --save-every-epoch 2>&1 | tail -30 || exit 1
A=runs/lora/e3_distill_r128/adapter; [ -f $A/adapter_config.json ] || { echo "NO ADAPTER"; exit 1; }
S=submissions/c19_c9ae_distill; rm -rf $S; cp -r submissions/c9ae_editfix_analyzercap $S
mkdir -p $S/adapters && cp -r $A $S/adapters/d1
sed -i 's/^model: gemma-4-31b-it-qat-w4a16-ct$/model: gemma-4-31b-it-qat-w4a16-ct\nadapter: d1/' $S/agent.yaml
scripts/package_submission.sh $S results/zips/c19.zip | tail -2
mkdir -p ops/queue_lora_d1/pending
for s in 1 2; do for f in ops/queue/shards/proxy_evalhalf/*.txt; do b=$(basename $f .txt)
  echo "$S px_c19_distill_s$s $f proxy" > ops/queue_lora_d1/pending/04_${b}_px_c19_distill_s$s; done; done
echo TRAIN_DONE
