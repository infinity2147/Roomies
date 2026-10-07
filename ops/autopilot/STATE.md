# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## TODAY'S PUSH (2026-10-07, deadline 12:30 IST)
- **RELEASE.md PROVISIONAL = C9ae** (zip submission_2026-10-07_c9ae_editfix_analyzercap.zip, = submissions/c9ae_combo); table refreshed 07:35.
  FINAL RULE (D17 + D18, the ~10:30 work cycle MUST apply it): run `.venv/bin/python ops/queue/px_report.py` and
  `--base c9a`. Use only runs with leak=0. Pick the largest clean paired diff vs C8 among {C9a, C9e, C9ae} with ≥38 pairs.
  C9ae wins ties within 0.03 if it has fewer ctxErr. Rewrite the RELEASE.md table, keeping line 1 `SUBMIT: <zip>`.
- Clean at 07:35: C8 38/119, C9a 41/114, C9e 41/101, C9ae 52/127. Paired vs C8: C9ae n=113 +0.088 (z=+2.36), C9e n=101 +0.089
  (z=+1.88), C9a n=114 +0.061. → rule currently selects C9ae.

## Tomorrow (2026-10-08) candidates — paired vs C9ae on proxy s1
- **C10** `submissions/c10_c9ae_plus` (analyzer w/o read_file, no tree reverts, stop after submit, repro asserts issue behaviour).
- **C11t** `submissions/c11t_c9ae_think` (NEW, D19): C9ae + root `include_thoughts: true`. Thinking was OFF in all prior
  submissions (include_thoughts:false forces enable_thinking=False). Rule in D19 (≥+0.03 over ≥60 pairs, min/task ≤1.3× C9ae, L4 timing).
  FIRST CHECK: px_report row c11t_s1 — if err ≈ n (e.g. vLLM rejects `thinking_token_budget`), inspect a trace, fix, re-enqueue.
- If both win: C12 = C10 + thinking (build only after both have ≥60 pairs).

## Queue (ops/queue; items sorted by name)
06 = C10 s1 + C11t s1 (interleaved by shard) → 07 = C8 s7 → 08 = anchor + c6a_t5 s1 (D11 calibration) → 14 C9all → 15 C9c →
20 = C9a/C9e s6–s7 → 22 C9b → 25 C9d → 40/41 = s2 seeds. Workers: `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N
--cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch` (QoS caps: a40 ≤2 GPU/job & 3 jobs, l40 ≤4/job & 4 jobs,
dgx ≤4/job & 4 jobs). Add work: `ops/queue/enqueue.sh <prio> <sub> <run> proxy`. leak must be 0 (D18).

## Running jobs (as of 08:00 IST 2026-10-07)
- ap-worker (old script, nodes commit OK): 337605 (a40 1), 337608 (a40 2), 337687 (a40 2), 337593 (l40 1), 337612 (l40 1).
  PENDING (fixed script): 338533 (dgx 4), 338534 (dgx 2), 338535 (l40 2). Total if all run = 15 GPUs.
  CHECK: `grep selftest results/slurm/ap_worker_33853[345].out` must say OK; else scancel + quarantine its shards.
- Kaggle (vedantmoghe, private, 4×L4 scorer stack, both RUNNING since 07:50): `gemma-rl-eval-c9ae-t30s` and `gemma-rl-eval-c10-t30s`
  = 30 public valid tasks (`--n 30 --seed 7`), concurrency 1 (serial like the scorer). Purpose: D9 L4 mean task time for C9ae/C10.
  Check `.venv/bin/kaggle kernels status vedantmoghe/<slug>`; fetch `kaggle kernels output vedantmoghe/<slug> -p results/kaggle/<slug>`;
  compute mean task time and 150×mean+0.5h. When a slot frees, push C11t the same way (`--run c11t-t30s --n 30 --seed 7 --concurrency 1`).
  Note: the Kaggle dataset gemma-rl-proxy is a stale 69-task build without the proxy test-dep shim — don't use it for proxy scores.

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
0. P0 (today ~10:30–11:30) Finalize RELEASE.md by the rule in the push section.
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
