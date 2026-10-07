# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## TODAY'S PUSH (2026-10-07, deadline 12:30 IST) — RELEASE = C9ae (D24)
- At 10:45 the L4 timing kernels (`gemma-rl-eval-c11t-t30s`, `-c9ae-t30s`) were still RUNNING (serial since 08:30, est. done ~14:30).
  **11:28 cycle:** `.venv/bin/kaggle kernels status vedantmoghe/gemma-rl-eval-c11t-t30s`; only if it is COMPLETE before 12:00 and passes D22,
  change today's RELEASE.md line 1 to `SUBMIT: submission_2026-10-07_c11t_c9ae_think.zip`. Otherwise do nothing; C9ae ships.
- px s1 FINAL (10:40, leak 0): C11t vs C9ae n=152 +0.112 (24W/7L z+3.05); time 1.25× C9ae on same GPU types (median per-task 1.54×).
  C10 vs C9ae n=122 +0.000 → C10 DROPPED (D24). C9ae vs C8 n=133 +0.083.

## Tomorrow (2026-10-08): submissions/daily/2026-10-08/RELEASE.md DRAFT. Planned pick = C11t once the L4 kernel passes D9 (D24)
- When the kernels are COMPLETE: `.venv/bin/kaggle kernels output vedantmoghe/gemma-rl-eval-c11t-t30s -p results/kaggle/c11t-t30s` (and c9ae →
  results/kaggle/c9ae-t30s), then `.venv/bin/python scripts/kaggle_eval/d9_timing.py c11t-t30s c9ae-t30s`. If it PASSES, set the 2026-10-08 line 1 to
  `SUBMIT: submission_2026-10-08_c11t_c9ae_think.zip`. If it FAILS, keep C9ae and look at C11n (faster) as the thinking candidate.
- After the kernels free up, launch an L4 timing kernel for C11n or C13t (whichever leads vs C11t): `scripts/kaggle_eval/make_kernel.py` (see D20, pinned image).
- C11n `submissions/c11n_think_noanalyzer` (D21) and C13t `submissions/c13t_c11t_locskill` (D23) are running at prio 07, paired vs C11t
  (n=14 / 6 so far). Zips are validated in the 2026-10-08 dir. Upgrade over C11t only by the D21/D23 rules (≥ 60 pairs).
- If the 2026-10-07 LB for C9ae is in by then, log it (lb_scores.tsv) and interpret (vs C8 0.13; noise ±1–2 tasks ≈ ±0.03).

## Queue (ops/queue; items sorted by name)
07 C11n s1 + C13t s1 (s0–s1 running) + C8 s7 → 08 anchor/c6a_t5 s1 (D11 calibration) + C9ae s2 → 14 C9all → 15 C9c → 20 C9a/C9e s6–s7 → 22 C9b
→ 25 C9d → 40/41 s2 seeds of old candidates (low value; delete if the GPUs are needed). C10 s4/s5/s7 still running (let them finish; no more C10).
**Capture queue ops/queue_cap** (NEW): 08 C11t s2 s0–s7, run by worker job `ap-worker-cap` (sbatch `--export=ALL,APQ=ops/queue_cap,CAPTURE=1`).
It writes results/px/px_c11t_s2 (px_report picks it up) and results/capture/<job>_<slot>.jsonl (all LLM calls, with reasoning) plus
<tag>.items.jsonl (item start times, used to map calls to shards). Only new workers support APQ/CAPTURE; old workers read only ops/queue.
Workers: `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N --cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch`
(QoS caps: a40 ≤2 GPU/job & 3 jobs, l40 ≤4/job & 4 jobs, dgx ≤4/job & 4 jobs). Add work: `ops/queue/enqueue.sh <prio> <sub> <run> proxy`. leak must be 0 (D18).

## Running jobs (as of 10:45 IST 2026-10-07)
- ap-worker RUNNING: 337605 (a40 1), 337608 (a40 2), 337687 (a40 2), 337593 (l40 1), 337612 (l40 1) = 7 GPUs. 10 h limit → they END ~14:15–14:30 IST.
  **The next cycle after 14:30 must resubmit workers** (keep about 8–15 GPUs) or the main queue stalls.
- PENDING: 338533 (dgx 4), 338535 (l40 2), 339851 ap-worker-cap (l40 2, capture queue). 338534 (dgx 2) was cancelled to make room for the capture worker.
  When they start: `grep selftest results/slurm/ap_worker_<id>.out` must say OK. For 339851, also check that the log has
  "capture proxy" lines and results/capture/339851_*.jsonl is growing. If the capture shards fail (ops/queue_cap/failed), move the items
  back to ops/queue/pending (as plain runs) and debug the capture setup offline.
- Kaggle (vedantmoghe, private, pinned image D20): `gemma-rl-eval-c9ae-t30s`, `gemma-rl-eval-c11t-t30s` RUNNING since 08:30 IST (2 of 2 slots).

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
0. P0 11:28 cycle: D22 last check (see TODAY). Afternoon: fetch the L4 kernels → d9_timing → finalize the 2026-10-08 line 1 (C11t or C9ae).
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
