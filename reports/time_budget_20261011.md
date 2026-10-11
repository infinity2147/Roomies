# Where the time goes: L4 time budget of the Gemma-4-31B SWE agent (2026-10-11)

**Question.** C9e (root agent plus `code_analyzer` sub-agent, thinking off) sits at the 12 h edge. The thinking variants (C15n512, C11n) solve about 11 points more but take about 1.8x the time. Where does the wall time go, which part of it is waste, and can removing the waste pay for thinking?

**Answer in one paragraph.**
- **Decode is the clock.** On L4, 78–85 % of every task's wall time is decoding completion tokens at about 36 tok/s. Prefill (vLLM prefix caching works), tool execution and sandbox setup/verification together take only 15–22 %.
- **Thinking costs a fixed tax on every call, not a long think.**
  - Thinking adds about 160 reasoning tokens to *every* root call. That is about 10k tokens and 280–300 s per task, roughly 55 % of a thinking run.
  - Thinking also triples compaction (the reasoning stays in the history).
  - A thinking budget of 512 instead of 4096 hardly changes the reasoning tokens per call.
- **The removable waste is mostly degenerate loops, not verbosity.**
  - C9e: rejected `edit_file` calls with missing `old_string`, which are not charged to the 100-call budget and so can loop hundreds of times; the analyzer ignoring its 20-call cap; loops of identical calls; BudgetExceeded loops.
  - Thinking runs: the agent keeps going after the fix is verified, and loops on `submit_patch`. The run only ends on a text-only reply, so the loop is free in tool budget but costs about 500 thinking tokens per call.
  - Narration and observation size are negligible.
- **Thinking fits if the waste goes and a time cap is added.**
  - Removing the measurable waste takes C9e from 4.9 to 3.0 L4-min/task, and C15n512 from 8.4 to 6.3.
  - Adding `max_time_minutes: 8` brings C15n512 to **5.1 min/task**, inside the nominal 5.93 min/task (12 h minus about 8.5 min vLLM start-up, over 120 tasks). The cost is at most 2.9 % of tasks (≈ 6 % of its solves).
  - It does **not** fit under the D28 1.45x scorer-slowdown safety factor (4.1 L4-min/task) without a tighter cap or fewer root calls.

Script: `src/analysis/time_budget.py` (re-runnable in about 1 min on CPU). Generated tables: `reports/time_budget/tables.md`; per-task rows: `reports/time_budget/{capture,trace}_tasks.jsonl`; models and interventions: `reports/time_budget/summary.json`.

---

## 0. Data and method

| source | what | n tasks |
|---|---|---|
| Kaggle L4 serial captures (`results/kaggle/{c9ae,c11t,c11n,c15t512}-t30s`) | Every LLM request and response with start time `t`, latency `dt` and usage. Exact scorer hardware, CONC=1, same 30 ids. | 4 × 30 |
| Kaggle L4 traces (c11n, c11t, c15t512) | Full trajectories of the same runs. | 3 × 30 |
| `results/px/time_c9e/l4_t30_ids` | C9e, A40 serial, same 30 ids, full traces. | 30 |
| Proxy runs `px_c9e_s1..5`, `px_c15n512_s1..3`, `px_c8_s1..4` | Full traces, 152 tasks per seed. Concurrent workers, so their wall clock is not used. | 760 / 449 (+7 without trace) / 607 |

**Latency model** (fit per L4 capture): `dt = a + b·new_prompt_tok + c·completion_tok + d·completion_tok·prompt_tok`.
- `new_prompt_tok` is the part of the prompt not covered by the previous request of the same conversation (vLLM prefix cache).
- The fit has R² = 0.997–0.999 on 2–4k calls per run.
- Decode is 36.4–37.1 tok/s at 4k context and 33.5–34.1 tok/s at 16k. Prefill runs at 1.65–2.3k new tok/s.
- **Prefix caching works.** Fitting prefill on the full prompt would imply about 28k tok/s, which is not physical. The mean prompt is 8.8k tokens, but only about 270 tokens per call are new.

**Trace re-costing.**
- Every trace LLM call is re-priced with the L4 model of its family:
  - C9e and C8 use c9ae.
  - C15n512 uses c15t512.
  - Thinking budgets are identical in that pairing.
- Added to each task:
  - tool time from the trace;
  - compaction cost at the per-root-call rate measured on the same L4 capture (compaction calls are invisible in traces);
  - the measured L4 setup+verify gap.
- **Validation** on the 90 L4 tasks that have both a trace and a capture:
  - summed time is within 1 % (c11n 8.73 vs 8.69 min/task, c15t512 9.04 vs 8.97, c11t 7.72 vs 7.67);
  - per-task MAPE is 7–9 %;
  - C9e proxy re-costed: 4.92 min/task, against 4.92 measured for C9ae on L4.

"h/120" below means hours per 120 tasks on L4: mean s/task × 120 / 3600.

## 1. Wall-time decomposition on L4 (measured, captures)

| run | min/task mean / med / p90 | decode | prefill | per-call overhead | tool exec (in-task gaps) | setup + verify (between tasks) | LLM s: root / analyzer / compaction | calls: root / analyzer / compaction |
|---|---|---|---|---|---|---|---|---|
| C9ae (no think) | 4.92 / 3.08 / 12.13 | 231 s (78 %) | 16 s (5 %) | 21 s (7 %) | 17 s (6 %) | 10 s (3 %) | 184 / 77 / 7 | 77 / 52 / 1.0 |
| C11t (think + analyzer) | 7.67 / 5.96 / 17.33 | 385 s (84 %) | 27 s (6 %) | 2 s | 26 s (6 %) | 20 s (4 %) | 328 / 42 / 44 | 52 / 24 / 1.7 |
| C11n (think, no analyzer) | 8.69 / 6.79 / 16.61 | 444 s (85 %) | 35 s (7 %) | 0 | 32 s (6 %) | 10 s (2 %) | 408 / 0 / 70 | 63 / 0 / 2.8 |
| C15t512 (think 512 + analyzer) | 8.97 / 5.72 / 15.75 | 431 s (80 %) | 32 s (6 %) | 0 | 45 s (8 %) | 30 s (6 %) | 380 / 38 / 45 | 65 / 25 / 1.8 |

Solved vs unsolved, in L4 min/task:

| run | solved | unsolved |
|---|---|---|
| C11t | 5.04 | 9.42 |
| C11n | 8.33 | 8.97 |
| C15t512 | 6.77 | 10.65 |

C9ae has no per-task labels. For C9e proxy (L4-estimated):
- solved: mean 208 s, median 112, p90 415;
- unsolved: mean 350 s, median 241, p90 730.

Other fixed costs:
- vLLM start-up plus the first sandbox take about 480–500 s per kernel.
- Setup and verification between tasks takes 10–30 s.

**Root vs analyzer (C9ae).**
- The analyzer makes 40 % of the calls but takes only 29 % of LLM time: 42 tok/call against 76 for the root.
- In C9e proxy traces the analyzer costs 71 s/task (24 %), 38 calls, 1.63 invocations.

**What thinking costs** (C11n − C9ae = +227 s/task):

| component | effect |
|---|---|
| reasoning decode | +306 s (10.9k reasoning tok/task) |
| compaction | +64 s (2.8 vs 1.0 compactions; summaries are 830 tok vs 210, because the reasoning stays in the history) |
| prefill | +19 s |
| tools | +15 s |
| action decode | −93 s (fewer and cleaner calls, no analyzer) |
| per-call overhead | −21 s |

| run | reasoning tok/task | reasoning tok per call | reasoning above 512/call (tok/task) | action tok/task |
|---|---|---|---|---|
| C11t | 8 721 | 168 | 2 915 | 4 794 |
| C11n (budget 4096) | 10 944 | 175 | 2 512 | 4 972 |
| C15t512 (budget 512) | 10 067 | 157 | 107 | 5 264 |

The reasoning is a tax of about 160 tokens (≈ 4.4 s) on **every** root call.
- The budget binds rarely. 4096 → 512 removes at most the 23 % above 512 (≈ 70 s/task on C11n), and C15t512 still spends 10k reasoning tok/task.
- **The lever for thinking is the number of root calls.**
  - A thinking root call costs about 6.5 s (242 tok); a non-thinking analyzer call costs about 1.5 s.
  - C11t (thinking root plus a non-thinking analyzer that does the grepping) is 12 % faster than C11n on the same 30 L4 tasks: 7.67 vs 8.69 min.

## 2. Wasted work (exclusive attribution, L4-estimated, traces)

Each LLM call (plus its tool time) is assigned to the **first** matching bucket. Full table: T4 in `reports/time_budget/tables.md`.

| bucket | C9e proxy (760) s/task (%) [h/120] | C15n512 proxy (449) | C9e A40-serial (30 L4 ids) | C15t512 L4 (30) | C11n L4 (30) |
|---|---|---|---|---|---|
| post-budget: calls after the 100-call budget is exhausted | 10 (3 %) [0.34] | 5 (1 %) [0.15] | 31 (12 %) [1.02] | 2 [0.07] | 3 [0.10] |
| submit loop: `submit_patch` re-called on an unchanged tree | 5 (2 %) [0.18] | **48 (10 %) [1.59]** | 9 (3 %) [0.29] | **113 (21 %) [3.75]** | 5 [0.18] |
| rejected call: ADK "mandatory input parameters" / backtick paths / edit not-found | **78 (27 %) [2.61]** | 13 (3 %) [0.43] | 30 (12 %) [1.01] | 3 [0.09] | 11 [0.38] |
| loop: 3rd+ identical call, no state change between | 24 (8 %) [0.80] | 8 (2 %) [0.27] | 29 (12 %) [0.98] | 11 [0.36] | 1 [0.02] |
| 2nd identical call, no state change | 4 (1 %) [0.12] | 9 (2 %) [0.31] | 3 [0.11] | 6 [0.19] | 11 [0.38] |
| analyzer beyond 20 calls/invocation or 2nd+ invocation | 21 (7 %) [0.70] | – | 16 (6 %) [0.54] | 4 [0.14] | – |
| after final content in place **and** a passing verification | 13 (4 %) [0.44] | **52 (10 %) [1.73]** | 8 [0.26] | 56 (10 %) [1.88] | 41 (8 %) [1.37] |
| after final content in place, before verification | 6 (2 %) [0.19] | 16 (3 %) [0.54] | 9 [0.31] | 19 [0.64] | 19 [0.64] |
| remaining analyzer work | 22 (8 %) [0.74] | – | 27 (11 %) [0.91] | 23 [0.76] | – |
| remaining root work | 96 (32 %) [3.19] | 270 (54 %) [8.99] | 76 (30 %) [2.53] | 230 (42 %) [7.67] | 351 (67 %) [11.70] |
| compaction | 6 (2 %) | 52 (10 %) [1.72] | 4 | 45 (8 %) | 70 (13 %) [2.34] |
| setup + verify | 10 (3 %) | 31 (6 %) | 10 | 31 (6 %) | 11 (2 %) |
| **total** | **295 s = 4.92 min [9.84 h]** | **503 s = 8.39 min [16.8 h]** | 253 s [8.4 h] | 542 s [18.1 h] | 524 s [17.5 h] |

**(a) Time after the final patch content was already in place.**
- Definition: from the earliest root edit after which every non-trivial `+` line of the final patch has appeared in an edit, to the end of the task.
- Solved tasks (§3) spend **27 % (C9e) to 38 % (C15n512) of their trajectory** after this point.
- Including the submit loops, after-content time is about 24 s/task for C9e and about 116 s/task for C15n512 (all tasks).

**(b) Repeated, identical calls and loops.**
- C9e: 28 s/task (9 %), more than half of it in the analyzer.
- The loops are pathological rather than mildly redundant. One call is repeated 28–64 times in a row, for example:
  - `python -c "import rich; print(rich.__version__)"` 56×;
  - `read_file filepath="tqdm/std.py`,start_line:880"` 57×.
- Thinking runs barely loop (≤ 2 %) **except** on `submit_patch`:
  - re-submits cost 48 s/task in C15n512 proxy and 112 s/task **measured** in the C15t512 L4 capture;
  - one L4 task (fastapi_14306) re-submitted for **2 785 s**, and one C11t task for 955 s;
  - 46/449 C15n512 runs have 3 or more re-submits.
- Cause: the harness ends a run only on a text-only reply after a submit, and `submit_patch` is not charged to the budget.

**(c) Rejected or malformed calls.** This is the single biggest C9e sink: 78 s/task (27 %), 2.6 h/120.
- 5 261 of the 6 012 rejected calls in C9e s1+s2 are `edit_file` calls without `old_string`. The model emits `new_string` first and then garbage keys.
- ADK rejects them *before* the tool runs, so **they are not charged to the 100-call budget** and can repeat up to the 500-LLM-call limit. One task had 437 of them.
- Each one also costs about 215–270 decode tokens.
- The heredoc-fallback prompt (C9a "editfix", already in C9ae/C11*/C15n) reduces this to 3–13 s/task. C9e lacks it.
- On L4, C9ae (which has the editfix) still measures 29 s/task of rejected calls.

**(d) Analyzer output ignored or duplicated.**
- The output is almost never ignored: when the analyzer returns a LOCATION and the patch is non-empty, the patch touches that file in 627/633 C9e runs.
- The waste is **overrun**: the prompt cap of "≤ 20 calls" is exceeded in 268/760 C9e runs. Calls beyond 20, plus 2nd and 3rd invocations, cost 21 s/task.
- Once the budget is gone, the analyzer is also the main post-budget looper: the AgentTool child runs under its own 500-call RunConfig.
- Removing the analyzer saves its 71 s/task in C9e but moves localisation onto the root. For thinking roots that is a net loss (C11n is 12 % slower than C11t, see §1).

**(e) Huge observations.** These are irrelevant for time.
- The median observation is about 400 chars and p90 about 1.7–3.8k. The harness already caps command output at 5k chars.
- Thanks to prefix caching, capping every observation at 2 000 chars saves **3–7 s/task (0.1–0.23 h/120)**.
- Prefill is 5–7 % of wall time in total.

**(f) Time on tasks that end unsolved.**
- C9e: 73 % of L4 time goes to the 62 % of tasks that fail (unsolved mean 350 s vs solved 208 s).
- C15n512: 62 % of time goes to the 50 % that fail.
- **Early detection is weak** (T9). Of the tasks still running at T, the solve rate is:

| set | at 4 min | at 6 min | at 8 min | at 10 min | at 15 min |
|---|---|---|---|---|---|
| C9e | 25 % | 24 % | 23 % | 24 % | 12 % |
| C15n512 | 40 % | 33 % | 28 % | 24 % | 28 % |

- Long-running tasks are only moderately less likely to succeed. There is no cheap "hopeless" signal before about 10–15 min.
- "No source edit after K root tool calls → stop" (T10) trades time for solves badly:
  - C9e K=40 saves 67 s/task but loses 28 solved runs out of 760;
  - C15n512 K=50 saves 29 s/task and loses 3 of 449.
- A **wall-clock cap** is the better tail control.
  - It mostly cuts runs whose patch is either already in place or never comes.
  - Of the C15n512 solves still running at 8 min, 36/49 already have their final content in place. A cap only loses a solve if no submit/diff happened before it.

## 3. Solved tasks: when is the fix done?

| set | solved n | L4 s/task (mean / med) | first source edit | final content in place: s (calls) | after content: s (calls) | share of trajectory after content | after first passing verification |
|---|---|---|---|---|---|---|---|
| C9e proxy | 292 | 208 / 112 | 129 / 59 | 143 / 62 (36 / 20 calls) | 46 / 20 (22 / 8 calls) | 27 % mean, 26 % med | 35 / 14 s |
| C15n512 proxy | 226 | 384 / 267 | 126 / 98 | 169 / 131 (21 / 16) | 137 / 60 (35 / 10) | 38 % / 36 % | 126 / 50 s |
| C11n L4 | 13 | 505 / 385 | 254 / 175 | 328 / 224 (37 / 26) | 110 / 59 (32 / 13) | 27 % / 26 % | 85 / 40 s |
| C15t512 L4 | 13 | 413 / 399 | 160 / 130 | 195 / 192 (31 / 30) | 117 / 78 (15 / 10) | 36 % / 28 % | 106 / 65 s |
| C9e A40-serial | 13 | 171 / 141 | 85 / 64 | 93 / 72 (27 / 30) | 73 / 27 (54 / 8) | 37 % / 30 % | 37 / 19 s |

"Final content in place" was detected for 73–91 % of solves; the rest use non-literal edits such as sed substitutions.
- **About a third of a solved trajectory comes after the fix is already written.**
- For the thinking agent this is 137 s mean per solved task. Most of it (126 s) comes *after* a passing test or repro, spent on:
  - extra test runs;
  - adding tests to test files (which the harness discards anyway);
  - `git diff` / `git status`;
  - re-submits.

## 4. Output-token waste (L4 captures)

Completion tokens per call:

| run | root mean / p50 / p90 / p99 | analyzer mean / p50 / p90 |
|---|---|---|
| C9ae | 76 / 13 / 248 / 547 | 42 / 32 / 45 |
| C11n | 215 / 78 / 531 / 1 791 | – |
| C15t512 | 198 / 64 / 523 / 907 | – |

Compaction summaries are 208 tokens (C9ae) and 770–840 tokens (thinking runs).

Decode seconds per task by what the call emitted:

| emitted | C9ae | C11n | C15t512 |
|---|---|---|---|
| reasoning (all calls) | 0 | **306** | **283** |
| run_command scripts/heredocs (repro scripts, python edits) | **79** | 53 | 48 |
| short read/grep/cmd calls, root | 14 | 31 | 30 |
| short read/grep/cmd calls, analyzer | 49 | – | 24 |
| `edit_file` / `write_file` arguments | 36 | 24 | 13 |
| text-only answers (root final + analyzer report) | 31 | 1 | 12 |
| compaction summaries | 6 | 29 | 18 |
| narration text next to a tool call | **1.8** | **0.1** | 12.8 |

- **Narration is not a sink.** C9e/C9ae emit essentially no text beside tool calls, and thinking runs put their prose into reasoning.
- "Forbid narration" saves ≤ 0.5 h/120 even for C15t512.
- In non-thinking runs the expensive outputs are repro and heredoc scripts (35 % of decode) and `edit_file` payloads. In C9e the payloads are repeated by the rejected-call loops in §2(c).

## 5. Ranked time sinks and interventions (L4, hours per 120 tasks)

Savings are non-overlapping (exclusive buckets) and are computed per task, then averaged. Full table: T11.

| # | intervention (how) | C9e: s/task [h/120] | C15n512: s/task [h/120] | notes / risk |
|---|---|---|---|---|
| I3 | Avoid rejected calls: C9a heredoc fallback after one failed `edit_file`, no backticks in args | −39 [−1.31] (50 % of 78 s) | −7 [−0.22] | Already validated in C9ae/C15n prompts. C9e is the only current candidate without it. |
| I2b | **End with a text-only reply right after `submit_patch`** (prompt: "after submit_patch returns ok, reply with one plain sentence and no tool call; that ends the task") | −5 [−0.18] | **−48 [−1.59]** | Kills the 46-min re-submit runaways seen on L4 (C15t512 −113 s/task measured). |
| I5 | Submit immediately after the first passing verification of the fix (no extra tests, no test-file edits) | −13 [−0.44] | **−52 [−1.73]** | By construction the patch is unchanged for the solved runs. Compliance is uncertain. |
| I2 | Loop breaker: never issue a 3rd identical call without a state change (prompt), and/or a mild `frequency_penalty` | −24 [−0.80] | −8 [−0.27] | Mostly degenerate repetition at T=0.2. |
| I4 | Analyzer hard cap 20 calls, single invocation | −21 [−0.70] | – | The prompt cap does not hold (268/760 over). It needs a structural fix: a smaller analyzer, or replacing the AgentTool with a scripted skill. |
| I1 | Stop on BudgetExceeded (root **and** analyzer prompt: "on BudgetExceeded, answer immediately") | −10 [−0.34] | −5 [−0.15] | Heavy tail: one task wasted 406 s. |
| I6 | Cap observations at 2 000 chars | −3 [−0.11] | −4 [−0.13] | Not worth a change. |
| I7 | Forbid narration | 0 | −2 [−0.07] | Not worth a change. |
| | **baseline → after I1–I7 (I3 at 50 %)** | **295 → 179 s (4.92 → 2.98 min) [9.8 → 6.0 h]** | **503 → 378 s (8.39 → 6.31 min) [16.8 → 12.6 h]** | |
| I8 | + `max_time_minutes` = 10 / 8 / 6 (L4 clock) | 2.82 / 2.72 / 2.56 min; solved lost 1.7 / 2.5 / 3.3 % of tasks | **5.55 / 5.09 / 4.40 min**; solved lost 2.4 / **2.9** / 6.9 % of tasks | Lost = solved runs whose final content was not in place by T. This is an upper bound, because I1–I7 move fixes earlier. |
| I9 | No-edit-after-K abandon | K=50: −55 s, but loses 20/760 solves | K=50: −29 s, loses 3/449 | Dominated by I8. |
| – | Thinking budget 4096 → 512 (C11n → C15n) | – | ≤ −70 s on C11n (reasoning above 512) | Already taken in C15n512. |

**Top 3 time sinks:**
1. **Reasoning decode in thinking runs.** About 10k tok ≈ 260–306 s/task (52–58 % of a thinking run). This is intrinsic to thinking: about 160 tok on *every* root call, so it scales with the number of root calls, not with the budget.
2. **Rejected `edit_file` loops in C9e.** 78 s/task, 27 %, 2.6 h/120. They are not budget-charged, so they are unbounded.
3. **Post-fix tail in thinking runs.** Verified-fix tail plus submit loops cost 100 s/task (20 %, 3.3 h/120) in C15n512 and 169 s/task (31 %) in the C15t512 L4 run (trace-based; the re-submits alone measure 112 s/task in its capture).

Next come the analyzer overrun and loop pair (C9e, 45 s/task, 1.5 h/120) and compaction (thinking, 45–70 s/task).

**Can the savings pay for thinking?**

| configuration (L4-estimated) | min/task | h per 120 tasks | vs the 5.93 min/task budget |
|---|---|---|---|
| C9e today | 4.92 | 9.8 | fits (as measured) |
| C15n512 today | 8.39 | 16.8 | 1.41x over |
| C15n512 + I1–I7 | 6.31 | 12.6 | 6 % over |
| C15n512 + I1–I7 + `max_time_minutes: 10` | 5.55 | 11.1 | fits, −2.4 % of tasks |
| **C15n512 + I1–I7 + `max_time_minutes: 8`** | **5.09** | **10.2** | **fits with 14 % headroom, −2.9 % of tasks (≈ −6 % of its solves)** |
| C15n512 + I1–I7 + `max_time_minutes: 6` / 5 / 4 (L4 min) | 4.40 / 3.95 / 3.41 | 8.8 / 7.9 / 6.8 | −6.9 / −10.7 / −15.4 % of tasks |

**Yes on our L4 measurement.** A C15n512 with the three prompt fixes (I2b, I5, I1; I3 is already in it) and an 8-min cap costs about the same wall time as today's C9e (5.09 vs 4.92 min/task). It keeps pass@1 ≈ 0.507 − 0.03 ≈ 0.48 against C9e's 0.385.
- The 1.8x premium does not disappear: the cleaned-up thinking agent is still 2.1x the cleaned-up C9e (378 vs 179 s).
- But the waste and tail that the thinking agent carries (≈ 200 s/task) are almost exactly what it needs to give up.
- **Under the D28 "scorer is 1.45x slower" assumption the margin goes.**
  - The budget becomes 5.93 / 1.45 = 4.09 L4-min/task.
  - `max_time_minutes` is enforced on the scorer's own clock, so a configured 8 min equals about 5.5 L4-min.
  - Interpolating the 5- and 6-L4-min rows gives about 4.2 L4-min/task: roughly at budget, losing about 8–9 % of tasks (≈ −17 % of solves), i.e. pass@1 ≈ 0.42.
  - Today's C9e (4.92 L4-min, uncapped) would not fit that scenario either, while a cleaned C9e (2.98) would.
- The next lever is fewer root calls: keep a non-thinking analyzer for exploration as in C11t/C15t, or batch greps per call. Each avoided thinking call saves about 6.5 s.

**Most promising intervention.** For the thinking agent, add an "end-of-task protocol" to the C15n512 prompt:
1. Once the repro passes and the nearest tests pass, run `git diff` once and call `submit_patch` once.
2. Then reply with a single plain-text sentence and no tool call.
3. On any BudgetExceeded, do the same immediately.

Combine it with `max_time_minutes: 8`.
- Estimated −100 s/task from I2b + I5, −5 s from I1, and the cap removes the remaining tail.
- Together that is 8.39 → 5.09 L4-min/task (16.8 → 10.2 h/120).
- All of it is prompt or config, with no new tool or model.
- It should be checked with one L4 serial t30s kernel, because compliance with "stop now" prompts is the main uncertainty.

## 6. Trace excerpts

**A. Rejected-edit loop, C9e** (`px_c9e_s2/s2`, tenacity_651, *solved*, 2 452 L4-s, of which 2 172 s are rejected calls)
```
   4 root read_file   tenacity/retry.py 220-250                      -> ok
   5 root run_command cat > /tmp/repro.py <<'EOF' ...                -> exit 1 (bug reproduced)
   6 root edit_file   {"filepath": "tenacity/retry.py", "new_string": "        if message is not None and match ...}
                      -> {"error": "Invoking `edit_file()` failed as the following mandatory input parameters are not present: old_string"}
 7-11 root  same call, 268 completion tok each, same error            (prompt grows 275 tok/call)
12-36 root edit_file  {"filepath": ..., "if message and match": "raise TypeError(..."}  -> same error x25
  37 root (compaction at ~14k tokens -> context reset to 2.8k) code_analyzer re-invoked, repro re-written
43-59 root  same malformed edit_file loop again ...
 ... content finally in place at 2 362 s, after 370 LLM calls; none of the rejected calls counted toward the 100-call budget
```

**B. Post-fix tail and submit loop, C15n512** (`px_c15n512_s3/s4`, jinja_2026, *solved*, 2 286 L4-s, final content in place at 171 s)
```
  13 root edit_file  src/jinja2/runtime.py (slots fix)           -> ok
  14 root edit_file  src/jinja2/runtime.py (__getattr__)         -> ok     <- final patch content complete (171 s)
  16 root run_command cat > /tmp/repro_copy.py ... ; python ...  -> "Copy succeeded / Deepcopy succeeded"
  18 root run_command python -m pytest tests/test_runtime.py tests/test_nativetypes.py -x -q -> all passed
  21 root run_command cat >> tests/test_nativetypes.py <<'EOF' ...  (test edits; the harness resets test files)
  22-198 more reads, test edits, re-runs ...
 199-214 root submit_patch {} -> ok   (x16 in a row)
 ...
 489-493 root submit_patch {} -> ok   (523 completion tokens each, mostly reasoning)
 => 1 700 s (74 %) after the first passing verification; 494 LLM calls in total
```

**C. Analyzer BudgetExceeded loop, C9e** (`time_c9e`, fastapi_14448, unsolved, 523 LLM calls, 729 L4-s, of which 406 s are post-budget)
```
 root -> code_analyzer #1: 26 calls; root 9 calls; code_analyzer #2: 58 calls; root 82 calls (72 of them submit_patch)
 root -> code_analyzer #3 ("Use at most 20 tool calls"): 347 calls
 177 analyzer run_command grep -rn "is_async_callable" fastapi/   -> {"error_type": "BudgetExceeded", "Tool call budget exhausted (100 calls)"}
 178 analyzer read_file fastapi/routing.py 60-100                  -> BudgetExceeded
 179-525 analyzer run_command grep -rn "is_async_callable" fastapi/ | grep -v "import"  -> BudgetExceeded  (x346, identical)
```
The AgentTool child has its own 500-LLM-call limit and the harness checks the tool budget only after the root's `run_async` returns, so nothing stops this loop except the analyzer itself.

## 7. Caveats

- **C9e has no L4 capture of its own.** Its numbers come from the C9ae L4 latency model applied to C9e traces. That reproduces 4.92 min/task, equal to the measured C9ae L4 value.
- **Proxy tool times** come from 8 concurrent workers and are slightly inflated (16–21 s/task vs 7 s serial). This is minor: tools are under 7 % of time.
- **"Final content in place"** checks `+` lines only (not deletions) and is found for 73–91 % of solves. Tasks without it count as "never in place" in the cap-loss estimate, which is conservative.
- **Savings assume perfect compliance** with prompt rules. I3 is counted at 50 %. The cap-loss estimate ignores that fixes would land earlier once waste is removed, so it is pessimistic.
- **Scorer speed is the larger uncertainty.** D28 measured the real scorer about 45 % slower than our L4 projection. Everything here is in our-L4 seconds. `max_time_minutes` is enforced on the scorer clock, so caps stay safe but the cap-loss rate would grow on a slower scorer.

Re-run: `.venv/bin/python src/analysis/time_budget.py` (writes `reports/time_budget/`; `--quick` uses one seed per proxy set).
