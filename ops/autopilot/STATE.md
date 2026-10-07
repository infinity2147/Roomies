# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## TODAY'S PUSH (2026-10-07, deadline 12:30 IST): pick the best evaluated submission
- GPU eval queue (ops/queue): workers = `sbatch -p <a40|l40|dgx> --qos=<same> --gres=gpu:N --cpus-per-task=$((12*N)) --mem=$((80*N))G ops/slurm/ap_worker.sbatch`
  (QoS caps: a40 ≤2 GPU/job & 3 running jobs, l40 ≤4/job & 4 jobs, dgx ≤4/job & 4 jobs). One vLLM (TP=1) per GPU,
  each slot pulls items from ops/queue/pending (name <prio>_<shard>_<run>), results in results/px/<run>/<shard>/.
  Add work: `ops/queue/enqueue.sh <prio> <submission_dir> <run> proxy` (8 stratified shards × 19 = 152 proxy tasks).
  A40/L40 nodes are Rocky 8: works because vllm._moe_C import is optional and cryptography was swapped to manylinux_2_28.
- **Queue reordered 05:45 (D17):** 05 = C9e s1 shards s0–s5, 06 = C9ae s1 s0–s5 (C9ae = C8+C9a+C9e, submissions/c9ae_editfix_analyzercap),
  then 10 = C8/C9a s1 s6–s7, 11 = C9e/C9ae s1 s6–s7. Original queue: 10 = C8 s1 + C9a s1, 11 = C9e s1, 12 = C9all s1, 15 = C9c s1, 22 = C9b s1, 25 = C9d s1,
  30 = anchor s1 + c6a_t5 s1 (calibration), 40 = C8/C9a/C9all s2, 41 = C9e s2. (C9c/C9d/C9all were built and
  queued ~04:24 before this cycle: c9c = early first edit + brute-force checks, c9d = import check before submit,
  c9all = c9a+b+c+d bundle.)
- Proxy validity: Prajna gold/empty check DONE (job 337590): gold 152/152, empty 0/152 -> all 152 tasks count.
- Report: `.venv/bin/python ops/queue/px_report.py [--done-only]` (per-run pass/ctxErr/err/empty + paired vs c8).
- **D16 finding:** ~31% of the first 13 proxy tasks died with ContextWindowExceededError inside the code_analyzer
  sub-agent (no compaction in sub-agent sessions). C9e = C8 + analyzer context cap built & queued.
- **Results at 05:40:** C8 s1 22/77 (0.286), C9a s1 25/65 (0.385). Paired C9a−C8 = +0.095 (n=63, 7W/1L, z=+2.12).
  ctxErr: C8 10/77, C9a 9. 2 tasks (click_3704, jinja_1984) fail in both runs with test_patch "can't find file"
  (the agent deleted a test file; a candidate for a C9f fix: only `rm` files that `git status` lists as `??`).
- **RELEASE.md is now PROVISIONAL = C9a (D17 supersedes the D16 rule below).** Final rule: largest paired diff vs C8
  among {C9a, C9e, C9ae} (C9e/C9ae need ≥38 pairs; C9ae wins ties within 0.03 of C9a if it has fewer ctxErr); else C9a.
  Update the table in RELEASE.md, keep line 1 `SUBMIT: <zip>`. All three zips are in submissions/daily/2026-10-07/.
- (superseded) RELEASE.md (SUBMIT line) was PROVISIONAL = C9e. NOTE: the daemon skips the release cycle because RELEASE.md exists,
  so the work cycle running at/after ~10:30 IST MUST finalize it, per the D16 rule: C9e if its paired shards vs C8 show
  fewer ctx errors and diff ≥ 0; else C9a if diff ≥ 0; else C9e anyway (most informative). Put the evidence table
  (px_report output) into RELEASE.md and keep line 1 `SUBMIT: <zip>`.
- Also keep GPUs busy: if the queue runs dry, enqueue more seeds / new one-change candidates (anti-loop guard,
  brute-force checks, early first edit) built from C8.
- LoRA preflight PASSED on A100-80GB (job 337543): 32k seq, peak 61.8 GiB, ~110 tok/s -> E1 training is feasible on 1 GPU.

## Running jobs (as of 06:00 IST 2026-10-07; unchanged since 05:30)
- ap-worker (ops/slurm/ap_worker.sbatch, all pull from ops/queue/pending; logs results/slurm/ap_worker_<id>.out):
  running 337605 (a40 1 GPU), 337608 (a40 2), 337687 (a40 2), 337593 (l40 1), 337612 (l40 1);
  pending 337609 (dgx 4), 337610 (dgx 2), 337611 (l40 2). Total if all start = 15 GPUs (cap 16).
  Workers exit when the queue is empty (time limit 10 h). Check: ls ops/queue/{running,done,failed}; failed items
  -> inspect results/px/<run>/<shard>/run_eval.log and re-enqueue by moving the item back to pending/.

## Environment status (2026-10-07)
- Prajna: .venv, .venv-eval built on login; .venv-harness (vLLM 0.19.1 + Kaggle Gemma-4 LoRA build, torch 2.10 cu128)
  verified on a DGX A100 node (job 337488: `server env ok ... gpu True`, `lora-capable: True`).
- Model weights: see shared-gpu-serving-setup memory / scripts/serve_vllm.sh for the local path (gemma-4-31b-it-qat-w4a16-ct).
- NOT yet built: a SLURM job that serves vLLM on a DGX node and runs the harness eval there (old box used PP 52/8 on
  port 8011 via scripts/serve_vllm.sh + scripts/eval_submission.sh).
- Kaggle: kverify-fix3 (CPU gold/empty verification with sandbox fix v3) ended in ERROR with an empty log; cause not
  investigated. Dataset vedantmoghe/gemma-rl-proxy is `ready`. results/chain_master.sh (old machine) never got past the gate.

## Backlog (prioritized; re-prioritize every cycle)
0. P0 (today) Finalize RELEASE.md by ~11:30 (see the push section). Then plan C10 = C9e + the C9a-d changes that win
   their paired tests (≥2 seeds). Check whether root-agent ctx errors also occur (px_report ctxErr after C9e) and
   whether other analyzer pathologies remain (malformed tool-arg keys such as `start_line"`).
1. P0 Prajna eval pipeline: ops/slurm/ap_eval.sbatch = start vLLM (scorer-identical: TP=4, max_model_len 32768,
   same flags as the Kaggle scorer) on 4 A100s + run scripts/eval_submission.sh on a task set + write a summary.
   Allow 2 evals per 8-GPU node. Verify the sandbox (no internet on DGX: tests must not need pip) with gold/empty
   patches on public tasks and on the proxy tasks first (CPU job: gold must pass, empty must fail).
2. P0 Proxy calibration: anchor_public vs c6a_t5 vs c8_anchorplus, ≥2 seeds each, on the proxy benchmark (+ the 107
   public valid tasks). Pass rule: anchor > c6a_t5 and C8 ≥ anchor (matches LB). Decision memo either way.
3. P1 Debug kverify-fix3 ERROR (Kaggle) only if Kaggle runs are still needed for L4 runtime checks.
4. P1 (in progress: C9a-e + C9all queued) C9 = C8 + one change at a time (each must be a separate candidate so LB results are interpretable):
   a) edit robustness when new_string contains ``` fences (trajectory_forensics: ~600 malformed edit calls),
   b) early first edit / anti-loop guard, c) brute-force property checks over long hand-simulation (D3.1).
   f) NEW: test-file deletion guard (2/152 proxy tasks lose to test_patch "can't find file"); build after the release.
5. P1 E1: trajectory capture with C8 on proxy + public train tasks → D5 filters → LoRA SFT (src/sft/train_lora.py,
   `--preflight` first, 1×A100-80GB) → LORO evaluation → candidate C8+LoRA.
6. P2 Paper track (deadline 2026-11-12): reports/council/paper_plan.md; RL re-ranking for fault localization as the
   research contribution; user must join the paper competition on Kaggle (D8).

## Open questions for the user (write here; user reads RELEASE.md / STATE.md)
- Are the submitting account and vedantmoghe on the same Kaggle Team (D14)?
- Joined the paper competition (D8)?

## Journal
- 2026-10-07 06:00: cycle 052819: harvested partial proxy (C9a +0.095 vs C8), built C9ae, reordered the queue so C9e/C9ae
  pair on s0–s5 before the 11:30 decision, provisional RELEASE -> C9a, D17.
- 2026-10-07 05:30: cycle 042819: harvested the verify job (proxy valid), found the analyzer ctx overflow (D16), built C9e,
  added a 2-GPU a40 worker, px_report.py, provisional RELEASE = C9e.
- 2026-10-07: autopilot installed (ops/autopilot). First cycles should do backlog items 1–2.

## Note from interactive session (2026-10-07 06:00)
- Paired proxy vs C8 s1 at 05:58: C9a 36 vs 29 (n=88), C9e 14 vs 8 (n=26). Fixes target different failures
  (edit malformation vs analyzer context overflow), so built C9ae = C9e + C9a's system.md (submissions/c9ae_combo)
  and enqueued px_c9ae_s1 at prio 05 (front of queue). Release candidate if it is ≥ both C9a and C9e on paired tasks.
