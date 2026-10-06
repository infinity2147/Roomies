
## This cycle: WORK
1. Read ops/autopilot/STATE.md and ops/autopilot/lb_scores.tsv. Check `squeue -u $USER`, finished job logs in
   results/slurm/, and Kaggle kernel statuses listed in STATE.md. Harvest every finished result into STATE.md.
2. If a new LB score appeared, interpret it (vs champion, vs noise of ±1–2 tasks) and update the champion /
   decisions accordingly.
3. Pick the highest expected-impact backlog items that are unblocked, and advance them: build tooling, launch
   SLURM/Kaggle jobs (keep GPUs busy with useful work within the compute rules), analyze results, and write new
   candidate submissions under submissions/<name>/ (validate each with scripts/package_submission.sh).
4. Plan ahead so that before the next daily release there is evidence to choose the best candidate.
5. Update STATE.md (status, running jobs + what to check, results, backlog re-prioritized), commit, then end
   with a 5-line summary: what you did, what is running, what the next cycle should do.
Aim to finish within ~2 hours of wall time.
