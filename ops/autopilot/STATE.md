# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## TODAY'S PUSH (2026-10-07, deadline 12:30 IST)
- **RELEASE.md PROVISIONAL = C9ae**; **switch to C11t by D22** (zip submission_2026-10-07_c11t_c9ae_think.zip, already validated
  in the daily dir). 10:28/11:28 cycles: `.venv/bin/kaggle kernels status vedantmoghe/gemma-rl-eval-c11t-t30s` (and c9ae-t30s);
  when COMPLETE: `.venv/bin/kaggle kernels output vedantmoghe/gemma-rl-eval-c11t-t30s -p results/kaggle/c11t-t30s` (same for c9ae),
  then `.venv/bin/python scripts/kaggle_eval/d9_timing.py c11t-t30s c9ae-t30s`. SUBMIT C11t if ≥25 tasks and (150×mean+0.5 h ≤ 11 h,
  or paired time ratio ≤ 1.05) AND px_report `--base c9ae` still shows C11t ≥ +0.03. Else keep C9ae. Rewrite RELEASE.md line 1 + table.
- px at 09:40 (clean): C11t vs C9ae n=105 +0.105 (16W/5L z+2.40); vs C8 n=100 +0.200. C9ae vs C8 n=133 +0.083. C10 vs C9ae n=77 +0.039.
  Among C9 variants the D17 rule still picks C9ae.

## Tomorrow (2026-10-08) — submissions/daily/2026-10-08/RELEASE.md is a DRAFT (C9ae default, C11t if D19 gate)
- If C11t is submitted today, tomorrow's question is C11n (no analyzer, D21) vs C11t, and C12 = C10 changes + thinking.
- **C10** `submissions/c10_c9ae_plus`: +0.039 vs C9ae (n=77) — weak; fold its changes into C12 = C11t + C10 only if C11n loses.
- **C11n** `submissions/c11n_think_noanalyzer` queued prio 07 (paired vs C11t, rule in D21).
- **C13l** `submissions/c13l_c9ae_locskill` (repo-locate skill in the analyzer; built last cycle, not queued). Offline accuracy eval
  by a subagent this cycle → reports/autopilot/locskill_eval_20261007.md.

## Queue (ops/queue; items sorted by name)
05 C11t s1 (running, last shards) → 06 C10 s6–s7 → 07 C11n s1 + C8 s7 → 08 anchor/c6a_t5 s1 (D11 calibration) + C11t/C9ae s2 →
14 C9all → 15 C9c → 20 C9a/C9e s6–s7 → 22 C9b → 25 C9d → 40/41 s2 seeds of old candidates (low value; consider deleting).
Workers: `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N --cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch`
(QoS caps: a40 ≤2 GPU/job & 3 jobs, l40 ≤4/job & 4 jobs, dgx ≤4/job & 4 jobs). Add work: `ops/queue/enqueue.sh <prio> <sub> <run> proxy`. leak must be 0 (D18).

## Running jobs (as of 09:45 IST 2026-10-07)
- ap-worker RUNNING: 337605 (a40 1), 337608 (a40 2), 337687 (a40 2), 337593 (l40 1), 337612 (l40 1) = 7 GPUs.
  PENDING (fixed script): 338533 (dgx 4), 338534 (dgx 2), 338535 (l40 2). Total if all run = 15 GPUs.
  CHECK when they start: `grep selftest results/slurm/ap_worker_33853[345].out` must say OK; else scancel + quarantine its shards.
- Kaggle (vedantmoghe, private, pinned image D20): `gemma-rl-eval-c9ae-t30s` and `gemma-rl-eval-c11t-t30s` RUNNING since 08:30 IST
  (30 public valid tasks, `--n 30 --seed 7`, concurrency 1). `gemma-rl-eval-c10-t30s` = old ERROR (pre-pin); relaunch C10 or C11n
  when a slot frees (C11n first if it is ahead by then).

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
0. P0 (today 10:28 + 11:28 cycles) Apply D22: fetch the C11t/C9ae L4 kernels, d9_timing.py, finalize RELEASE.md line 1.
1. P0 (tomorrow) Harvest C10 and C11t s1 vs C9ae (paired, ≥38/60 pairs); Kaggle L4 timings; pick the 2026-10-08 release
   (write submissions/daily/2026-10-08/RELEASE.md). Then queue s2 for the winner(s) + C9ae s2 (prio 40 exists).
2. P0 Proxy calibration (D11): anchor + c6a_t5 s1 now at prio 08. Pass rule: anchor > c6a_t5, and C8 ≥ anchor.
3. P1 Kaggle L4 timing for C11t (thinking adds tokens; D9 risk) as soon as a Kaggle slot frees.
4. P1 Localization skill script (not budget-gated) to replace analyzer grep loops; or analyzer via `sub_agents` transfer (compaction).
5. P1 E1: capture-enabled seeds (capture_proxy) of the D19 winner → build_dataset (split analyzer sessions) → 4-fold LORO LoRA.
6. P2 Paper track (deadline 2026-11-12): reports/council/paper_plan.md; the user must join the paper competition (D8).
7. P3 kverify-fix3 Kaggle ERROR / stale Kaggle proxy dataset (rebuild with the 152-task set + shim only if L4 proxy scores needed).

## Open questions for the user (write here; user reads RELEASE.md / STATE.md)
- Are the submitting account and vedantmoghe on the same Kaggle Team (D14)?
- Joined the paper competition (D8)?

## Journal
- 2026-10-07 09:45: cycle 092819: no LB; C11t +0.105 vs C9ae (n=105) → D22 conditional switch of today's release to C11t
  pending L4 timing; packaged C11t zip in today's dir; d9_timing.py; committed last cycle's leftovers (D20/D21, C11n, C13l); locskill eval.
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
