# Autopilot STATE (single source of truth between cycles; newest first in Journal)

## Champion
C8 `submissions/c8_anchorplus` (zip: submission_c8_anchorplus.zip) — public LB 0.13 (2026-10-06).

## Running jobs
(none)

## Environment status (2026-10-07)
- Prajna: .venv, .venv-eval built on login; .venv-harness (vLLM 0.19.1 + Kaggle Gemma-4 LoRA build, torch 2.10 cu128)
  verified on a DGX A100 node (job 337488: `server env ok ... gpu True`, `lora-capable: True`).
- Model weights: see shared-gpu-serving-setup memory / scripts/serve_vllm.sh for the local path (gemma-4-31b-it-qat-w4a16-ct).
- NOT yet built: a SLURM job that serves vLLM on a DGX node and runs the harness eval there (old box used PP 52/8 on
  port 8011 via scripts/serve_vllm.sh + scripts/eval_submission.sh).
- Kaggle: kverify-fix3 (CPU gold/empty verification with sandbox fix v3) ended in ERROR with an empty log; cause not
  investigated. Dataset vedantmoghe/gemma-rl-proxy is `ready`. results/chain_master.sh (old machine) never got past the gate.

## Backlog (prioritized; re-prioritize every cycle)
1. P0 Prajna eval pipeline: ops/slurm/ap_eval.sbatch = start vLLM (scorer-identical: TP=4, max_model_len 32768,
   same flags as the Kaggle scorer) on 4 A100s + run scripts/eval_submission.sh on a task set + write a summary.
   Allow 2 evals per 8-GPU node. Verify the sandbox (no internet on DGX: tests must not need pip) with gold/empty
   patches on public tasks and on the proxy tasks first (CPU job: gold must pass, empty must fail).
2. P0 Proxy calibration: anchor_public vs c6a_t5 vs c8_anchorplus, ≥2 seeds each, on the proxy benchmark (+ the 107
   public valid tasks). Pass rule: anchor > c6a_t5 and C8 ≥ anchor (matches LB). Decision memo either way.
3. P1 Debug kverify-fix3 ERROR (Kaggle) only if Kaggle runs are still needed for L4 runtime checks.
4. P1 C9 = C8 + one change at a time (each must be a separate candidate so LB results are interpretable):
   a) edit robustness when new_string contains ``` fences (trajectory_forensics: ~600 malformed edit calls),
   b) early first edit / anti-loop guard, c) brute-force property checks over long hand-simulation (D3.1).
5. P1 E1: trajectory capture with C8 on proxy + public train tasks → D5 filters → LoRA SFT (src/sft/train_lora.py,
   `--preflight` first, 1×A100-80GB) → LORO evaluation → candidate C8+LoRA.
6. P2 Paper track (deadline 2026-11-12): reports/council/paper_plan.md; RL re-ranking for fault localization as the
   research contribution; user must join the paper competition on Kaggle (D8).

## Open questions for the user (write here; user reads RELEASE.md / STATE.md)
- Are the submitting account and vedantmoghe on the same Kaggle Team (D14)?
- Joined the paper competition (D8)?

## Journal
- 2026-10-07: autopilot installed (ops/autopilot). First cycles should do backlog items 1–2.
