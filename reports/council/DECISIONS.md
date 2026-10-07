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

# 2026-10-07 05:30–06:00 — autopilot work cycle
**Evidence.** Proxy s1, partial (px_report 05:40): C8 22/77 (0.286), C9a 25/65 (0.385). Paired C9a vs C8: n=63, diff **+0.095**, 7 wins / 1 loss, sign-z +2.12 (above the ~0.03 run-to-run noise; one seed so far). Context-overflow errors over more tasks: C8 10/77 (13%), C9a 9/~70. That is lower than the 31% seen on the first 13 tasks, but it is still the largest error class. Other losses: 2+2 hit the 100-call budget, and 2 tasks (click_3704, jinja_1984) fail for both runs with "Failed to apply test_patch: can't find file". The agent deleted or moved an existing test file. This is a candidate for a later one-change fix.
**D17 — Today's release rule supersedes the D16 rule.** C9a and C9e touch disjoint files (root system.md vs analyzer prompt/sampling). We built **C9ae = C8 + C9a + C9e** (`submissions/c9ae_editfix_analyzercap`, validated) and moved the queue so C9e s1 (prio 05) and C9ae s1 (prio 06) run on shards s0–s5 before the C8/C9a s6–s7 items. The provisional SUBMIT is now **C9a**, the only candidate with significant evidence. The final cycle (~10:30–11:30 IST) picks the candidate with the largest paired diff vs C8 among {C9a, C9e, C9ae}, using these conditions:
- C9e or C9ae needs ≥ 38 pairs; otherwise it cannot be chosen.
- C9ae wins ties within 0.03 of C9a if its ctxErr count is lower, because it combines two independently motivated fixes.
- If nothing reaches 38 pairs, ship C9a.
We drop the one-change-per-LB rule for today. Score is the mission, and the proxy (16 unseen repos) now supplies the attribution evidence.

# 2026-10-07 06:30–07:30 — autopilot work cycle
**Evidence.** Forensics (reports/autopilot/forensics_20261007.md): on worker job 337610 (cn17-dgx), every patch included the harness's own `conftest.py`/`pytest.ini`. The harness's baseline `git commit` fails silently there, most likely because git has no identity on that node. No other node's patches show this (px_report `leak` column). Affected shards: C9ae s1/s2 and C9e s5. In jinja_1984 the agent ran `git checkout -- .` and lost its fix. We moved those shards to results/px_quarantine/ and re-enqueued them. Clean paired results vs C8: C9e n=61 **+0.131** (11W/3L, z=+2.14); C9a n=114 +0.061 (13W/6L); C9ae n=25 +0.120 (4W/1L), which is +0.080 vs C9a.
**D18 — The harness needs a git identity on every worker, and contaminated data never counts.** ap_worker.sbatch now exports GIT_AUTHOR/COMMITTER and logs a `git-commit selftest` at startup. We cancelled 337609/337610/337611 and resubmitted them as 338533 (dgx 4), 338534 (dgx 2) and 338535 (l40 2). Any run with leak > 0 must be quarantined before it is used. The D17 release rule stands, applied to clean data only. Provisional SUBMIT = C9ae: both of its components beat C8 independently on clean data, and C9ae beats C9a on clean pairs. If C9ae still has < 38 clean pairs at finalization, ship C9e, which then has the largest significant diff.
**C10 = C9ae + four forensics fixes** (`submissions/c10_c9ae_plus`, validated; queued as px_c10_s1 at prio 12; a candidate for 2026-10-08):
- `read_file` removed from the analyzer. Malformed `start_line"` keys drive its loops and overflows; it reads with `sed -n` instead.
- No whole-tree git reverts (`checkout -- .`, `stash`, `clean`, `reset`).
- Stop making tool calls after `submit_patch` succeeds. Up to 238 repeated submits per task were seen.
- The repro script asserts each behaviour the issue states.
We rejected `presence_penalty` for the analyzer loops: vLLM applies it within one response only, and the loops repeat across turns.

# 2026-10-07 07:30–08:30 — autopilot work cycle
**Evidence.** Clean proxy s1 at 07:35 (leak=0): paired vs C8 — C9ae n=113 **+0.088** (14W/4L, z=+2.36), C9e n=101 +0.089 (z=+1.88), C9a n=114 +0.061. C9ae vs C9a n=108 +0.037. The D17/D18 rule already selects C9ae (≥38 pairs, ties C9e within 0.03, fewer ctxErr 6 vs 7); RELEASE.md table refreshed. The ~10:30 cycle re-applies the rule.
Harness audit (reports/autopilot/harness_knobs_20261007.md): the submission schema has **no hard per-sub-agent call/turn cap** (unknown keys fail compilation); `submit_patch` never ends the episode; sub-agent compaction is not configurable.
**D19 — Thinking has been OFF in every submission since the anchor.** `include_thoughts: false` forces `chat_template_kwargs.enable_thinking=False` and drops `thinking_token_budget` (`adk_submission/resolvers/generation.py:290-337`). So anchor/C8/C9*/C10 all ran without reasoning; D13's "thinking-on generalizes" was a misreading — the anchor's gain came from the analyzer sub-agent/prompting, not thinking. Thinking is now an untested lever aimed at the largest failure class ("wrong fix", 20/28 of C9ae failures).
Action: **C11t = C9ae + `include_thoughts: true` on the root only** (thinking_budget 4096 now takes effect; analyzer unchanged). One change, paired vs C9ae. Queued px_c11t_s1 at prio 06, interleaved shard-by-shard with C10. Decision rule: C11t replaces the base if paired diff vs C9ae ≥ +0.03 over ≥ 60 pairs AND its proxy min/task ≤ 1.3× C9ae's on the same GPU types AND a Kaggle L4 timing run gives 150×mean + 0.5 h ≤ 11 h (D9). Stop rule: drop if diff < 0 after 60 pairs or ctxErr/err rises by > 5 tasks.
E1 (reports/autopilot/e1_inventory.md): 173 passing proxy trajectories (66 tasks) exist, but they contain no thinking text and were not recorded through the capture proxy, so there is no SFT-ready data. E1 waits for D19's answer (train with or without thinking), then records capture-enabled seeds of the winner.

**D20 — Kaggle eval kernels pinned to the last working image; queue favours C11t (2026-10-07 08:45).** Both L4 timing kernels (C9ae, C10) ended in ERROR within seconds: Kaggle's default image moved to Python 3.13 and the competition's cp312 wheelhouse no longer installs. `scripts/kaggle_eval/make_kernel.py` now pins `docker_image` (sha256:37c64f7d…, the image of the COMPLETE lora-smoke kernel) with `docker_image_pinning_type: original`. The scorer is unaffected (it runs its own stack). Relaunched L4 timing for C9ae and C11t (C10 after a slot frees; C10 is neutral vs C9ae, +0.000 on n=45, and faster). Queue: C11t s1 shards → prio 05 (to reach D19's 60 pairs first), C10 s1 stays 06; C11t s2 + C9ae s2 at prio 08, interleaved with the D11 calibration runs. Tomorrow's draft release = C9ae unless C11t passes D19.

**D21 — C11n = C11t without the code_analyzer sub-agent (2026-10-07 09:00).** Trace analysis (reports/autopilot/c11t_trace_analysis_20261007.md, 43 pairs): thinking is active on every root call, rarely hits the 4096 budget (2/2496 calls; a larger budget is not worth testing), costs ≈1.1× time; with thinking on the root skips the analyzer in 17/43 tasks, and 2 of C11t's 3 losses are analyzer runaways (context overflow / 86 of 100 calls). Hypothesis: with thinking, the analyzer is net negative or neutral and only adds runtime risk. Test: px_c11n_s1 at prio 07, paired vs C11t. Rule: adopt C11n over C11t if paired diff ≥ −0.01 over ≥ 60 pairs and min/task is lower (simpler + faster = less D9 risk); drop if diff ≤ −0.03.

**D22 — Today's (2026-10-07) release may switch to C11t; L4 timing is the only open gate (09:45).** Proxy s1 clean (leak=0): C11t vs C9ae n=105, +0.105 (16W/5L, sign-z +2.40); vs C8 n=100, +0.200 (23W/3L, z +3.92); min/task 14.1 vs 12.8 (1.10×); ctxErr 3 / err 7 vs C9ae 10 / 26 on more tasks. D19's proxy conditions are met. The expected gain (+0.1 on proxy, ≈ +5 public tasks if even half transfers) outweighs one day's LB reading of C9ae, and C9ae stays a fallback. A Notebook Timeout costs only that day's slot.
Rule for the 10:28 / 11:28 cycles: fetch `gemma-rl-eval-c11t-t30s` (and `-c9ae-t30s`) and run `scripts/kaggle_eval/d9_timing.py c11t-t30s c9ae-t30s`. **SUBMIT C11t** (`submission_2026-10-07_c11t_c9ae_think.zip`) if the kernel is COMPLETE with ≥ 25 tasks and either (a) 150 × mean + 0.5 h ≤ 11 h, or (b) the C9ae kernel is also complete and the paired total-time ratio C11t/C9ae ≤ 1.05 (C9ae's root equals C8's, and C8 completed on the scorer). Otherwise (kernel not done by 12:00 IST, ERROR, or timing fails) keep C9ae today and C11t becomes tomorrow's candidate under the same gate. Also re-check that C11t's paired diff vs C9ae is still ≥ +0.03 with all s1 shards.

**D23 — C13t = C11t + repo-locate skill in the analyzer (2026-10-07 09:55).** Offline eval (reports/autopilot/locskill_eval_20261007.md, 48 proxy tasks / 13 repos): gold file top-1 71% / top-5 96% vs a grep baseline 44% / 79%, 0.3 s per call, 2 ranking bugs fixed in locate.py. Skills are not budget-gated, so this targets the analyzer runaways behind 2 of C11t's 3 losses. Built on C11t (the likely next base) rather than C9ae; c13l (on C9ae) is not queued. Test: px_c13t_s1 at prio 07, interleaved with C11n, paired vs C11t. Rule: adopt over C11t if diff ≥ +0.03 over ≥ 60 pairs and min/task not higher; if both C11n and C13t beat C11t, next build = C11n + repo-locate on the root. Caveat: the proxy repos may overlap the skill's tuning set, so a proxy win can overstate the hidden-set gain.

**D24 — 2026-10-07 release stays C9ae; C11t is the default for 2026-10-08 once L4 timing passes; C10 dropped (10:45).** C11t s1 is now complete (152 tasks, clean): +0.112 vs C9ae (24W/7L, sign-z +3.05). Its total task time is 1.25× C9ae's on the same GPU types (95 tasks; median per-task ratio 1.54×), inside D19's 1.3× limit. The L4 timing kernels have run serially since 08:30, and 30 tasks at ~10 min each will not finish before 12:00. D22 therefore keeps C9ae for today. C10 is neutral vs C9ae (n=122, +0.000, 11W/11L), so it is dropped: no s2, and its changes are not carried into C12. Tomorrow's draft (submissions/daily/2026-10-08/RELEASE.md) switches to C11t as soon as the L4 kernel passes D9. C11t s2 now runs through the capture proxy (separate queue ops/queue_cap, worker env APQ/CAPTURE=1, job ap-worker-cap). The same runs supply release evidence and E1 SFT trajectories with thinking text.
