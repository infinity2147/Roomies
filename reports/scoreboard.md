# Proxy experiment scoreboard

Generated 2026-10-10T21:12:51 by `.venv/bin/python -m src.eval.px_scoreboard` (rerun to refresh; trace parsing cached in `results/.scoreboard_cache.json`). Machine-readable: `results/scoreboard.json`.

**Populations.** `full152` = proxy shards s0..s7 (152 tasks); `evalhalf85` = held-out half e0..e3 (85 tasks, used for fine-tuned models); `trainhalf67` = t0..t3; `public` = public-LB task set (informational). Never compare pass@1 across populations — use the paired Δ column, which is always computed on the candidate's own tasks.

**Columns.** Δ parent = paired diff on matched (task, seed-label) pairs vs the parent (parent runs from any population, restricted to the candidate's tasks); W/L = candidate-only / parent-only solves; CI = 95% task-clustered paired bootstrap (2000 resamples); p = exact two-sided sign test on W vs L. tok = mean generated (completion, incl. thinking) tokens/task from traces. calls = tool calls/task. badTC = rejected/invalid tool calls per task (missing mandatory args / INVALID_ARGUMENTS, malformed names/keys, plus tool calls truncated at the token limit). min, p90 = per-task **parallel-worker wall time on the proxy cluster (A40/L40/DGX, concurrent)** — not L4 serial time. TO = session timeouts; bud = tool-call/turn budget hit (task error or BudgetExceeded tool result); ctx = context-window errors; infra = model NotFound/5xx/ENOSPC; empty = no patch; inval = agent patch made the hidden test patch fail to apply, or test run shows Syntax/IndentationError (heuristic); leak = patch touches b/conftest.py or b/pytest.ini. Think = root/analyzer thinking (include_thoughts & budget>0).


## full152

| cand | bundle | parent | adapter | think root/anl | cap | seeds | n | succ | pass@1 | Δ parent [95% CI] | W/L | p | Δ vs C8 | tok/task | calls | badTC | min | p90 | TO | bud | ctx | infra | empty | inval | leak | status / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **c15n512** | c15n_think512_noanalyzer | c8 |  | on(512)/n/a |  | 1,2 | 304 | 154 | **0.507** | +0.197 [+0.141,+0.257] (n=304) | 68/8 | 0.000 |  | 12.7k | 44 | 0.88 | 23.9 | 60.1 | 26 | 26 | 0 | 1 | 21 | 10 | 0 |  |
| **c11n** | c11n_think_noanalyzer | c8 |  | on(4096)/n/a |  | 1,2 | 304 | 152 | **0.500** | +0.191 [+0.135,+0.247] (n=304) | 66/8 | 0.000 |  | 14.5k | 43 | 1.20 | 20.7 | 45.8 | 11 | 25 | 0 | 7 | 12 | 8 | 0 | fails L4 time gate (D28 note) |
| **c13t** | c13t_c11t_locskill | c8 |  | on(4096)/off |  | 1,2 | 304 | 151 | **0.497** | +0.188 [+0.135,+0.243] (n=304) | 66/9 | 0.000 |  | 15.2k | 51 | 0.81 | 20.5 | 47.0 | 15 | 43 | 4 | 3 | 22 | 7 | 0 |  |
| **c14d** | c14d_c11t_importcheck | c11t |  | on(4096)/off |  | 1,2 | 304 | 142 | **0.467** | +0.023 [-0.026,+0.069] (n=304) | 31/24 | 0.419 | +0.158 [+0.105,+0.207] 58/10 | 13.0k | 49 | 1.27 | 16.7 | 36.9 | 5 | 35 | 8 | 0 | 24 | 5 | 0 |  |
| **c14b** | c14b_c11t_reprofail | c11t |  | on(4096)/off |  | 1,2 | 304 | 139 | **0.457** | +0.013 [-0.039,+0.069] (n=304) | 29/25 | 0.683 | +0.148 [+0.092,+0.204] 57/12 | 12.8k | 48 | 1.50 | 19.9 | 48.6 | 19 | 38 | 11 | 0 | 28 | 12 | 0 |  |
| **c15t1024** | c15_think1024 | c8 |  | on(1024)/off |  | 1 | 152 | 69 | **0.454** | +0.151 [+0.079,+0.230] (n=152) | 30/7 | 0.000 |  | 12.7k | 51 | 1.36 | 19.3 | 50.6 | 10 | 14 | 4 | 2 | 13 | 6 | 0 | pilot |
| **c17** | c17_c9e_analyzerthink | c9e |  | off/on(2048) |  | 1,2,3 | 437 | 196 | **0.449** | +0.059 [+0.013,+0.115] (n=304) | 37/19 | 0.022 | +0.126 [+0.082,+0.173] 72/17 | 17.3k | 55 | 13.39 | 19.7 | 40.9 | 11 | 50 | 17 | 0 | 43 | 7 | 0 | partial(437/456); fails A40 serial time gate (ratio 2.11 > 1.15) |
| **c15t512** | c15_think512 | c8 |  | on(512)/off |  | 1 | 152 | 68 | **0.447** | +0.145 [+0.079,+0.211] (n=152) | 26/4 | 0.000 |  | 11.3k | 51 | 1.95 | 19.9 | 48.4 | 12 | 12 | 7 | 1 | 18 | 7 | 0 | pilot; fails L4 time gate |
| **c11t** | c11t_c9ae_think | c8 |  | on(4096)/off |  | 1,2 | 304 | 135 | **0.444** | +0.135 [+0.072,+0.197] (n=304) | 59/18 | 0.000 |  | 11.9k | 46 | 1.01 | 23.9 | 60.1 | 39 | 33 | 4 | 0 | 45 | 9 | 0 | fails L4 time gate (D26) |
| **c14c** | c14c_c11t_timebox | c11t |  | on(4096)/off |  | 1 | 152 | 67 | **0.441** | -0.046 [-0.112,+0.020] (n=152) | 11/18 | 0.265 | +0.138 [+0.072,+0.204] 26/5 | 13.9k | 51 | 4.96 | 18.3 | 38.9 | 5 | 18 | 5 | 0 | 16 | 5 | 0 | pilot |
| **c14p** | c14p_bestof2 | c11t |  | on(4096)/n/a |  | 1 | 19 | 8 | **0.421** | +0.053 [+0.000,+0.158] (n=19) | 1/0 | 1.000 | +0.263 [+0.105,+0.474] 5/0 | 19.1k | 77 | 0.58 | 45.2 | 60.3 | 3 | 4 | 0 | 3 | 8 | 1 | 0 | infra-errors; partial(19/152); pilot; intra-task best-of-2 |
| **c9e** | c9e_analyzercap | c8 |  | off/off |  | 1,2 | 304 | 117 | **0.385** | +0.076 [+0.020,+0.132] (n=304) | 40/17 | 0.003 |  | 7.6k | 54 | 18.40 | 13.2 | 34.7 | 19 | 30 | 17 | 0 | 57 | 5 | 0 | current daily release |
| **c9c** | c9c_timebox | c8 |  | off/off |  | 1 | 152 | 56 | **0.368** | +0.066 [+0.000,+0.132] (n=152) | 18/8 | 0.076 |  | 8.3k | 60 | 12.10 | 11.6 | 26.6 | 2 | 20 | 24 | 0 | 38 | 3 | 0 | pilot |
| **c9ae** | c9ae_combo | c8 |  | off/off |  | 1,2 | 304 | 110 | **0.362** | +0.053 [+0.003,+0.102] (n=304) | 33/17 | 0.033 |  | 7.6k | 61 | 8.56 | 12.5 | 29.7 | 5 | 39 | 23 | 1 | 65 | 5 | 0 | LB 0.10 (uncapped zip) |
| **c9a** | c9a_editfix | c8 |  | off/off |  | 1,2 | 304 | 107 | **0.352** | +0.043 [+0.003,+0.082] (n=304) | 28/15 | 0.066 |  | 7.8k | 58 | 18.07 | 10.8 | 22.2 | 0 | 32 | 37 | 0 | 71 | 7 | 0 |  |
| **c9all** | c9all_bundle | c8 |  | off/off |  | 1,2 | 304 | 105 | **0.345** | +0.036 [-0.010,+0.082] (n=304) | 30/19 | 0.152 |  | 7.2k | 55 | 15.61 | 10.1 | 23.6 | 4 | 32 | 42 | 0 | 71 | 7 | 0 |  |
| **c9b** | c9b_reprofail | c8 |  | off/off |  | 1 | 152 | 51 | **0.336** | +0.033 [-0.020,+0.086] (n=152) | 12/7 | 0.359 |  | 7.5k | 60 | 16.03 | 13.6 | 33.5 | 7 | 18 | 16 | 0 | 31 | 6 | 0 | pilot |
| **anchor** | anchor_public | c8 |  | off/off |  | 1,2,3 | 456 | 149 | **0.327** | +0.002 [-0.039,+0.042] (n=456) | 45/44 | 1.000 |  | 8.4k | 59 | 20.78 | 12.0 | 26.9 | 7 | 50 | 62 | 0 | 100 | 16 | 0 |  |
| **c8** | c8_anchorplus | — |  | off/off |  | 1,2,3,4 | 608 | 197 | **0.324** | — | — | — |  | 8.0k | 57 | 19.14 | 12.0 | 29.0 | 7 | 67 | 77 | 0 | 142 | 13 | 0 | champion (LB 0.13) |
| **c10** | c10_c9ae_plus | c8 |  | off/off |  | 1 | 152 | 49 | **0.322** | +0.020 [-0.059,+0.092] (n=152) | 19/16 | 0.736 |  | 6.6k | 51 | 8.88 | 18.6 | 60.2 | 19 | 12 | 2 | 7 | 40 | 3 | 0 | pilot |
| **c9d** | c9d_importcheck | c8 |  | off/off |  | 1 | 152 | 49 | **0.322** | +0.020 [-0.033,+0.072] (n=152) | 11/8 | 0.648 |  | 8.5k | 57 | 22.32 | 14.0 | 35.6 | 5 | 18 | 21 | 0 | 34 | 4 | 0 | pilot |
| **c9ae_t7** | c9ae_t7 | c8 |  | off/off | 7 | 1,2,3,4,5 | 760 | 243 | **0.320** | +0.003 [-0.039,+0.043] (n=608) | 56/54 | 0.924 |  | 3.7k | 41 | 3.33 | 5.5 | 7.3 | 298 | 25 | 28 | 0 | 230 | 11 | 0 | 7-min cap |
| **c11tc** | c11tc_timecap | c8 |  | on(4096)/off | 5 | 1,2,3 | 456 | 132 | **0.289** | -0.035 [-0.090,+0.018] (n=456) | 41/57 | 0.129 |  | 3.8k | 25 | 0.45 | 4.9 | 5.2 | 293 | 5 | 7 | 0 | 240 | 7 | 0 | rejected (no gain, 5-min cap) |
| **c9ae_t5** | c9ae_t5 | c8 |  | off/off | 5 | 1,2,3 | 456 | 127 | **0.279** | -0.046 [-0.092,+0.000] (n=456) | 32/53 | 0.029 |  | 2.8k | 35 | 2.70 | 4.6 | 5.3 | 256 | 7 | 11 | 0 | 182 | 14 | 0 | LB 0.08; 5-min cap |
| **c6a_t5** | c6a_t5 | c8 |  | off/n/a | 5 | 1,2,3 | 456 | 122 | **0.268** | -0.057 [-0.112,-0.002] (n=456) | 37/63 | 0.012 |  | 2.6k | 32 | 6.28 | 4.1 | 5.3 | 207 | 0 | 0 | 1 | 113 | 21 | 0 | LB 0.06; 5-min cap |
| **c18_e2lora** | c18_c8_e2lora_nocap | c8 | e2 | off/off |  | 1,2 | 303 | 50 | **0.165** | -0.145 [-0.214,-0.079] (n=303) | 14/58 | 0.000 |  | 18.8k | 60 | 0.09 | 48.9 | 60.3 | 141 | 152 | 6 | 0 | 116 | 7 | 205 | suspect; partial(303/304); CONTAMINATED: harness conftest/pytest.ini leak in 205/303 patches (D18: leak must be 0); pass@1 on leak-free rows 0.041; LoRA run under infra investigation (~49 min/task, budget/timeouts); D30 rejection on hold; 19 re-run rows (last kept) |
| **c16_e2lora** | c16_e2lora | c8 | e2 | off/off | 5 | 1 | 152 | 1 | **0.007** | -0.296 [-0.375,-0.224] (n=152) | 1/46 | 0.000 |  | 0.3k | 4 | 0.00 | 5.1 | 5.2 | 151 | 0 | 0 | 0 | 148 | 0 | 0 | suspect; pilot; LoRA run under infra investigation (earlier attempt ran on base-only workers; 5-min cap confound) |

## evalhalf85

| cand | bundle | parent | adapter | think root/anl | cap | seeds | n | succ | pass@1 | Δ parent [95% CI] | W/L | p | Δ vs C8 | tok/task | calls | badTC | min | p90 | TO | bud | ctx | infra | empty | inval | leak | status / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **c9e_evalhalf** | c9e_analyzercap | c8 |  | off/off |  | 1,2 | 170 | 72 | **0.424** | +0.041 [-0.024,+0.100] (n=170) | 18/11 | 0.265 |  | 9.9k | 61 | 20.44 | 12.3 | 29.7 | 0 | 34 | 10 | 0 | 21 | 3 | 79 | CONTAMINATED: harness conftest/pytest.ini leak in 79/170 patches (D18: leak must be 0); pass@1 on leak-free rows 0.429 |
| **c16** | c16_c9e_graphlocate | c9e_evalhalf/c9e |  | off/off |  | 1,2 | 170 | 68 | **0.400** | -0.024 [-0.094,+0.053] (n=170) | 14/18 | 0.597 | +0.018 [-0.053,+0.094] 17/14 | 8.0k | 57 | 18.02 | 14.5 | 33.3 | 7 | 26 | 17 | 0 | 32 | 8 | 66 | CONTAMINATED: harness conftest/pytest.ini leak in 66/170 patches (D18: leak must be 0); pass@1 on leak-free rows 0.356; rejected (no gain vs C9e, graph-locate) |
| **c9ae_evalhalf** | c9ae_editfix_analyzercap | c8 |  | off/off |  | 1,2 | 170 | 61 | **0.359** | -0.024 [-0.094,+0.047] (n=170) | 14/18 | 0.597 |  | 7.3k | 52 | 12.70 | 18.2 | 60.1 | 22 | 22 | 14 | 0 | 38 | 2 | 63 | CONTAMINATED: harness conftest/pytest.ini leak in 63/170 patches (D18: leak must be 0); pass@1 on leak-free rows 0.308 |
| **c19_distill** | c19_c9ae_distill | c9ae_evalhalf | d1 | off/off |  | 1,2 | 128 | 12 | **0.094** | -0.234 [-0.328,-0.148] (n=128) | 2/32 | 0.000 | -0.297 [-0.391,-0.203] 1/39 | 0.7k | 8 | 0.30 | 60.0 | 60.2 | 116 | 0 | 0 | 0 | 113 | 0 | 0 | suspect; partial(128/170); LoRA run under infra investigation (20/22 tasks hit 60-min timeout in first harvest) |

## trainhalf67

| cand | bundle | parent | adapter | think root/anl | cap | seeds | n | succ | pass@1 | Δ parent [95% CI] | W/L | p | Δ vs C8 | tok/task | calls | badTC | min | p90 | TO | bud | ctx | infra | empty | inval | leak | status / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **c11t_cap** | c11t_c9ae_think | c8 |  | on(4096)/off |  | 3,4,5,6,7,8 | 402 | 176 | **0.438** | +0.179 [+0.097,+0.269] (n=134) | 30/6 | 0.000 |  | 13.5k | 53 | 1.20 | 25.4 | 60.1 | 38 | 56 | 3 | 0 | 37 | 15 | 0 | thinking capture runs (SFT data) |

## public

| cand | bundle | parent | adapter | think root/anl | cap | seeds | n | succ | pass@1 | Δ parent [95% CI] | W/L | p | Δ vs C8 | tok/task | calls | badTC | min | p90 | TO | bud | ctx | infra | empty | inval | leak | status / notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **c11t_cap** | c11t_c9ae_think | c8 |  | on(4096)/off |  | 1,2,3,4 | 428 | 182 | **0.425** | — | — | — |  | 12.3k | 54 | 1.52 | 17.1 | 35.6 | 16 | 71 | 9 | 0 | 58 | 8 | 0 | thinking capture runs (SFT data) |

## pass@k / oracle union (best-of-2 upside)

Per candidate, on tasks with ≥2 seed runs. pass@2 = unbiased estimate of P(at least one of 2 independent seeds solves) = mean_t[1 − C(k−c,2)/C(k,2)]; union = tasks solved by any seed (oracle, all k seeds); stable = solved by every seed. pass@2 − pass@1 is the ceiling for a perfect best-of-2 selector; a real selector (C14p) recovers only part of it, and best-of-2 doubles L4 time.

| cand | pop | tasks | mean k | pass@1 | pass@2 | Δ(2−1) | union (any seed) | union rate | stable | stochastic |
|---|---|---|---|---|---|---|---|---|---|---|
| c9e_evalhalf | evalhalf85 | 85 | 2.0 | 0.424 | 0.506 | +0.082 | 43 | 0.506 | 29 | 14 |
| c16 | evalhalf85 | 85 | 2.0 | 0.400 | 0.459 | +0.059 | 39 | 0.459 | 29 | 10 |
| c9ae_evalhalf | evalhalf85 | 85 | 2.0 | 0.359 | 0.459 | +0.100 | 39 | 0.459 | 22 | 17 |
| c19_distill | evalhalf85 | 64 | 2.0 | 0.094 | 0.156 | +0.062 | 10 | 0.156 | 2 | 8 |
| c11n | full152 | 152 | 2.0 | 0.500 | 0.579 | +0.079 | 88 | 0.579 | 64 | 24 |
| c14d | full152 | 152 | 2.0 | 0.467 | 0.579 | +0.112 | 88 | 0.579 | 54 | 34 |
| c13t | full152 | 152 | 2.0 | 0.497 | 0.572 | +0.076 | 87 | 0.572 | 64 | 23 |
| c15n512 | full152 | 152 | 2.0 | 0.507 | 0.559 | +0.053 | 85 | 0.559 | 69 | 16 |
| c14b | full152 | 152 | 2.0 | 0.457 | 0.526 | +0.069 | 80 | 0.526 | 59 | 21 |
| c17 | full152 | 152 | 2.9 | 0.446 | 0.526 | +0.080 | 83 | 0.546 | 48 | 35 |
| c11t | full152 | 152 | 2.0 | 0.444 | 0.520 | +0.076 | 79 | 0.520 | 56 | 23 |
| c9e | full152 | 152 | 2.0 | 0.385 | 0.461 | +0.076 | 70 | 0.461 | 47 | 23 |
| c9ae | full152 | 152 | 2.0 | 0.362 | 0.441 | +0.079 | 67 | 0.441 | 43 | 24 |
| c9all | full152 | 152 | 2.0 | 0.345 | 0.434 | +0.089 | 66 | 0.434 | 39 | 27 |
| c9a | full152 | 152 | 2.0 | 0.352 | 0.414 | +0.062 | 63 | 0.414 | 44 | 19 |
| c8 | full152 | 152 | 4.0 | 0.324 | 0.413 | +0.089 | 74 | 0.487 | 25 | 49 |
| anchor | full152 | 152 | 3.0 | 0.327 | 0.412 | +0.086 | 68 | 0.447 | 29 | 39 |
| c9ae_t7 | full152 | 152 | 5.0 | 0.320 | 0.399 | +0.079 | 71 | 0.467 | 23 | 48 |
| c11tc | full152 | 152 | 3.0 | 0.289 | 0.366 | +0.077 | 61 | 0.401 | 26 | 35 |
| c9ae_t5 | full152 | 152 | 3.0 | 0.279 | 0.360 | +0.081 | 61 | 0.401 | 24 | 37 |
| c6a_t5 | full152 | 152 | 3.0 | 0.268 | 0.357 | +0.090 | 61 | 0.401 | 20 | 41 |
| c18_e2lora | full152 | 151 | 2.0 | 0.166 | 0.225 | +0.060 | 34 | 0.225 | 16 | 18 |
| c11t_cap | trainhalf67 | 67 | 6.0 | 0.438 | 0.536 | +0.099 | 42 | 0.627 | 12 | 30 |

## Secondary paired comparisons

| cand | vs | pop | n pairs | cand | base | Δ [95% CI] | W/L | sign p | seeds |
|---|---|---|---|---|---|---|---|---|---|
| c14b | c8 | full152 | 304 | 0.457 | 0.309 | +0.148 [+0.092,+0.204] | 57/12 | 0.000 | 1,2 |
| c14c | c8 | full152 | 152 | 0.441 | 0.303 | +0.138 [+0.072,+0.204] | 26/5 | 0.000 | 1 |
| c14d | c8 | full152 | 304 | 0.467 | 0.309 | +0.158 [+0.105,+0.207] | 58/10 | 0.000 | 1,2 |
| c14p | c8 | full152 | 19 | 0.421 | 0.158 | +0.263 [+0.105,+0.474] | 5/0 | 0.062 | 1 |
| c17 | c8 | full152 | 437 | 0.449 | 0.323 | +0.126 [+0.082,+0.173] | 72/17 | 0.000 | 1,2,3 |
| c16 | c8 | evalhalf85 | 170 | 0.400 | 0.382 | +0.018 [-0.053,+0.094] | 17/14 | 0.720 | 1,2 |
| c19_distill | c8 | evalhalf85 | 128 | 0.094 | 0.391 | -0.297 [-0.391,-0.203] | 1/39 | 0.000 | 1,2 |
| c9e_evalhalf | c9ae_evalhalf | evalhalf85 | 170 | 0.424 | 0.359 | +0.065 [+0.006,+0.129] | 20/9 | 0.061 | 1,2 |
| c9e | c9ae | full152 | 304 | 0.385 | 0.362 | +0.023 [-0.026,+0.069] | 29/22 | 0.401 | 1,2 |
| c17 | c11t | full152 | 304 | 0.444 | 0.444 | +0.000 [-0.056,+0.056] | 30/30 | 1.000 | 1,2 |
| c11t | c9ae | full152 | 304 | 0.444 | 0.362 | +0.082 [+0.023,+0.138] | 46/21 | 0.003 | 1,2 |
| c9ae_t5 | c9ae | full152 | 304 | 0.280 | 0.362 | -0.082 [-0.125,-0.039] | 13/38 | 0.001 | 1,2 |
| c9ae_t7 | c9ae | full152 | 304 | 0.322 | 0.362 | -0.039 [-0.082,+0.003] | 18/30 | 0.111 | 1,2 |
| anchor | c6a_t5 | full152 | 456 | 0.327 | 0.268 | +0.059 [+0.007,+0.114] | 66/39 | 0.011 | 1,2,3 |

## C8 baseline reconciliation

| C8 seed (full152) | n | solved | rate |
|---|---|---|---|
| s1 | 152 | 46 | 0.303 |
| s2 | 152 | 48 | 0.316 |
| s3 | 152 | 54 | 0.355 |
| s4 | 152 | 49 | 0.322 |

| pooled set | n | solved | rate |
|---|---|---|---|
| s1 | 152 | 46 | 0.303 |
| s1+s2 | 304 | 94 | 0.309 |
| s1+s2+s3 | 456 | 148 | 0.325 |
| s1+s2+s3+s4 | 608 | 197 | 0.324 |
| all seeds, evalhalf85 ids only | 340 | 134 | 0.394 |

C8 rate as seen by each paired comparison (base rate restricted to that candidate's matched pairs):

| comparison | C8 rate on pairs | n pairs | seeds paired |
|---|---|---|---|
| c14p [full152] | 0.158 | 19 | 1 |
| c11t_cap [trainhalf67] | 0.254 | 134 | 3,4 |
| c10 [full152] | 0.303 | 152 | 1 |
| c14c [full152] | 0.303 | 152 | 1 |
| c15t1024 [full152] | 0.303 | 152 | 1 |
| c15t512 [full152] | 0.303 | 152 | 1 |
| c16_e2lora [full152] | 0.303 | 152 | 1 |
| c9b [full152] | 0.303 | 152 | 1 |
| c9c [full152] | 0.303 | 152 | 1 |
| c9d [full152] | 0.303 | 152 | 1 |
| c11n [full152] | 0.309 | 304 | 1,2 |
| c11t [full152] | 0.309 | 304 | 1,2 |
| c13t [full152] | 0.309 | 304 | 1,2 |
| c14b [full152] | 0.309 | 304 | 1,2 |
| c14d [full152] | 0.309 | 304 | 1,2 |
| c15n512 [full152] | 0.309 | 304 | 1,2 |
| c9a [full152] | 0.309 | 304 | 1,2 |
| c9ae [full152] | 0.309 | 304 | 1,2 |
| c9all [full152] | 0.309 | 304 | 1,2 |
| c9e [full152] | 0.309 | 304 | 1,2 |
| c18_e2lora [full152] | 0.310 | 303 | 1,2 |
| c17 [full152] | 0.323 | 437 | 1,2,3 |
| c9ae_t7 [full152] | 0.324 | 608 | 1,2,3,4 |
| anchor [full152] | 0.325 | 456 | 1,2,3 |
| c11tc [full152] | 0.325 | 456 | 1,2,3 |
| c6a_t5 [full152] | 0.325 | 456 | 1,2,3 |
| c9ae_t5 [full152] | 0.325 | 456 | 1,2,3 |
| c16 [evalhalf85] | 0.382 | 170 | 1,2 |
| c9ae_evalhalf [evalhalf85] | 0.382 | 170 | 1,2 |
| c9e_evalhalf [evalhalf85] | 0.382 | 170 | 1,2 |
| c19_distill [evalhalf85] | 0.391 | 128 | 1,2 |

**Why C8 shows 0.303 / 0.309 / 0.310 / 0.323 / 0.325 in different reports.** `px_report.py` prints, for every candidate, the
C8 rate *on that candidate's matched (task, seed) pairs*, and C8 seeds were added over time (s1, s2, s3, then s4), so the
"C8 baseline" quoted in each STATE.md entry is a different subset:

* **0.303** = C8 seed 1 alone (46/152): the base for every single-seed candidate (C9b, C9c, C9d, C10, C15t512, C15t1024, C14c).
* **0.309** = C8 s1+s2 (94/304): the base for 2-seed candidates (C9a, C9ae, C11n, C11t, ...) — e.g. "c8 0.309 vs anchor" (10:40).
* **0.310** = C8 s1+s2 restricted to the pairs C18 had completed (297 then, 303 now) — "C18 0.175 vs C8 0.310".
* **0.323** = C8 s1+s2+s3 restricted to the 437 pairs C17 has (C17 s3 is partial) — the C17 "+0.126/+0.137 vs C8" line.
* **0.325** = C8 s1+s2+s3 (148/456) — the 20:40 calibration entry ("c8 0.325") and the base for every 3-seed candidate
  (anchor, C6a_t5, C9ae_t5, C11tc); while C9ae_t5 was still incomplete (n=427) the same pairing printed 0.321.
* **0.324** = all four C8 seeds pooled (197/608), the base for C9ae_t7 (5 seeds; pairs on s1-s4).

Seed 3 is the high run (0.355) and seed 1 the low one (0.303), so the more seeds a comparison pairs on, the higher "C8"
looks; single-seed candidates were all judged against the weakest C8 seed, which inflates their Δ by ~+0.02.
None of these is an error — they are the same data on different pair sets. The per-seed spread (0.303-0.355, SD ≈ 0.02, i.e.
±3 tasks) is the run-to-run noise floor; any claimed gain under ~0.03 on a single seed pair is inside it.

**Recommended canonical C8 baseline.** Quote C8 on full152 as **pooled over all available seeds (s1-s4): 197/608 = 0.324**,
always with the seed list. For decisions use only the **paired Δ on matched (task, seed) pairs** (the table above shows the
matching C8 rate), never a candidate's pass@1 against a differently-seeded C8 number; for eval-half candidates use C8 (all seeds)
restricted to the 85 eval-half ids. Run new candidates on seeds that C8 already has (s1-s4) so every pair is matched.


## Expected 12-hour hidden score (projection)

Expected score = proxy pass@1 × fraction of the 120 hidden tasks finished in 720 min, where fraction =
min(1, 720 / (120 × L4 min/task)). Assumptions: (1) L4 serial min/task measured on Kaggle (30 ids) for C9ae 4.92, C11t 7.67,
C11n 8.69, C15t512 8.97; C9e ≈ C9ae; C17 = 4.92 × 2.11 (A40 serial C17/C9e ratio on the same 30 ids); other candidates
inherit their family's number (column "source"); LoRA serving overhead is ignored. (2) Bundles with `max_time_minutes` are
bounded by the cap. (3) Proxy pass@1 transfers to hidden tasks (it does not in absolute terms: LB 0.13 vs proxy 0.32 for C8 —
use this column for *ranking*), and eval-half pass@1 is on a different, easier/harder set than full152. (4) D28 found the real
scorer run ≥45 % slower than our L4 projection, so the "@1.5×" columns divide the fraction by 1.5. (5) Unfinished tasks score 0;
in practice an uncapped bundle that overruns the notebook limit can score **nothing** (D28 "Kaggle Error"), so fraction < 1 for an
uncapped bundle is a hard-failure risk, not partial credit — cap it before release.

| cand | pop | pass@1 | L4 min/task | source | frac of 120 done in 12 h | exp. score | frac @1.5× safety | exp. @1.5× | status |
|---|---|---|---|---|---|---|---|---|---|
| c9e_evalhalf | evalhalf85 | 0.424 | 4.92 | assumed = C9ae (same root, analyzer cap) | 1.00 | 0.424 | 0.81 | 0.344 | CONTAMINATED: harness conftest/pytest.ini leak in 79/170 pat |
| c16 | evalhalf85 | 0.400 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.400 | 0.81 | 0.325 | CONTAMINATED: harness conftest/pytest.ini leak in 66/170 pat |
| c9e | full152 | 0.385 | 4.92 | assumed = C9ae (same root, analyzer cap) | 1.00 | 0.385 | 0.81 | 0.313 | current daily release |
| c9c | full152 | 0.368 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.368 | 0.81 | 0.300 | pilot |
| c9ae | full152 | 0.362 | 4.92 | Kaggle L4 c9ae-t30s (D25) | 1.00 | 0.362 | 0.81 | 0.294 | LB 0.10 (uncapped zip) |
| c9ae_evalhalf | evalhalf85 | 0.359 | 4.92 | Kaggle L4 c9ae-t30s (D25) | 1.00 | 0.359 | 0.81 | 0.292 | CONTAMINATED: harness conftest/pytest.ini leak in 63/170 pat |
| c9a | full152 | 0.352 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.352 | 0.81 | 0.286 |  |
| c9all | full152 | 0.345 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.345 | 0.81 | 0.281 |  |
| c9b | full152 | 0.336 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.336 | 0.81 | 0.273 | pilot |
| anchor | full152 | 0.327 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.327 | 0.81 | 0.266 |  |
| c8 | full152 | 0.324 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.324 | 0.81 | 0.263 | champion (LB 0.13) |
| c10 | full152 | 0.322 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.322 | 0.81 | 0.262 | pilot |
| c9d | full152 | 0.322 | 4.92 | assumed = C9ae (non-thinking C8 family) | 1.00 | 0.322 | 0.81 | 0.262 | pilot |
| c9ae_t7 | full152 | 0.320 | 4.92 | assumed = C9ae (non-thinking C8 family); 7-min cap bounds tail | 1.00 | 0.320 | 0.81 | 0.260 | 7-min cap |
| c13t | full152 | 0.497 | 7.67 | assumed = C11t (thinking root) | 0.78 | 0.389 | 0.52 | 0.259 |  |
| c14d | full152 | 0.467 | 7.67 | assumed = C11t (thinking root) | 0.78 | 0.365 | 0.52 | 0.244 |  |
| c14b | full152 | 0.457 | 7.67 | assumed = C11t (thinking root) | 0.78 | 0.358 | 0.52 | 0.238 |  |
| c11t | full152 | 0.444 | 7.67 | Kaggle L4 c11t-t30s (D26) | 0.78 | 0.347 | 0.52 | 0.232 | fails L4 time gate (D26) |
| c11tc | full152 | 0.289 | 5.00 | assumed = C11t (thinking root); capped at 5 min | 1.00 | 0.289 | 0.80 | 0.232 | rejected (no gain, 5-min cap) |
| c11n | full152 | 0.500 | 8.69 | Kaggle L4 c11n-t30s | 0.69 | 0.345 | 0.46 | 0.230 | fails L4 time gate (D28 note) |
| c14c | full152 | 0.441 | 7.67 | assumed = C11t (thinking root) | 0.78 | 0.345 | 0.52 | 0.230 | pilot |
| c9ae_t5 | full152 | 0.279 | 4.92 | assumed = C9ae (non-thinking C8 family); 5-min cap bounds tail | 1.00 | 0.279 | 0.81 | 0.226 | LB 0.08 |
| c15n512 | full152 | 0.507 | 8.97 | assumed = C15t512 (lower bound for t1024) | 0.67 | 0.339 | 0.45 | 0.226 |  |
| c6a_t5 | full152 | 0.268 | 4.92 | assumed = C9ae (non-thinking C8 family); 5-min cap bounds tail | 1.00 | 0.268 | 0.81 | 0.218 | LB 0.06 |
| c15t1024 | full152 | 0.454 | 8.97 | assumed = C15t512 (lower bound for t1024) | 0.67 | 0.304 | 0.45 | 0.202 | pilot |
| c15t512 | full152 | 0.447 | 8.97 | Kaggle L4 c15t512-t30s | 0.67 | 0.299 | 0.45 | 0.199 | pilot |
| c17 | full152 | 0.449 | 10.38 | C9e(=C9ae) L4 x A40 serial ratio 2.11 | 0.58 | 0.259 | 0.39 | 0.173 | partial(437/456) |
| c18_e2lora | full152 | 0.165 | 4.92 | assumed = C9ae (LoRA serving overhead unknown) | 1.00 | 0.165 | 0.81 | 0.134 | suspect |
| c14p | full152 | 0.421 | 15.34 | assumed 2 x C11t (two thinking solvers share one GPU) | 0.39 | 0.165 | 0.26 | 0.110 | infra-errors |
| c19_distill | evalhalf85 | 0.094 | 4.92 | assumed = C9ae (LoRA serving overhead unknown) | 1.00 | 0.094 | 0.81 | 0.076 | suspect |
| c16_e2lora | full152 | 0.007 | 4.92 | assumed = C9ae (LoRA serving overhead unknown); 5-min cap bounds tail | 1.00 | 0.007 | 0.81 | 0.005 | suspect |

## Timing references

| run | hw | n | solved | mean min/task (sum of task durations) | wall min/task |
|---|---|---|---|---|---|
| time_c17 | A40 serial CONC=1 | 30 | 13 | 12.67 | – |
| time_c9e | A40 serial CONC=1 | 30 | 13 | 5.98 | – |
| kaggle:c11n-t30s | Kaggle L4 serial | 30 | 13 | 8.70 | 8.96 |
| kaggle:c11t-t30s | Kaggle L4 serial | 30 | 12 | 7.67 | 7.94 |
| kaggle:c15t512-t30s | Kaggle L4 serial | 30 | 13 | 8.98 | 9.52 |
| kaggle:c9ae-t30s | Kaggle L4 serial | 30 | 8 | – | 5.19 |

Public LB: submission_c6a_t5.zip = 0.06, submission_c8_anchorplus.zip = 0.13, submission_2026-10-07_c9ae_editfix_analyzercap.zip = 0.10, submission_2026-10-08_c9ae_t5.zip = 0.08

