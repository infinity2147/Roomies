#!/usr/bin/env bash
# E2: convert Nebius OpenHands trajectories -> SFT windows, one shard per array task (CPU only).
# sbatch ops/slurm/ap_convert_nebius.sbatch   (NSHARDS parallel shards in one job, N_PER_SHARD trajectories each)
#SBATCH -J ap-convert
#SBATCH -p a40
#SBATCH --qos=a40
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=12:00:00
#SBATCH -o results/slurm/ap_convert_%j.out
cd /home/fmr-group/24b4518/project/Gemma_RL
N=${N_PER_SHARD:-64}; T=${NSHARDS:-16}
for K in $(seq 0 $((T-1))); do
  .venv-harness/bin/python -m src.sft.convert_openhands --n $N --shard $K --nshards $T \
    --out data/derived/sft/e2_nebius/shard_$K.jsonl > results/slurm/ap_convert_${SLURM_JOB_ID}_$K.log 2>&1 &
done
wait
cat data/derived/sft/e2_nebius/shard_*.jsonl | wc -l
echo CONVERT_DONE
