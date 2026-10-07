# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## TODAY'S PUSH (2026-10-07, deadline 12:30 IST): pick the best evaluated submission
- **RELEASE.md PROVISIONAL = C9ae** (zip submission_2026-10-07_c9ae_editfix_analyzercap.zip, identical to submissions/c9ae_combo).
  FINAL RULE (D17 + D18, the ~10:30 work cycle MUST apply it): run `.venv/bin/python ops/queue/px_report.py` and
  `--base c9a`. Use only runs with leak=0. Pick the largest clean paired diff vs C8 among {C9a, C9e, C9ae} with ≥38 pairs
  (C9a needs none). C9ae wins ties within 0.03 if it has fewer ctxErr. If C9ae has < 38 clean pairs, ship C9e
  (+0.131, n=61 clean at 07:00). Rewrite the RELEASE.md table, keeping line 1 `SUBMIT: <zip>`.
- Clean results at 07:00: C8 34/114, C9a 41/114, C9e 27/66, C9ae 10/27. Paired vs C8: C9a +0.061 (n=114, z=1.61),
  C9e +0.131 (n=61, z=2.14), C9ae +0.120 (n=25). C9ae vs C9a +0.080 (n=25).
- **D18 harness bug:** worker 337610 (cn17-dgx) leaked harness conftest.py/pytest.ini into all patches (silent baseline
  `git commit` failure, no git identity). Shards C9ae s1/s2 and C9e s5 moved to results/px_quarantine/ and re-enqueued at prio 05.
  Fixed in ops/slurm/ap_worker.sbatch (GIT_* env + startup `git-commit selftest` line). px_report has a `leak` column, and leak must be 0.
- Queue (ops/queue): 05 = C9ae s1 (s1,s2,s6,s7) + C9e s5 reruns; 10 = C8/C9a s1 s6–s7; 11 = C9e s1 s6–s7; 12 = **C10 s1** (new);
  14 = C9all s1; 15 = C9c; 22 = C9b; 25 = C9d; 30 = anchor + c6a_t5 (calibration); 40 = C8/C9a/C9all/C9ae s2; 41 = C9e s2.
  Workers: `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N --cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch`
  (QoS caps: a40 ≤2 GPU/job & 3 jobs, l40 ≤4/job & 4 jobs, dgx ≤4/job & 4 jobs). Add work: `ops/queue/enqueue.sh <prio> <sub> <run> proxy`.
- Forensics (reports/autopilot/forensics_20261007.md): the remaining C9ae failures are mostly wrong fixes (20/28). Others:
  analyzer repeat-loops (the 20-call cap is often ignored; the sub-agent shares the 100-call budget), shallow early submits,
  and repeated submit_patch calls. No root-agent ctx overflow seen.
- Proxy validity: gold 152/152, empty 0/152 (job 337590). LoRA preflight PASSED (job 337543).

## Running jobs (as of 07:05 IST 2026-10-07)
- ap-worker running with the OLD script (fine; their nodes commit OK, leak=0): 337605 (a40 1), 337608 (a40 2), 337687 (a40 2),
  337593 (l40 1), 337612 (l40 1). New (fixed script), PENDING: 338533 (dgx 4), 338534 (dgx 2), 338535 (l40 2). Total if all run = 15 GPUs.
  CHECK: `grep selftest results/slurm/ap_worker_33853[345].out` must say OK, and px_report leak = 0 for the shards they run.
  If the selftest FAILED, scancel that job and quarantine its shards.

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
1. P0 (tomorrow's release) C10 s1 results vs C9ae on paired tasks (≥38 pairs). If C10 ≥ C9ae, it becomes the 2026-10-08 candidate.
   Then queue C10 s2 + C9ae s2 for a second seed. Next ideas from forensics: analyzer call cap enforced by the harness? (check
   whether agent_tool / sub-agent yaml supports a per-agent max-call limit); "follow the issue even if an existing test asserts
   the old behaviour"; never repeat an edit that returned "identical".
2. P0 Proxy calibration (D11): the anchor + c6a_t5 s1 queue items (prio 30) must run. Pass rule: anchor > c6a_t5, and C8 ≥ anchor.
3. P1 Runtime on the scorer (D9): C9e/C9ae look faster than C8 on proxy, but the hardware is confounded. The next Kaggle L4 check
   should cover the release candidate if there is quota.
4. P1 E1: trajectory capture → D5 filters → LoRA SFT (src/sft/train_lora.py, preflight passed) → LORO evaluation. Use proxy
   repos held out by repo to avoid contamination.
5. P2 Paper track (deadline 2026-11-12): reports/council/paper_plan.md; the user must join the paper competition (D8).
6. P3 kverify-fix3 Kaggle ERROR. Debug only if Kaggle L4 runs are needed.

## Open questions for the user (write here; user reads RELEASE.md / STATE.md)
- Are the submitting account and vedantmoghe on the same Kaggle Team (D14)?
- Joined the paper competition (D8)?

## Journal
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
