
## This cycle: WORK (cycles run back-to-back; the user wants the cluster and your token budget used hard)
1. Read ops/autopilot/STATE.md, reports/council/strategy_20261007.md (the research program) and ops/autopilot/lb_scores.tsv.
   Check `squeue -u $USER`, finished job logs in results/slurm/, ops/queue/{done,failed}, ops/queue_cap, and the Kaggle
   kernel statuses listed in STATE.md. Harvest every finished result into STATE.md (px_report, paired stats).
2. If a new LB score appeared, interpret it (vs champion, vs noise of ±1–2 tasks) and update the champion / decisions.
3. KEEP THE GPUs FULL: target 16–20 GPUs busy at all times (QoS caps in STATE.md). If workers are ending within 2 h,
   resubmit now. If ops/queue/pending has < 2 h of work, enqueue the next experiments from the program (seeds first for
   anything within ±0.05 of the leader, then new one-change candidates, then capture runs for E1).
4. ADVANCE THE PROGRAM, not just the queue: every cycle must also make progress on at least one P0/P1 research item
   (build the next candidate, write the analysis, extend the SFT pipeline, run forensics on new failures). Use the Agent
   tool with 2–4 parallel subagents for independent investigations. A cycle that only waits is a failed cycle.
5. Build new candidate submissions under submissions/<name>/ (validate each with scripts/package_submission.sh) and keep
   tomorrow's submissions/daily/<date>/RELEASE.md draft current (line 1 = `SUBMIT: <zip>`; the runtime gate must pass).
6. Update STATE.md (status, running jobs + what to check, results, backlog re-prioritized), commit, then end with a 5-line
   summary: what you did, what is running, what the next cycle should do.
Use up to ~60 minutes of wall time per cycle; do not stop early while there is queued work you could prepare.
