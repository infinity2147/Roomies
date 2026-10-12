#!/bin/bash
#SBATCH -J ap-pxreport
#SBATCH -p a40
#SBATCH --qos=a40
#SBATCH -t 00:25:00
#SBATCH --cpus-per-task=4
#SBATCH -o results/slurm/ap-pxreport-%j.log
cd /home/fmr-group/24b4518/project/Gemma_RL
for b in c23 c9e; do echo "=== base $b"; .venv/bin/python ops/queue/px_report.py --base $b --done-only; done 2>&1 | grep -E -i "=== |c24|c25|c23 |c9e " 
