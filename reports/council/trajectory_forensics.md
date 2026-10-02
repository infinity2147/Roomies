# Trajectory forensics: why the same agent solves a task in some runs and not others

Author: trajectory-forensics council member · 2026-10-02 · status: analysis complete, nothing committed

## 1. Question

The pilot is 8 scaffold configurations × the same 30 tasks on the Kaggle scorer hardware, so 240 runs in total.
- 4 tasks were solved by all 8 runs.
- 10 tasks were solved by only some runs (stochastic).
- 16 tasks were never solved.

The question is what concretely separates a solved run from a failed one. The answer feeds two decisions:
- (a) which scaffold changes to make next;
- (b) which trajectories to keep for rejection-sampling SFT.

## 2. Data

- **Runs:** `results/kaggle/{c1,c2,c3,c4,c5a,c5b,c6a,c6b}_n30/results/<run>/`. Each has `task_results.jsonl`, an ATIF trace per task, patches and hidden-test outputs.
- **Gold:** gold and test patches are in `data/tasks.jsonl`.
- **Size:** 240 (task, run) rows; 69 resolved and 171 failed.
- **Tool calls:** 8,540 parsed from the traces.

## 3. Method

1. **Per-(task, run) feature table.** `src/analysis/forensics/extract.py` produces `reports/council/trajectory_table.csv` (240 rows × 71 columns). The columns cover:
   - outcome, duration, and tool calls by type;
   - malformed calls, and failed or successful edits;
   - the first read and first edit of a gold file, and the first source edit (seconds since session start);
   - test runs after the edit, repetition loops, and whether `submit_patch` was called;
   - patch files split into src, test, config and scratch, compared with the gold files;
   - patch size against gold size, and the fraction of gold hunks the patch overlaps (±3 lines);
   - hidden-test pass/fail counts and error types;
   - an automatic failure bucket.
2. **Aggregates.** `src/analysis/forensics/stats.py` prints every aggregate quoted below.
3. **Side-by-side reading.** `src/analysis/forensics/render.py <cfg> <task>` renders a compact trajectory.
   - Every failed run of the 10 stochastic tasks (43 runs) was compared with a success on the same task, to find the divergence point.
   - Every failed run of the 16 never-solved tasks (128 runs) was read against the gold patch, the test patch and the hidden-test log.
   - Four parallel readers did this work, and I spot-checked their key claims myself: requests env, httpx env, edit-streak counts and fastapi_14258.
4. **Root-cause labels.** `src/analysis/forensics/labels.py` holds one manual primary label per failed run and asserts that all 171 are covered.
   - Codes: SPEC (spec not inferable), ENV, MALF (tool-call malformation or degenerate loop), TIME, UND (wrong hypothesis), LOC, API (inferable name or usage error), FIXC (incomplete fix), HYG (test edit broke test_patch).
   - The primary label is the first thing which, had it gone right, would most plausibly have flipped the run. It is a judgement, so treat individual labels as ±1 category.

Reproduce:
```
.venv/bin/python -m src.analysis.forensics.extract     # writes reports/council/trajectory_table.csv
.venv/bin/python -m src.analysis.forensics.stats       # all aggregates + per-task matrix
.venv/bin/python -m src.analysis.forensics.labels      # root-cause tallies
.venv/bin/python -m src.analysis.forensics.render c6a fastapi_14258
```

## 4. Results

### 4.1 Headline

1. **9 of the 30 tasks cannot be won by any agent on this harness.** That is 70 of the 171 failed runs (41%).
   - **SPEC, 7 tasks.** The hidden tests need a name, message or file that the issue never states:
     - fastapi_13713 needs kwarg `openapi_external_docs`, but the issue says `external_docs`.
     - fastapi_14258 needs `AssertionError` with an exact message.
     - fastapi_15661 needs a 216-line `scripts/prepare_release.py` with 7 named symbols.
     - fastapi_14953 needs a new `docs_src/json_base64_bytes` module.
     - fastapi_15800 is a ~650-line feature behind an empty PR template.
     - fastapi_14306 needs an `endpoint_ctx=` kwarg in 2 of its 7 tests.
     - rich_4076's whole issue text is "preserve newlines. Fixes #3577".
   - **ENV, 2 tasks.** The hidden tests import a stale installed package instead of the repo `src/` (details below).
   - **Ceiling:** at most 21/30 on this harness. The 8 configs together solved 14 of those 21.
2. **Localization is rarely what separates success from failure.**
   - 149 of 171 failed runs (87%) read a gold file, at a median of 20 s. Successes read it at a median of 21 s.
   - LOC is the primary cause in only 12 of 171 failures (7%).
3. **On the winnable tasks, failures are about process and repair, not finding the code.** In priority order:
   - time or budget runs out after a correct or near-correct diagnosis (TIME, 32);
   - wrong semantic hypothesis, often because a repro did not reproduce (UND, 26);
   - tool-call malformation and degenerate repetition loops (MALF, 14 primary, plus 14 runs where it contributed);
   - incomplete fixes (FIXC, 9);
   - API misuse (API, 4);
   - test-file edits (HYG, 4 primary; already fixed from C4 on).
4. **Within a stochastic task, success versus failure is decided by what happens after localization.**
   - Did the edit call parse?
   - Did the agent commit to an edit before the clock ran out?
   - Did its repro actually reproduce the bug?
   - Did it avoid touching test files?

   The divergence point is almost never "opened the wrong file".

### 4.2 Bucket shares (automatic, from patches and logs; n = 171 failures)

| bucket | n | share | stochastic | never |
|---|---|---|---|---|
| right_file_wrong_fix (gold file in patch, tests fail) | 62 | 36% | 12 | 50 |
| time-limit hit, no source edit | 59 | 35% | 15 | 44 |
| no_patch (submitted empty or budget ran out) | 22 | 13% | 3 | 19 |
| wrong_location (source edit, but not in a gold file) | 15 | 9% | 7 | 8 |
| test_patch_conflict | 10 | 6% | 4 | 6 |
| touched_tests_only / scratch_only | 3 | 2% | 2 | 1 |

**Correction to the earlier triage.**
- About 10 runs the earlier triage labelled "wrong_location" had only `repro.py` and similar scratch files in the patch.
- Those runs never edited source at all, so they really belong in the no-edit groups.

### 4.3 Root-cause labels (manual; `labels.py`)

| scope | SPEC | ENV | TIME | UND | MALF | LOC | FIXC | API | HYG |
|---|---|---|---|---|---|---|---|---|---|
| all failures (171) | 56 | 14 | 32 | 26 | 14 | 12 | 9 | 4 | 4 |
| stochastic tasks (43) | 0 | 0 | 9 | 12 | 10 | 3 | 1 | 4 | 4 |
| never-solved (128) | 56 | 14 | 23 | 14 | 4 | 9 | 8 | 0 | 0 |
| thinking-on configs (127) | 42 | 10 | 29 | 16 | 7 | 7 | 8 | 4 | 4 |
| thinking-off configs C5b and C6a (44) | 14 | 4 | 3 | 10 | 7 | 5 | 1 | 0 | 0 |

The two kinds of config fail differently:
- **Thinking-on configs mostly fail on TIME.** The model deliberates for 60–160 s between calls and the 8-minute limit expires.
- **Thinking-off configs mostly fail on UND and MALF.** They give up ("no bug found") or loop.

### 4.4 Gold-file contact among the 171 failures

- **Read a gold file:** 149/171. Never read one: 22/171.
- **Made at least one successful edit to a gold file:** 73/171.
- **Gold file in the final patch:** 72/171.
- **Patch overlaps at least one gold hunk:** 62/171. Overlaps all gold hunks: 22/171.

Of the 22 failures that covered every gold hunk:
- fastapi_14258: 7 runs; right place and idea, but the exception type and message are not inferable.
- requests_7309: 8 runs; ENV.
- rich_3043 c1/c2 and fastapi_14492 c1/c2: correct fix, broken by test-file edits.
- rich_2725 c3: an over-fix.
- rich_3521 c6a: half the fix.

**So the agent reaches the gold file but writes the wrong fix in 62 of 171 failures (36%).** About 15 of those 62 are SPEC or ENV cases where the fix was right or nearly right.

### 4.5 Timing (seconds since session start; median [IQR])

| group | first gold read | first source edit | duration |
|---|---|---|---|
| success (n=69) | 21 [16–37] | 104 [62–184] | 250 [170–396] |
| failure (edited n=96) | 20 [15–30] | 207 [88–310] | 483 [331–488] |
| thinking-on success / failure | – | 116 / 219 | 261 / 485 |
| thinking-off success / failure | – | 62 / 52 (only 17/44 failures ever edit) | 101 / 239 |

**Success rate by when the first source edit happened (all 240 runs):**

| first edit at | success rate |
|---|---|
| < 60 s | 15/27 (56%) |
| 60–120 s | 25/45 (56%) |
| 120–180 s | 11/23 (48%) |
| 180–240 s | 10/24 (42%) |
| 240–300 s | 2/14 (14%) |
| ≥ 300 s | 6/32 (19%) |
| **never** | **0/75** |

- 75 of the 171 failures (44%) never made a successful source edit. 61 of those 75 never even tried `edit_file`.
- **Caveat:** this pattern is partly confounded by task difficulty. Within stochastic tasks the success-vs-failure medians do not separate cleanly (per-task table in `stats.py` output).
- **The robust part is the "never edited" mass.** It is pure loss, and it sits mostly in TIME runs (thinking on) and loops or give-ups (thinking off).

**Tool calls in successful runs:**
- median 23; 46 of 69 used ≤ 30 calls.
- success rate falls with call count: 49% for < 20 calls, 35% for 20–30, 21% for 30–45, 10–15% above 45.

### 4.6 Verification (ran pytest, tests.py or check.py after the first edit)

| sample | verified | not verified |
|---|---|---|
| all 165 runs with an edit (raw) | 32/57 (56%) | 37/108 (34%) |
| stochastic tasks only | 10/16 (62%) | 27/50 (54%) |

- **Task-stratified (Mantel–Haenszel-weighted) difference, verified minus unverified, within stochastic tasks: −0.16.**
- **Conclusion: no evidence that running tests per se causes success.** The raw gap comes from easy tasks being both verified and solved.
- What mattered in the trajectories was whether the repro actually reproduced the issue. Non-reproducing repros were the proximate cause of these UND failures:
  - fastapi_15589: 5 runs tested scalar `Header()`, which already works, and concluded "already works".
  - rich_4077 c4 and c5a: the probe class lacked the `io.TextIOBase` base that causes the bug.
  - fastapi_14419 c2, c5b and c6a.
  - fastapi_14430: all runs.

### 4.7 Tool-call malformation (a newly quantified failure mode)

- **Scale:** across 8,540 calls, there were **634 `edit_file`/`write_file` calls rejected for a missing mandatory argument, against only 518 successful edits.**
- **Cause:** 523 of the 612 rejected `edit_file` calls (85%) end `new_string` with a stray backtick followed by the next key, as in `` ...objects = ("",)`,old_string: ``. The model closes the string with a backtick instead of the proper string delimiter, the parser swallows `old_string`, and the call fails.
- **Trigger:** this happens far more often when the text contains triple-backtick fences. fastapi's `Doc()` docstrings contain them, which is why fastapi_13713 hits it in 5 of 8 runs.
- **Same failure on reads:** `"filepath": "rich/console.py`,start_line:960,end_line:980"`, and keys such as `start_line"`.
- **Streaks:** 34 runs had ≥ 5 failed edits in a row; 13 of them still resolved, usually by switching to `sed`.

The worst streaks:

| run | consecutive failed edits | outcome |
|---|---|---|
| fastapi_14258 c6a | 96 (calls 7–107) | timeout; the fix idea was correct |
| fastapi_14605 c1 | 47 | params.py never edited, so 10 hidden tests "DID NOT WARN" |
| fastapi_14605 c5b | 52 | as below |
| fastapi_14605 c6b | 36 | ended with a `sed` that produced `FastAPIFastAPIDeprecationWarning` |
| fastapi_13537 c5b | 11 | the correct visited-set fix never landed |

**Over-escaping** is a second variant: literal `\"\"\"` written into source.
- It causes `SyntaxError` in fastapi_14605 c5b and c6a, and fastapi_14306 c3.

**Seven submitted patches did not import at all:**
- SyntaxError ×3;
- `NameError: Dict` (14306 c4);
- `NameError: Json` (14616 c5b);
- a circular import (14605 c5a);
- `FastAPIFastAPIDeprecationWarning` (14605 c6b).

### 4.8 Degenerate repetition (the same tool and arguments issued ≥ 5 times in one run)

| config | runs with a loop | share of all calls that are duplicates |
|---|---|---|
| c1, c2, c3, c4, c5a, c6b | 3–8 / 30 | 11–17% |
| **c5b (thinking off)** | **20/30** | **48%** |
| **c6a (thinking off, frozen)** | **19/30** | **56%** |

- Example, c6a fastapi_14246: `grep -rn "response_model" fastapi/ | grep "nested"` was issued about 60 times, then an empty patch was submitted.
- Example, c6a rich_2725: 54 identical greps.
- Runs with a loop succeed 13/68 (19%); runs without one succeed 56/172 (33%).
- **C6a's "same accuracy, 34% faster" hides a large problem.** More than half of its tool budget is spent on literal repeats, and its failures are early give-ups: 7 empty submissions. It is fast because it gives up.
- Sampling is temperature 0.3 with thinking off (`submissions/c6a/configs/sampling.yaml`).
- **Hypothesis:** the low temperature with thinking off drives the loops. Not tested.

### 4.9 Hygiene

- **test_patch conflicts:** 10 runs, all on requests_7309, fastapi_14492, rich_3043 and fastapi_14953.
  - In 4 of them (14492 c1/c2, 3043 c1/c2) the source fix was correct, and the agent's test edit was even identical to the gold test hunk.
  - C4, C5a and C6b had 0 conflicts. C5b and C6a had 1 each, on tasks that could not be won anyway.
  - The C4 `check.py` fix works when it is called. **This is mostly solved.**
- **Prompt contradiction:** the prompt says "put scratch scripts in /tmp", but `write_file` to `/tmp` is rejected with "Path traversal detected".
  - That happened 144 times.
  - Agents then write `repro.py` into the workspace, which leaks into patches: 5 of 69 successes and 24 of 171 failures.
- **Hygiene of successful patches:** 15 of 69 are not clean.
  - Root-level test files: 10.
  - `repro*.py`: 5.
  - `.pre-commit-config.yaml`: 1.
  - fastapi_14616 c4 also leaves `print("DEBUG…")` in library code.

### 4.10 The environment problem (verify before trusting any requests or httpx number)

- **requests_7309.**
  - All 8 runs edited the gold hunk, and the c4 patch is semantically equal to gold.
  - With the patch applied, the hidden tests import `/usr/local/lib/python3.12/dist-packages/requests/utils.py`, not `src/requests`. This was verified in `results/kaggle/c4_n30/.../test_outputs/requests_7309.log:348`.
  - Result: `6 failed, 201 passed`. One of the failures is unrelated to the fix.
- **httpx_3672.**
  - All 7 patched runs fail at collection with `module 'httpx' has no attribute 'Stream'. Did you mean: 'stream'?`, which means the installed httpx was imported.
  - A reader re-ran the hidden tests locally with `PYTHONPATH=src`: c1, c3, c5a, c5b, c6a and c6b pass all 24, and c4 fails 1.
  - Per that reader, gold and empty patches collect normally in `verify_gold`. That suggests a patch-dependent shadowing in the harness (hypothesis).
- **Implication.** If the official scorer behaves like our Kaggle harness, src-layout repos are unwinnable for everyone. requests is 13 of the 129 public tasks.
  - If it does not, our measured pass@1 understates true performance by up to about 1.25 tasks per run (10 runs that were effectively correct, out of 8 configs).
  - **Action:** run `verify_gold` and a known-good non-gold patch for every requests and httpx task on the Kaggle kernel.

## 5. Per-task divergence notes

Each line gives the failing config, the call number and the elapsed time.

### Stochastic tasks

- **fastapi_13537 (7/8).** c5b had the correct visited-set fix in `new_string` at call 9 (88 s), but the call was backtick-terminated, so `old_string` was lost. 11 retries failed the same way, then timeout. Only `repro.py` reached the patch, and the hidden tests show `assert 422 == 200`. **MALF.**
- **fastapi_14492 (6/8).**
  - c1 at call 7 (47 s) found `"identifier": "MIT"` in a test and said "I should probably fix it there too". It edited the test, and the test patch failed to apply. c2 did the same at call 15.
  - The successful c3 found the same test at call 13, quoted the "never edit tests" rule, and left it alone. **HYG.**
- **rich_2725 (6/8).**
  - c3, call 10 (159 s): "change box_segments order **and change this line to use header_row and footer_row**". The extra index change broke the rows without header or footer (3 failures in `test_placement_table_box_elements`). **UND (over-fix).**
  - c6a: a `"start_line\""` key at call 5 was repeated 9×, then 54 identical greps, then an edit in the wrong file `box.py`. **MALF to LOC.**
- **rich_3043 (5/8).**
  - c1 and c2 fixed the template correctly, then saw `test_console.py` fail on the old expected HTML. They decided the "tests assert the WRONG HTML" and edited them, so the test patch failed to apply. **HYG.**
  - c5b repeated a no-op edit (`old_string == new_string`) about 22× until budget pressure, then only deleted `<html>` without moving it. **MALF to FIXC.**
- **rich_4077 (4/8).** The successful c6a ran `grep FileProxy` at call 7 and copied the sibling `isatty` pattern from `progress.py`; the edit was at 50 s.
  - c3, call 3: "the issue title suggests that **Console** should have an isatty() method". It never opened `file_proxy.py`. **LOC.**
  - c4 and c5a built probe classes without the `io.TextIOBase` base. The probes "proved" proxying works, and the runs timed out (c5a found the cause at 448 s). **TIME after a bad probe.**
  - c1 drifted to unwrapping `Console.file`. **UND.**
- **fastapi_14419 (3/8).**
  - c4's repro (call 12, 296 s) inverted the semantics: it added child scopes to the cache key, and the tests show `assert 2 == 1`.
  - c2 and c5b concluded "already cached" from repros that did not show the bug.
  - c6a rewrote a buggy repro 9× and never edited.
  - c6b emitted a giant repro inside one tool call that was truncated at the token limit. **UND / TIME / MALF.**
- **fastapi_14605 (2/8).** This task needs edits across 7 files. Every run saw `params.py` in its first grep, and 5 of the 6 failures are MALF:
  - c1: 47 consecutive malformed edits;
  - c4: 14 consecutive malformed edits;
  - c6b: 36 consecutive malformed edits, then `sed` produced `FastAPIFastAPIDeprecationWarning`;
  - c5b and c6a: literal `\"\"\"` written into the source, giving a SyntaxError.

  c5a created a circular import (`from fastapi import … FastAPIDeprecationWarning` inside `fastapi.dependencies.utils`). Not one failing run ever imported the package after editing.
- **fastapi_14616 (2/8).** Pydantic stores a `Json()` *instance* in `metadata`, so `Json in metadata` is False.
  - The successful c4 probed this first (call 17: `m is Json → False`; call 21: `isinstance(m, Json) → True`), and only then edited.
  - c1, c3 and c5a wrote `Json in …metadata` without checking. c5a's own later probe printed False, but the budget was gone. **API.**
  - c2 and c5b worked on the wrong code path (they assumed an `Annotated` annotation). **UND.**
- **fastapi_15589 (1/8).** The trap: a scalar `Header()` already rejects underscores.
  - c1 switched to a BaseModel repro at call 13 (344 s), got "BINGO", and edited the exact gold line at 460 s.
  - c2, c3, c5b and c6a stopped at the passing scalar repro, or chased alias code. **UND.**
  - c4 and c6b identified the right loop but ran out of time. **TIME.**
  - c5a's plan named the extra-keys loop, but the edit landed in the scalar loop at 490 s. **FIXC.**
- **rich_4075 (1/8).** Several runs had the right diagnosis (`objects = (NewLine(),)` when there are no objects) by 39–67 s.
  - c1 and c4 then traced `Text.render` with 100–160 s thinking gaps and never edited. **TIME.**
  - c6b planned the exact fix at 400 s; 6 backtick-malformed edits followed, then timeout. **MALF.**
  - c5b and c6a were sent to `Text.split` by `locate.py` and looped 30–70×. **LOC.**
  - The one success, c3, landed the fix through `sed` after 9 malformed edits.

### Never-solved tasks: classification and whether a run was close

| task | root cause | closest run | what would have flipped it |
|---|---|---|---|
| fastapi_15661 | SPEC (empty template; needs 7 named symbols) | c3 guessed the right filename | nothing inferable |
| rich_4076 | SPEC (no issue body); no run opened `rich/ansi.py` | – | the issue text |
| fastapi_14258 | SPEC: tests need `AssertionError` + exact message; 7/8 runs raised `FastAPIError` in the gold hunk | all (overlap 1.0) | the message; c6a was also a 96× MALF loop |
| fastapi_13713 | SPEC: kwarg `openapi_external_docs` vs the issue's `external_docs`; plus MALF in 5/8 (Doc docstrings with ``` fences) | c1, c6b: complete apart from the name | – |
| fastapi_14953 | SPEC: tests import an unmentioned `docs_src` module | c3, c4: 188 pass / 4 error | – |
| fastapi_15800 | SPEC: ~650-line API, empty template | c3: 14/60 | – |
| fastapi_14306 | SPEC (2/7 tests); also escaping SyntaxError (c3), missing import (c4), MALF (c6b) | c3 (0.42 overlap) | 5/7 at best |
| requests_7309 | ENV (stale site-packages); also HYG in 4 runs | c4 = gold-equivalent | harness fix |
| httpx_3672 | ENV (installed httpx imported) | 6 runs pass with `PYTHONPATH=src` | harness fix |
| fastapi_14448 | FIXC: misses the second hunk, the generator-branch order in `_solve_generator` | c5a: 26 pass / 2 fail; single edit at 438 s, no time to test | one test run after the edit |
| fastapi_14246 | TIME (c2, c3, c6b) / UND (c4, c5a misread it as serialization) | c3 stated the gold idea at 446 s, timeout 487 s | about 60 s more, or fewer wasted greps |
| fastapi_14430 | LOC: everyone anchored on `shared.py`, where `UnionType` is already handled | – | `grep -rn "is Union"` |
| fastapi_14371 | FIXC/UND: overloaded `.alias` instead of a separate validation alias | c1, c5a: 728 pass / 16 fail | run existing xfail tests with `--runxfail` (the issue points at them) |
| rich_3772 | UND: 4 runs read "recursion" as a re-entrant excepthook | c1 wrote a `__cause__ = self` repro at 387 s, saw the hang, then the session ended | the cycle hypothesis about 150 s earlier |
| rich_3506 / rich_3521 | TIME: 13 of 16 runs timed out after only 12–23 calls, hand-simulating cell widths in thought | 3521 c6a: 50/59 (half the fix) | a brute-force check over all split positions; `pos = 0` passes all hidden tests of both tasks (verified locally by a reader) |

## 6. Recommendations

### (a) Scaffold and prompt interventions, ranked by estimated tasks gained per 30-task run

Method for the estimates:
- Count the failed runs, across the 8 configs, whose primary or secondary label an intervention addresses, and divide by 8 to get runs per config.
- Multiply by an assumed flip probability, stated for each row.
- One standard error on 30 tasks is about ±2.5, so **no single intervention below is detectable in one n=30 run**. Validate them as a bundle on n ≥ 60, or on paired task × seed.

| # | intervention | addressable runs (of 171) | flip prob. | est. gain per run | evidence |
|---|---|---|---|---|---|
| 1 | **Commit-and-iterate time box** for thinking-on configs: first edit by about 40% of the time budget; "when stuck on arithmetic or semantics, write a brute-force/property check in /tmp instead of reasoning"; cap thinking per turn | TIME 32 (29 in thinking-on) | 0.3 | **+1.0 to +1.2** | 0/75 runs with no edit succeed; 2/14 and 6/32 succeed with first edit ≥ 240 s, against 56% before 120 s; rich_3506/3521 (14 runs) are fixed by a one-line change a brute-force check reveals; 4075, 4077, 15589, 14246 had the diagnosis and ran out of time |
| 2 | **Edit-robustness fallback**: "if `edit_file` returns *missing old_string* once, never retry the same call; apply the edit with `run_command` + `python3 - <<'EOF'` (read, `str.replace`, assert count == 1, write)", or a one-argument skill script that takes a JSON or diff payload; and "never put ``` fences or backticks inside `new_string`; avoid editing Doc() docstrings" | MALF 14 primary + 14 secondary | 0.5 primary, 0.15 secondary | **+0.8 to +1.0** | 634 rejected vs 518 successful edits; the single-string `run_command` route rescued rich_4075 c3 and others (13 of the 34 long-streak runs still resolved, mostly via `sed`); 14605 alone lost 5 runs |
| 3 | **Anti-repetition for thinking-off configs (C6a)**: a prompt rule ("never issue the same command twice; if a grep returns nothing, change the pattern or read the file"), raise temperature to about 0.7–1.0 (Gemma's default is 1.0), and treat duplicate calls as a signal to edit or submit | c5b/c6a: 39 of 60 runs loop; UND and LOC give-ups 15 | 0.25 | **+0.5 to +1.0 for C6a** | 56% of C6a's calls are duplicates; loop runs succeed 19% vs 33%; 7 C6a empty submissions. *Hypothesis: temperature is the lever; test on 30 tasks × 2 seeds* |
| 4 | **"Repro must fail first" + probe-before-assume**: write a repro that FAILS on the unmodified code before editing; if it passes, the hypothesis is wrong (change the input shape, e.g. model vs scalar). Check type facts in Python (`isinstance`, `in`) before relying on them | UND 26 + API 4 | 0.15 | **+0.4 to +0.6** | 15589 (5 runs), 14419 (3), 4077 (2), 14616 (3 API), 14430 (8): all derailed by passing repros or unverified assumptions; the successes on 14616 c4 and 15589 c1 did exactly this |
| 5 | **Post-edit import check, then the relevant test**: `python -c "import <pkg>"` plus the most relevant existing test file (made mandatory through `check.py` before `submit_patch`). This also keeps the existing test-revert and scratch cleanup | 7 non-importing patches + FIXC 9 + residual HYG | 0.2 | **+0.3** | 14605 c5a/c5b/c6a/c6b, 14306 c3/c4 and 14616 c5b submitted code that does not import; 14448 c5a's one failing branch shows up in the first test run |

Also do these (no direct task gain on this set, but they are cheap and remove noise):
- **Fix the /tmp contradiction.** Either "write /tmp files with `run_command` heredocs" or allow `write_file` to /tmp. This removes 144 wasted calls and the `repro.py` leakage.
- **Settle the ENV question first.** It is worth up to +1.25 measured tasks per run on this set, and it decides whether requests and httpx tasks are worth anything at all.
- **Do not spend more effort on localization for this pilot.** LOC is 7% of failures (detail in 6c).

The combined realistic target is about +2.5 to +3.5 tasks per run. That would move pass@1 from about 9/30 to about 12/30, against a ceiling of 21/30 on this harness. These estimates assume the effects are largely additive, which is optimistic because TIME, MALF and loops overlap.

### (b) Selecting trajectories for rejection-sampling SFT

**Funnel on this pilot** (from `stats.py`):

| step | runs | tasks |
|---|---|---|
| resolved | 69 | 14 |
| no test, config or scratch file in the final patch | 54 | 13 |
| no test-file edit anywhere in the trajectory | 50 | 13 |
| no degenerate loop | 42 | 10 |
| submitted, not harvested at the time limit | 36 | 10 |
| ≤ 40 calls | 34 | 9 |
| zero malformed calls | 24 | 8 |

**Hard filters (reject the trajectory):**
1. Resolved, by the hidden tests on the scorer harness.
2. The final patch touches only non-test source. No `tests/` files, root `test_*.py`, configs, `repro*`/`debug*` scratch files, or `print("DEBUG` lines. Alternatively, sanitize the patch and drop the trajectory if the trajectory itself depends on those files.
3. No test-file edit anywhere in the trajectory, even if reverted. Otherwise we teach the behaviour that cost 4 correct fixes.
4. No degenerate repetition: any identical tool call more than twice means reject.
5. Ended with `submit_patch` before the time limit. Harvested-at-timeout successes such as rich_4077 c2 and c6b, or 14301 c1/c2, teach dawdling.
6. The agent did not submit after its own check printed a failure. Example: fastapi_14616 c6a submitted right after its repro printed "Test failed".

**Handling malformed calls (mask, don't filter):**
- Filtering on zero malformed calls cuts the set to 24 runs and 8 tasks.
- Instead, keep the trajectory, but give the malformed assistant turns and their error observations zero loss.
- Alternatively, drop the failed call/observation pair and re-render the following prompts. The captured per-call prompts make this feasible (see BRIEF finding 5).
- SFT on correctly formatted `edit_file` calls is itself the most direct cure for MALF.

**Soft preferences (for ranking and weighting):**
- first source edit ≤ 200 s;
- ≤ 30 calls;
- a repro that fails before the fix and passes after, or a run of an existing test;
- a minimal diff (agent/gold size ratio ≈ 1; the success median is 1.0).

**Balance:**
- Cap at 2 trajectories per task, and up-weight stochastic tasks.
- The 4 always-solved tasks are 1–5-line fixes (median gold size 2 lines) and would otherwise dominate the set: 32 of the 69 successes.

**Good exemplars identified by reading:**
- fastapi_13537 c6a: edit at 81 s, ad-hoc check, submit at 134 s.
- rich_4077 c6a: sibling-pattern reuse, test run, submit at 69 s. Mask its 5 malformed reads.
- rich_2725 c4: reverted the edit to confirm the bug, re-applied it, deleted the repro.
- fastapi_14492 c3 and c5a: refused to edit the test.
- fastapi_14616 c4, for its probing behaviour only. Its patch must be sanitized: DEBUG prints and junk files.
- fastapi_15589 c1: model repro, then the gold-identical line. The edit came at 460 s, so down-weight it.

**Not exemplars:**
- rich_4075 c3: 9 malformed edits, an unrequested `log()` change, no tests.
- fastapi_14605 c3: 28 malformed calls.
- fastapi_14616 c6a.

**Data volume is the binding constraint.** This pilot yields only about 20–30 usable trajectories on about 10 tasks. Use the C6a×4 and B0×2 runs on 107 tasks, plus the mined and synthetic tasks, with the same filters.

### (c) What the remaining errors say about localization versus repair

- **Localization is largely solved for this model on these repos.**
  - 87% of failed runs read the gold file, and they did so as early as successes did (about 20 s).
  - Only 12 of 171 failures are LOC-primary. They come from 4 tasks: 14430 ×8, rich_4077 c3, rich_4075 c5b/c6a, rich_2725 c6a.
  - Even in those, an exact-pattern grep would have found the code: `grep "is Union"` for 14430, `grep FileProxy` for 4077.
  - This agrees with the council finding that the BM25 ranker ≈ LambdaMART (MRR about 0.40) and that improving it has little end-to-end headroom.
- **The capability gap is repair under a budget.** It has three parts:
  1. **Execution reliability:** malformed edit calls, loops, and code that does not import. These are fixable by scaffold, and SFT on clean tool calls should help.
  2. **Hypothesis testing:** non-reproducing repros, inverted semantics, over-fixes and API assumptions. Partly fixable by prompt (repro-must-fail-first); otherwise this is what RL or expert iteration should target.
  3. **Time management:** correct diagnoses that never become an edit. Fixable by scaffold and by cheaper thinking.
- **About 41% of observed failures are unwinnable (SPEC or ENV).** The public pilot therefore understates the share of the remaining winnable failures that are process errors. Any per-config comparison should report scores on the 21 winnable tasks, or exclude SPEC tasks, to cut noise.

## 7. Open questions

1. **ENV.** Does the official Kaggle scorer import installed `requests`/`httpx` instead of the repo `src/`? Run `verify_gold` plus one known-good alternative patch per requests and httpx task on the kernel. Why do gold patches collect but agent patches do not on httpx (hypothesis: patch-dependent install refresh)?
2. **Temperature and repetition.** Do the C6a loops disappear at temperature 0.7–1.0, or with a presence penalty, if `generate_content_config` passes it through? Test 30 tasks × 2 seeds; this is cheap.
3. **Malformed-call trigger.** Is the backtick terminator triggered by argument order (`new_string` before `old_string`), or only by fenced content? A local replay of the 612 failing generations against the vLLM Gemma parser would tell us whether a parser-side repair is possible. That would need GPU time; not done here.
4. **SPEC prevalence.** Is the SPEC share (7/30 here) representative of the hidden set? If so, a model that guesses names from repo conventions could matter, e.g. 14258 copying the neighbouring `assert` style, or 13713 copying the `openapi_*` kwarg prefix. Both were weakly inferable from local conventions, and neither was used.
5. **Causal check.** Item 4.5 (early edit leads to success) is observational. The time-box intervention (#1) is the experiment that would confirm it.

## Files

- Code:
  - `src/analysis/forensics/extract.py`: builds the table.
  - `src/analysis/forensics/stats.py`: aggregates.
  - `src/analysis/forensics/render.py`: trajectory viewer.
  - `src/analysis/forensics/labels.py`: manual root-cause labels and tallies.
- Data: `reports/council/trajectory_table.csv` (240 × 71).
