# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## RESEARCH PROGRAM (lead session 12:30) — read reports/council/strategy_20261007.md every cycle
Cadence changed: cycles every 15 min, up to 60 min of work each, 16–20 GPUs busy at all times. P0 order:
1. Settle the base: seed 2 for C11t / C11n / C13t (paired n ≥ 150 × 2 seeds) and the D25 L4 timing gate; add runtime
   insurance (`eval_config max_time_minutes` ≈ 5) to the 10-08 candidate if its L4 ratio > 1.05.
2. L2 feasibility spike (memo §6b refined design): Sequential[ Parallel[solver_A repro-first, solver_B test-first,
   test_writer] → selector ]. Budget is ONE shared 100-call counter (context.py:549) → prompt caps 35/35/15/15.
   Remaining unknowns: can edit_file/read_file touch /tmp worktrees (write_file cannot)? L4 wall time (target ≤ 1.4× C11t).
   Build the K=2 prototype, run 2 shards paired vs C11t, time it. Cheap variant if isolation fails: parallel planners + critic.
3. E1 capture at scale on the C11t base: **8–10 rollouts/task** (T≈0.8), proxy+public (+ synthetic), target ≥1–2k resolved
   trajectories, cap 3/task, mask malformed turns (memo §6a) → `train_lora.py --preflight` at **rank 128** all-linear
   (fall back to 64 if >75 GiB) → 4 LORO folds on DGX. Check the rules before any non-Gemma teacher distillation.
4. Rebuild the ACI micro-fixes (repro-must-fail, import check, timebox, anti-loop) on the C11t base; seeds.
5. Synthetic tasks (SWE-smith-style bug injection) + more Google-style repos for proxy/SFT.
6. Kaggle intel (memo §6c): public LB top 0.24, cluster 0.15, we are 0.13; public = ~half of hidden; 2 finals selected.
   A participant saw `get_code_*` graph tools return EMPTY in official runs → every candidate (esp. C13t locate skill) must
   degrade gracefully with no graphs/embeddings. Checked 12:55: C13t's `skills/repo-locate/scripts/locate.py` has no
   graph/embedding dependency; the analyzer merely *offers* get_code_* tools, which already return empty on proxy repos
   (shim has public graphs only) — so proxy scores are measured under the pessimistic no-graph condition. OK.
7. Paper track: target the **New Resource** prize with the proxy benchmark + synthetic generator + forensics taxonomy
   (memo §6c); RL-re-ranked traversal only as a section if results exist by ~Nov 1.

## TODAY (2026-10-07) — RELEASE = C9ae (final; D22 not met: C11t kernel still RUNNING at 11:30)
- Nothing left to do for today's release. If the C9ae LB score arrives, log it in lb_scores.tsv (vs C8 0.13; noise ±0.03).

## Tomorrow (2026-10-08): submissions/daily/2026-10-08/RELEASE.md DRAFT (line 1 = C9ae). Planned pick = C11t if the D25 gate passes
- **D25 (11:50):** C9ae L4 kernel COMPLETE: 8/30, 4.92 min/task serial (results/kaggle/c9ae-t30s). 150×mean rule fails even for C9ae
  (12.8 h) though C8-speed runs completed on the scorer → gate is now the paired L4 total-time ratio vs c9ae-t30s ≤ 1.10 (same 30 ids,
  data/derived/l4_t30_ids.txt). L4 cost model: decode 87% of time (~35 tok/s); predicts C11t ≈ 1.04× C9ae.
- When `gemma-rl-eval-c11t-t30s` is COMPLETE (est. ~14:30): `.venv/bin/kaggle kernels output vedantmoghe/gemma-rl-eval-c11t-t30s -p results/kaggle/c11t-t30s`,
  then `.venv/bin/python scripts/kaggle_eval/capture_task_times.py c11t-t30s c9ae-t30s` (d9_timing.py does not work: no task_results.jsonl in
  kernel output). ≥25 tasks and ratio ≤ 1.10 → set 2026-10-08 line 1 to `SUBMIT: submission_2026-10-08_c11t_c9ae_think.zip` + D-entry.
- `gemma-rl-eval-c11n-t30s` (same ids) pushed 11:45 (est. done ~15:00). Fallback if C11t > 1.10: C11n if ≤ 1.10 and proxy ≥ −0.01 vs C11t.
  If both > 1.10: build C11t + eval_config `max_time_minutes` cap (+ thinking_budget 2048) and L4-time it; keep C9ae meanwhile.
- C11n / C13t vs C11t on proxy (11:40): C11n n=48 +0.021 (4W/3L), C13t n=45 +0.044 (5W/3L) — not decisive yet (≥60 pairs needed, D21/D23).

## Queue (ops/queue; items sorted by name)
07 C11n s1 + C13t s1 (s0–s1 running) + C8 s7 → 08 anchor/c6a_t5 s1 (D11 calibration) + C9ae s2 → 14 C9all → 15 C9c → 20 C9a/C9e s6–s7 → 22 C9b
→ 25 C9d → 40/41 s2 seeds of old candidates (low value; delete if the GPUs are needed). C10 s4/s5/s7 still running (let them finish; no more C10).
**Capture queue ops/queue_cap** (NEW): 08 C11t s2 s0–s7, run by worker job `ap-worker-cap` (sbatch `--export=ALL,APQ=ops/queue_cap,CAPTURE=1`).
It writes results/px/px_c11t_s2 (px_report picks it up) and results/capture/<job>_<slot>.jsonl (all LLM calls, with reasoning) plus
<tag>.items.jsonl (item start times, used to map calls to shards). Only new workers support APQ/CAPTURE; old workers read only ops/queue.
Workers: `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N --cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch`
(QoS caps: a40 ≤2 GPU/job & 3 jobs, l40 ≤4/job & 4 jobs, dgx ≤4/job & 4 jobs). Add work: `ops/queue/enqueue.sh <prio> <sub> <run> proxy`. leak must be 0 (D18).

## Running jobs (as of 11:50 IST 2026-10-07)
- ap-worker RUNNING: 337605 (a40 1), 337608 (a40 2), 337687 (a40 2), 337593 (l40 1), 337612 (l40 1) = 7 GPUs. 10 h limit → they END ~14:15–14:30 IST.
  **The first cycle after 14:15 must resubmit workers** (keep total ≤ 16 GPUs incl. pending) or the main queue stalls.
- PENDING: 338533 (dgx 4), 338535 (l40 2), 339851 ap-worker-cap (l40 2, capture queue ops/queue_cap). When they start:
  `grep selftest results/slurm/ap_worker_<id>.out` must say OK; for 339851 also check "capture proxy" lines and results/capture/339851_*.jsonl growing.
  If capture shards fail (ops/queue_cap/failed), move items back to ops/queue/pending as plain runs and debug offline.
- Kaggle (vedantmoghe, private, pinned image D20; 2 slots both busy): `gemma-rl-eval-c11t-t30s` RUNNING since 08:30; `gemma-rl-eval-c11n-t30s` pushed 11:45.
  `gemma-rl-eval-c9ae-t30s` COMPLETE (fetched).

## Findings this cycle
- Harness (reports/autopilot/harness_knobs_20261007.md): no schema key hard-caps sub-agent calls; submit_patch doesn't end the run;
  no sub-agent compaction. Structural options left: skill scripts (not budget-gated) for localization; `sub_agents` transfer
  instead of agent_tool (gets compaction); `seed` for less noisy A/B.
- E1 (reports/autopilot/e1_inventory.md): 173 passing proxy trajectories / 66 tasks, but no thinking text and not captured via the
  capture proxy → not SFT-ready. Plan: after D19 resolves, run capture-enabled seeds of the winner; 4-fold LORO by repo group.

## Environment status (2026-10-07)
- Prajna: .venv, .venv-eval built on login; .venv-harness (vLLM 0.19.1 + Kaggle Gemma-4 LoRA build, torch 2.10 cu128)
  verified on a DGX A100 node (job 337488: `server env ok ... gpu True`, `lora-capable: True`).
- Model weights: see shared-gpu-serving-setup memory / scripts/serve_vllm.sh for the local path (gemma-4-31b-it-qat-w4a16-ct).
- NOT yet built: a SLURM job that serves vLLM on a DGX node and runs the harness eval there (old box used PP 52/8 on
  port 8011 via scripts/serve_vllm.sh + scripts/eval_submission.sh).
- Kaggle: kverify-fix3 (CPU gold/empty verification with sandbox fix v3) ended in ERROR with an empty log; cause not
  investigated. Dataset vedantmoghe/gemma-rl-proxy is `ready`. results/chain_master.sh (old machine) never got past the gate.

## Backlog (prioritized; re-prioritize every cycle)
0. P0 Afternoon: fetch c11t-t30s (and later c11n-t30s) → capture_task_times.py vs c9ae-t30s → finalize the 2026-10-08 line 1 by D25.
1. P0 Resubmit workers when the 10 h workers end (~14:30). Then L4 timing for the C11n/C13t leader once the Kaggle slots free.
2. P0 Proxy calibration (D11): anchor + c6a_t5 s1 at prio 08. Pass rule: anchor > c6a_t5, and C8 ≥ anchor.
3. P1 C11n vs C11t and C13t vs C11t (D21/D23) → candidate for 2026-10-09. If both win: build C11n + repo-locate on the root.
4. P1 Analyzer via `sub_agents` transfer (compaction) as an alternative to agent_tool, if C11n loses (i.e. the analyzer is still useful).
5. P1 E1: capture of C11t s2 is running (ops/queue_cap) → extend src/sft/build_dataset.py to read results/capture/*.jsonl (map calls to
   tasks via the first user message / items.jsonl; split analyzer sessions) → 4-fold LORO LoRA (train_lora.py --preflight first).
6. P2 Paper track (deadline 2026-11-12): reports/council/paper_plan.md; the user must join the paper competition (D8).
7. P3 kverify-fix3 Kaggle ERROR / stale Kaggle proxy dataset (rebuild with the 152-task set + shim only if L4 proxy scores needed).

## Open questions for the user (write here; user reads RELEASE.md / STATE.md)
- Are the submitting account and vedantmoghe on the same Kaggle Team (D14)?
- Joined the paper competition (D8)?

## Journal
- 2026-10-07 11:50: cycle 112820: no LB; C11t kernel still running → C9ae ships today (final). C9ae L4 kernel done: 4.92 min/task,
  150-task D9 rule unattainable even for C8-speed → D25 gate = L4 ratio vs C9ae ≤ 1.10 (model predicts C11t 1.04×); capture_task_times.py;
  C11n L4 kernel pushed on the same 30 ids.
- 2026-10-07 10:45: cycle 102819: no LB; C11t s1 complete (+0.112 vs C9ae, n=152, 1.25× time); L4 kernels not done → C9ae ships today
  (D24), C11t planned for 2026-10-08 pending L4; C10 dropped; capture option in ap_worker (APQ/CAPTURE) + capture queue for C11t s2 (job 339851);
  C11n/C13t zips validated in the 2026-10-08 dir.
- 2026-10-07 09:45: cycle 092819: no LB; C11t +0.105 vs C9ae (n=105) → D22 conditional switch of today's release to C11t
  pending L4 timing; packaged C11t zip in today's dir; d9_timing.py; committed last cycle's leftovers (D20/D21, C11n, C13l); locskill eval → built + queued C13t (D23).
- 2026-10-07 08:00: cycle 072819: C9ae confirmed by the rule (n=113, +0.088); found thinking OFF everywhere (D19) → built
  C11t (queued prio 06 with C10); queue reprioritized (C10/C11t, then calibration); Kaggle L4 timing runs C9ae/C10; harness + E1 audits.
- 2026-10-07 07:05: cycle 062819: deduped the c9ae queue (two identical dirs), forensics -> found the cn17 conftest leak (D18),
  quarantined + re-enqueued 3 shards, fixed the worker, resubmitted 3 workers; provisional RELEASE -> C9ae; built + queued C10.
- 2026-10-07 06:00: cycle 052819: harvested partial proxy (C9a +0.095 vs C8), built C9ae, reordered the queue so C9e/C9ae
  pair on s0–s5 before the 11:30 decision, provisional RELEASE -> C9a, D17.
- 2026-10-07 05:30: cycle 042819: harvested the verify job (proxy valid), found the analyzer ctx overflow (D16), built C9e,
  added a 2-GPU a40 worker, px_report.py, provisional RELEASE = C9e.
- 2026-10-07: autopilot installed (ops/autopilot). First cycles should do backlog items 1–2.

## Note from interactive session (2026-10-07 06:00)
- Paired proxy vs C8 s1 at 05:58: C9a 36 vs 29 (n=88), C9e 14 vs 8 (n=26). Fixes target different failures
  (edit malformation vs analyzer context overflow), so built C9ae = C9e + C9a's system.md (submissions/c9ae_combo)
  and enqueued px_c9ae_s1 at prio 05 (front of queue). Release candidate if it is ≥ both C9a and C9e on paired tasks.
