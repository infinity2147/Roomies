#!/bin/bash
#SBATCH -J ap-pxreport
#SBATCH -p a40
#SBATCH --qos=a40
#SBATCH -t 00:40:00
#SBATCH --cpus-per-task=4
#SBATCH -o results/slurm/ap-pxreport-%j.log
cd /home/fmr-group/24b4518/project/Gemma_RL
for b in c23; do echo "=== base $b"; .venv/bin/python ops/queue/px_report.py --base $b --done-only; done 2>&1 | grep -E -i "=== |c25|c23 "
echo "=== time budget"; .venv/bin/python src/analysis/time_budget.py --out reports/time_budget_c25 2>&1 | tail -40
