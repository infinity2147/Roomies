# Council Decisions — round 1 (2026-10-02, evening)

Inputs: `localization_headroom.md`, `trajectory_forensics.md` (+ `trajectory_table.csv`), `methodology_review.md`,
`paper_plan.md` (+ `references.bib`). Training plan pending. Each decision lists the evidence I (lead) re-verified.

## Pre-registered rules → outcomes
| Q | Rule (AGENDA.md) | Result | Decision |
|---|---|---|---|
| Q1 | ≥60% of stochastic failures reach a gold file → repair-side + SFT | 149/171 failed runs read the gold file (87%); wrong location primary in 12/171 | **Repair-side interventions + SFT are the competition levers.** |
| Q2 | Phase D as competition lever only if RL-addressable ≥15% AND file misses ≥20% of failures | graph-only headroom ≤6/117 (5%); wrong location 25/240 task-runs (10%) | **Phase D (RL traversal) is no-go for the competition.** Paper: re-scoped to *learned re-ranking*, gated (below). |
| Q4 | any critical issue blocks dependent decisions | 2 critical (E1, E2) | **All Kaggle reference/SFT runs blocked until the Kaggle environment is fixed and verified.** |
| Q5 | choose framing at P11 | strategist recommends fallback framing; RL gate ~15–20% | **Primary paper framing = "localization is not the bottleneck; consistency is".** |

## Decisions and actions

**D1 — Fix the Kaggle evaluation environment (critical E1/E2). Status: in progress.**
- Evidence (re-verified): `requests_7309` hidden tests import `/usr/local/lib/python3.12/dist-packages/requests` (test log); src-layout repos (requests, httpx) never import the patched workspace ⇒ 10/107 valid tasks (9.3%) unsolvable in every Kaggle run so far.
- Action: sandbox fix (`scripts/kaggle_eval/sandbox_fix.py`: editable install + workspace-first `.pth`) inserted into the eval kernel template; CPU-only A/B verification kernels (`kverify-fix` vs `kverify-nofix`, gold vs empty on all 129 tasks) running on Kaggle.
- Gate: re-launch C6a×4 / B0×2 only when `kverify-fix` shows gold-pass ≥ local valid set on requests/httpx. Queue stopped before any buggy run was pushed (run 1 + LoRA smoke were already queued; run 1 remains valid for the 97 non-src tasks).

**D2 — Localization: stop competition work; paper re-scoped.**
- Headroom over BM25 is re-ranking headroom (34/117 tasks have gold at BM25 rank 6–50), not graph headroom (≤6/117); the graph is sparse (median degree 1–2). Cheap fusion gives ΔMRR +0.032 [−0.006, +0.073] (n.s.).
- Paper gate (Oct 22): learned re-ranker trained on ≥150 synthetic issues + 66 mined tasks (≥10 repos) must reach ΔMRR ≥ +0.05 with CI excluding 0 on held-out real repos. Otherwise the localization section reports the diagnostic results only.

**D3 — New scaffold C7 targeting the measured failure modes (new tag `scaffold-v2`; C6a stays frozen until C7 wins).**
Ranked by the forensics' estimated gain (each ≤ one standard error alone; combined +3–4 tasks/30):
1. Time box: first source edit by ~40% of the budget; brute-force checks in /tmp instead of long reasoning.
2. Edit robustness: 634+ `edit_file` calls lost `old_string` because argument values were split into bogus keys (e.g. keys `"if prefix"`, `"column = Column(...)"` — re-verified in traces). Needs a root-cause study first (D6) before choosing the workaround.
3. Anti-loop: no repeating an identical call; consider temperature 0.7 (untested; C6a issues duplicate calls in 19/30 runs, 56% of calls).
4. Reproduce-before-edit: the repro must fail before editing.
5. Pre-submit import check (7 submitted patches failed to import) — extend `check.py`.
6. Scratch files: `write_file` to /tmp is blocked (144 errors, re-verified) → instruct `run_command` heredoc to /tmp; `check.py` already deletes scratch files in /workspace.
- Evaluate C7 vs C6a only after D1, on the same tasks, ≥2 runs each, paired comparison.

**D4 — Measurement fixes.**
- `tool_err_rate` counts benign non-zero exits (grep no-match: 376/446 C6a "errors"); redefine as tool-protocol errors (invalid arguments / unknown tool / FileEditError).
- pass@8 = 0.467 mixes 8 configs ⇒ a best-of-configs ceiling. Single-policy pass@k comes from C6a×4 (after D1).
- Paired comparisons: use per-task success counts across runs (paired bootstrap), not majority-vote McNemar (needs ~8 net tasks at n=30).
- Concurrency confound: Kaggle evals at concurrency 4 slow each task; time-based conclusions need a concurrency-1 timing run.

**D5 — SFT data protocol.**
- Selection: resolved ∧ clean patch (no scratch/test/config files) ∧ no test edit in trajectory ∧ no repetition loop ∧ explicit submit; mask (don't drop) malformed tool-call turns; cap 2 trajectories/task (4 always-solved tasks supply 46% of successes).
- Capture must carry explicit task ids (prefix-matching collides 28× once mined tasks are added).

**D6 — Next council round (to commission).**
- Tool-call robustness study (CPU): reproduce the argument-splitting failure with vLLM's Gemma-4 tool parser on captured model outputs; find the trigger (e.g. `name: value` lines inside string values) and design the most robust edit path.
- C7 implementation + local smoke; Kaggle A/B after D1.

**Addendum (never-solved deep dive, 8 tasks × 8 configs):**
- httpx_3672: 6/7 agent patches pass all 24 hidden tests when run with `PYTHONPATH=src` ⇒ environment failure, corroborates D1.
- Edit-call malformation is triggered by triple-backtick fences inside `new_string` (fastapi `Doc()` docstrings): fastapi_13713 5/8 runs, fastapi_14953 c6a 27 in a row, httpx_3672 c3 32 ⇒ D6 study starts from this trigger.
- rich_3506/3521: a brute-force property check over all split positions finds a one-line fix (`pos = 0`) that passes all hidden tests (52/52, 59/59); runs instead hand-simulated cell widths for minutes ⇒ supports D3.1 (brute-force checks over long reasoning).
- Spec-gap tasks (fastapi_13713 `openapi_external_docs`, fastapi_14953 new docs module, fastapi_15800 empty PR body) are not fixable by the scaffold; treat them as the ceiling, not as targets.

**D7 — Corrections to the technical report.** Per-run pass@1 range is 0.233–0.333 (not 0.29–0.33); run-to-run std 0.029; locator on the 107 valid tasks: file hit@1 0.453, hit@3 0.651; "pass@8" must be labelled best-of-8-configs.

**D9 — Runtime safety (new, after C4 "Notebook Timeout" >12 h).**
- Projection from measured durations (Kaggle, conc 4 ⇒ pessimistic): C4 14.1 h / 120 tasks (matches the timeout); C6a uncapped 9.4 h (11.7 h if 150 tasks); C6a with a 5-min cap 8.5 h (10.5 h at 150). 7/9 C6a solves finished in <4 min, so the cap costs ≤1 task/30.
- Decision: next submission = `submission_c6a_t5.zip` (frozen C6a prompt, `max_time_minutes: 5`). Every future candidate must pass a projected-runtime check: 150 × mean task time + 0.5 h ≤ 11 h.
- Use the completion time of c6a_t5 as a signal of hidden-set size / serial speed.

**D10 — Training (Q3 closed).** Rule met: tiny end-to-end test passes (re-run by lead: PASS; logit diff vs vLLM semantics 1.9e-5 with the global-layer k→v LoRA copy, 15.3 without).
- Method: train LoRA on the frozen int4 QAT weights unpacked on the fly (bit-identical to what vLLM serves) — no bf16-base mismatch.
- Bug found and fixed: global-attention layers have no v_proj (V = K); vLLM copies only base K into V, so every exported adapter must duplicate k_proj LoRA into v_proj (`train_lora.py` exporter does; `--verify` checks it).
- Compute: 1×80 GB GPU (H100 ≈2–3 h, A100 ≈6–9 h per 300×20k×2-epoch run; 3 LORO folds + final ≈3×). Local A5000s and Kaggle GPUs cannot train it. First step on rented hardware: `--preflight` (512-dim global-head attention at 32k) and a vLLM log-prob parity check.
- E1 starts when: (a) hardware is available, (b) D1 Kaggle env fixed, (c) C6a×4 capture runs produce ≥30 clean successful trajectories (D5 filters).

**D8 — Needs the user.** Join the paper competition `gemma-4-developer-agent-paper` on Kaggle (account shows not entered). Arrange training hardware (pending training plan).

# Round 2 (2026-10-05) — leaderboard reality check

**Evidence.** C6a_t5 scored **0.06** on the public LB (vs ~0.20 on our 107 public-repo valid tasks: C6a run 1 = 21/107; 21/97 excluding the 10 env-broken src-layout tasks). The public "anchor" bundle (thinking on, read-only analyzer sub-agent, no eval_config) scored 0.12. Harness source (`swegemma/harness/sample_verification.py`) describes the benchmark as "all 13 repositories" with only 4 public ⇒ the hidden set very likely contains ~9 unseen repos. LoRA smoke on Kaggle scorer stack: adapter served for 283/283 agent steps (P3 closed).

**D11 — Our offline metric is invalid for model selection until calibrated.** All C-series choices were made on 4 public repos. New primary metric: a proxy benchmark from likely hidden repos (hidden-set analyst, in progress); calibration requirement: the offline metric must rank anchor (0.12) > C6a_t5 (0.06).
**D12 — Calibration runs on Kaggle GPUs** (gated on kverify-fix2 env check): anchor_public vs C6a_t5 vs C8 on the 107 public valid tasks now; repeat on the proxy benchmark when built.
**D13 — Next submission = C8 (anchor + 2 measured hygiene fixes)**: tests whether thinking-on + analyzer sub-agent generalizes better; no eval_config (anchor proved this fits 12 h).
**D14 — Account hygiene**: eval kernels run on `vedantmoghe`; submissions come from another account — both must be on the same Kaggle Team (rules §3.5).

# 2026-10-07 — C8 result
**C8 (public anchor + 2 measured hygiene fixes: /tmp via heredoc, revert test edits) scored LB 0.13** (vs C6a_t5 0.06, anchor 0.12). Confirms D11: thinking-on + read-only analyzer sub-agent generalizes to the hidden repos; our public-repo-tuned C6a did not. C8 is the new base (successor to the frozen C6a for SFT data collection once proxy calibration confirms).
Compute: moving to IITB Prajna (DGX/A40/L40 SLURM partitions) — enables scorer-identical TP=4 serving, fast eval, and E1 LoRA training. Migration: scripts/migrate/{push_to_prajna.sh, setup_env.sh}.

# 2026-10-07 04:30–05:30 — autopilot work cycle
**D15 — Prajna proxy eval is valid as a harness.** Gold/empty check on Prajna (job ap-verify 337590): gold 152/152 pass, empty 0/152, so all 152 proxy tasks count. The eval queue (ops/queue, ap-worker jobs, TP=1 per GPU, max_model_len 32768) is the evaluation pipeline. Report: `ops/queue/px_report.py`.
**D16 — New failure mode: the analyzer sub-agent overflows its context and kills the task.** The `code_analyzer` sub-agent (anchor/C8/C9*) runs in its own session with no event compaction. On the first 13 proxy tasks (C8 s1 + C9a s1), 4 tasks (31%) ended in `ContextWindowExceededError` (24.6k prompt + 8192 max_output > 32768). In each case the last caller was code_analyzer, after 19–83 calls (one was a loop: 12 identical `read_file` calls with a malformed `start_line"` key). The task then errors with an empty patch. Kaggle C6a runs (no sub-agent) never hit this; the root agent stays ≤ 18.8k because it is compacted. The same harness code runs on the scorer, so this very likely also costs us hidden tasks.
Action: **C9e = C8 + an analyzer context cap** (one conceptual change, sub-agent only): analyzer-specific sampling (max_output_tokens 4096, thinking_budget 2048 → ~28.6k input headroom) + a prompt budget (≤20 calls, ≤60-line reads, no repeated identical calls, `sed -n` fallback, answer with low confidence at the cap). It is queued at prio 11 (paired with C8 s1) and prio 41 (s2).
Release rule for 2026-10-07: C9e if its paired proxy shards vs C8 show (a) fewer context errors and (b) pass-rate diff ≥ 0. Otherwise C9a if its paired diff ≥ 0. Otherwise C9e anyway, as the most informative one-change experiment (it targets a hard failure; its downside is bounded to analyzer quality).
