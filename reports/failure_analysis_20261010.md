# C9e trajectory-level failure analysis (2026-10-10)

Scope: every failed run of **C9e** (`px_c9e_s1`, `px_c9e_s2`: 304 runs, 117 resolved, **187 failed**), contrasted with its 117 successes, plus **C17** (`px_c17_s1..s3`: 437 runs, 241 failed) and cross-candidate solve data. `px_c9e_evalhalf_*` was extracted (`results/failure_analysis/c9e_evalhalf_*.jsonl`) but left out of the main numbers because 79 of its 170 patches contain the harness conftest/pytest.ini leak.

Deliverables:
- `src/analysis/failure_c9e.py`: deterministic extractor. It is idempotent and runs in about 15 s per 300 runs.
- `results/failure_analysis/c9e_failures.jsonl`: one row per failed run, holding the signals, `auto_primary`, `auto_secondary`, the `manual_*` labels when the run was sampled, and `primary_final`. `c9e_all.jsonl` covers all runs; `c17_*.jsonl` is the same for C17.
- `results/failure_analysis/manual_labels_sample61.jsonl` and `manual_sample_design.json`: the semantic labels and the sampling design.

## 1. Method

**Deterministic signals.** These are computed for every run.
- **F2P tests.** FAIL_TO_PASS is rebuilt from `results/verify_prajna_proxy_empty/logs` (tests that fail on the base commit). All 152 tasks pass with the gold patch.
- **Hidden-test split.** Hidden failures are split into still-failing F2P tests vs regressions.
- **Gold functions.** AST-enclosing defs of the gold-changed lines at the base commit, read from `data/derived/proxy/repos`. The same mapping is applied to the agent patch, giving "touched gold function".
  - This is noisy at function boundaries: 109 of 117 successes register as touching the gold function.
- **Reading.** Whether the gold file and gold-function lines were read, using `read_file` ranges, `sed -n` and `cat`.
- **Analyzer.** Whether its `LOCATION:` points at the gold file or function.
- **Edit calls.** `edit_file` calls are classed as ok, not-found, or malformed (harness: "mandatory input parameters are not present").
- **Repeats.** Repeated identical tool calls, for the root and the analyzer.
- **Repro and tests.** Repro runs before and after the first mutation, pytest runs after the last mutation and their outcome, and whether the agent ran the test file that the hidden test_patch replaces.
- **Patch checks.** The patch is applied to a copy of the original files and py-compiled, and its test, scratch and doc files are listed.
- **Budget and infra.** Budget/turn/timeout/context errors, plus a serving-stall detector (a gap of more than 15 min with no step, followed by session timeout).
- **Time attribution.** Per-step wall-time deltas are attributed to: analyzer, malformed call, identical repeat, after-submit, or productive.

**Semantic labels.** These come from a stratified sample of 49 C9e failures plus 12 C17 failures.
- Strata are the deterministic `auto_primary` buckets: near-miss 21/104, empty 4/14, overflow 3/15, the small buckets almost fully sampled, and 6 of the 17 stalls.
- Each run was rendered as a digest: issue, gold patch, test patch, agent patch, hidden failures, compressed trajectory.
- Digests were labelled by 6 parallel reader agents with a fixed rubric: primary/secondary codes 1–14, understanding, repro validity, verification, and fixability. I spot-checked several labels, e.g. click_3728 (13: the issue says "sort", the tests want declaration order) and the infra stalls.
- Counts were extrapolated with the stratified estimator Σ_h N_h·p̂_h. The 95% CIs come from a bootstrap that resamples within strata.
  - The CIs cover sampling error only, not labeller error. Treat every semantic label as ±1 adjacent category (4↔5↔2 especially).
- The 8 unsampled "11_budget" runs are counted as 11. The 17 stall runs are forced to **infra** whatever the reader said.

## 2. Headline numbers (C9e, 187 failed runs)

| signal | failed (187) | resolved (117) |
|---|---|---|
| read a gold file / gold-function lines | 172 / 163 | 117 / 117 |
| analyzer LOCATION in gold file / gold function | 151 / 131 | 114 / 110 |
| final patch touches a gold file (of 132 non-empty failed patches) | **128 / 132** | 117 |
| final patch touches a gold function | 121 | 109 |
| gold patch size (lines, median [IQR]) | **27 [12–63]** | 8 [3–15] |
| gold functions touched (median) | 3 (near-misses) | 1 |
| near-misses covering *all* gold functions | 39 / 104 | 87 / 117 |
| empty final patch | 55 | 0 |
| ran the test file that hidden tests replace | 57 (30%) | 83 (71%) |
| last agent pytest after last edit = pass | 58 | 94 |
| wrote a repro / repro "failed" before first edit (heuristic) | 150 / 114 | 116 / 92 |
| median tool calls / duration | 64 / 542 s | 26 / 264 s |
| median analyzer tool calls | 22 | 7 |
| runs with ≥1 malformed `edit_file` | 45 | 18 |

**Localization is not the bottleneck.**
- 128 of 132 non-empty failed patches touch a gold file, and 121 of 187 failures touch a gold function.
- Failures are much larger tasks: the gold patch is about 3× bigger and spans about 3 functions.
- The agent typically fixes one site. Of the 104 near-misses, 31 pass some but not all F2P tests, and only 39 cover every gold function.

## 3. Taxonomy (primary cause, extrapolated to 187)

| code | cause | est. runs | % | 95% CI (sampling only) |
|---|---|---|---|---|
| 4 | correct function, wrong modification | 43 | 23% | 12–35% |
| 5 | incomplete patch (misses a case, site, sibling impl or async twin) | 34 | 18% | 7–29% |
| 13 | hidden requirement not in issue | 23 | 12% | 4–23% |
| 10 | repeated tool-call loops (incl. 15 analyzer context overflows) | 19 | 10% | 8–14% |
| infra | serving stall (17) + test-file edit broke test_patch (1) | 18 | 10% | deterministic |
| 1 | wrong diagnosis | 14 | 7.5% | 2–14% |
| 2 | incorrect API/behaviour assumption | 10 | 5% | 0–13% |
| 11 | time/budget exhaustion (unsampled, deterministic) | 8 | 4% | – |
| 7 | malformed tool calls (primary) | 7 | 3.5% | 0.5–6% |
| 3 | correct file, wrong function | 6 | 3% | 0–7% |
| empty / 6 / 8 | gave up / syntax-import / invalid repro | 3.5 / 3 / 3 | ~2% each | – |
| 14 | genuine localization failure | ≈0 primary (3 secondary) | <2% | – |

Grouped into families (95% CI):
- **Semantic wrong or incomplete fix (1, 2, 4, 5): 54% [43–64%].**
- Process degeneration (7, 10, 11, 12): 18% [14–23%].
- Hidden requirement: 12% [4–23%].
- Infra: 10%.
- Localization: 3%.

**Secondary causes.** These are raw counts in the 49-run sample.
- 10 loops: 19 runs.
- **9 missing or incorrect verification: 18.**
- 11 budget: 14.
- 7 malformed: 8.
- 13 hidden requirement: 7.
- 12 overflow: 6.
- 8 invalid repro: 5.

**Reader judgements** (n=49):
- **Understood the issue:** yes 22, partial 21, no 6.
- **Expected behaviour correct:** yes 15, partial 23, no 11.
- **Repro:** valid 27, invalid 11, none 9.
- **Verification after the last edit:** none 18, repro-only 12, tests passed 11, tests failed but ignored 8.
- **Interpreted results correctly:** yes in only 14 of 37 applicable runs.

**False confidence.**
- Of the 132 non-empty failed patches, 89 ended with the agent's own check green: 58 with the last pytest passing and 80 with a clean repro (these overlap).
- Of the 104 near-misses, 52 had the agent's last pytest pass.

**Waste** (traced agent time; failed runs total 38.9 h):

| category | time | share |
|---|---|---|
| analyzer | 11.4 h | 29% |
| malformed edit calls | 7.9 h | 20% |
| identical repeats | 3.3 h | 8% |
| after submit | 1.7 h | 4% |
| productive | 14.1 h | 36% |

- Across all 304 C9e runs, malformed calls cost about 10 h (≈19% of agent time).
- Time after the patch was final (after the last successful mutation) was 8.8 h in failed runs; the median per run was only 50 s, so a few runs carry most of it.
- 26 failures ran a `submit_patch` loop (≥10 calls, up to 267); 5 of those hit the 500-LLM-turn cap.
- Failed runs averaged 9 calls after "Tool call budget exhausted".
- **Malformed edits.** 4,895 of 5,835 `edit_file` calls (84%) were malformed. 82% of those end `new_string` with a stray backtick plus `,old_string:`, so the parser drops `old_string`. 35 runs had a streak of 20 or more identical malformed retries.
  - Root-thinking candidates (C11n, C13t, C14d, C15n512) show a malformed share of only 16–22%. C9ae's prompt-only "edit fallback" rule cut C9e's 84% only to 71%, and did not improve pass rate.
- **Context overflow.** All 17 overflows happen inside `code_analyzer`; 15 of them end in an empty patch. They come at 18–20 analyzer calls, of which about 75% are identical repeats, e.g. marshmallow_2854: `sed -n '540,565p' fields.py` ×48. The context limit is 32k and 4,096 output tokens are requested.
- **Infra stalls.** 17 timeouts are serving stalls: no step for 15–60 min. 13 of them are consecutive in `px_c9e_s1/s3`. **C9e s1 is therefore understated by up to about 3 tasks**, which is the within-task expectation. C17 has none.

## 4. Successes vs failures

What distinguishes successes is mostly task size, not process:
- Gold patch: 8 vs 27 lines; gold functions: 1 vs about 3.
- Successes are short: 26 vs 64 tool calls, and 7 vs 22 analyzer calls.
- Successes run the module's test file far more often: 71% vs 30%. At least part of this is a consequence of being on track, not a cause.
- Repro writing is near-universal in both groups. Edit counts are similar (median 1 ok edit).

Within-task contrasts (the same task across C9e and C17 runs), as expected extra solves over the 304 C9e runs:

| failure mode | runs | expected extra solves |
|---|---|---|
| malformed loop (≥20) | 28 | 8.1 |
| analyzer overflow | 17 | 5.7 |
| submit loop | 26 | 4.2 |
| infra stall | 17 | 3.0 |

These overlap, so about 12–15 in total (~4–5 pp).

## 5. Tasks C9e never solves

- 82 of 152 tasks are never solved in s1/s2.
- 40 are never solved by any candidate in ~50 runs. Treat those as the current ceiling.
- 17 are solved by C17 at least once, and 41 by some candidate.
- The 19 "should-solve" tasks (C17 > 0, or others ≥ 25%) account for 38 C9e failed runs:
  - 20 are near-misses with a semantically wrong fix. Examples: click_3821 (all 8 F2P fail ×2 seeds), werkzeug_3266 (23/23 F2P fail), jinja_2029 (`__reduce__` returns an unpicklable lambda; the repro still printed "Pickle failed" and the agent submitted).
  - 6 are empty patches. jinja_2022 concluded "iteration is deterministic, no change".
  - 3 are analyzer overflows, 3 are infra stalls in s1/s3 (tenacity_615/653, jinja_1665), 1 is a malformed-edit loop, and the rest are mixed.
- C17's +0.06 comes from better analyzer localization: gold function in LOCATION 85% vs 79%. Its root behaviour is unchanged (malformed share 78%), and the analyzer now consumes 66% of agent time.
  - The C17 sample of 12 failures labels as: 7 ×4, 13 ×3, 1 ×2, 2/4/infra ×1. C17 failures are relatively more process (malformed) and spec failures.

**Near misses** are the best target for correction: 104 runs touched a gold function with a syntactically valid patch, and 31 of them partially pass F2P. Examples:
- werkzeug_3273: `__getattribute__` returns `.string` without warning, so the test reports "DID NOT WARN".
- marshmallow_2854 s2: unconditional `self._schema.many = self.many`, where the gold uses a `None` default.
- tenacity_694: fixed sync `_run_wait` only; the async twin and `__radd__` remain.
- click_3860: the issue says to print the section "iff at least one argument has help", and `format_arguments` was left untouched.

## 6. Comparison with the old C1–C6 forensics (`reports/council/trajectory_forensics.md`, 30 tasks)

| old claim | now (C9e, 152 tasks) |
|---|---|
| LOC primary 7% | **confirmed / lower: ≈3%** (3+14). 128/132 non-empty patches hit a gold file |
| SPEC 33% (56/171) | **lower: ≈12% [4–23%]**. The new proxy has fewer unwinnable tasks, but 40/152 tasks are still never solved by anyone |
| TIME 19% | **mostly gone (≈4%)** with the 60-min cap. The timeouts that remain are mostly infra stalls |
| UND 15% + FIXC 5% + API 2% | **grown to ≈54%** (4+5+1+2). This is now the dominant failure |
| MALF 8% primary (+8% contributing) | **similar primary (≈3.5% for 7, ≈10% for 10)**. Malformed calls are still 84% of edit calls and 19% of time; the mechanism is the same backtick bug |
| repro not reproducing drove UND | partly: 11/49 invalid and 9/49 no repro. **Ignoring failing evidence** (8/49 tests failed and ignored; 23/37 misinterpreted results) matters as much |

## 7. Top three causes and smallest interventions

### 1. Wrong or incomplete modification at the right location, submitted with false confidence
- **Size:** 4+5+2 ≈ 87 runs (47%), or 54% including 1. Near-misses: 104 runs.
- **Intervention: a deterministic pre-submit gate as a skill.** Skills are not budget-gated. Call it `skills/presubmit/scripts/check.py`:
  - It runs `/tmp/repro.py`, plus the existing test file(s) mapped from each modified module (`tests/test_<module>.py` or a grep for importers), on the patched tree.
  - It runs `git stash; repro; git stash pop` to show whether the repro failed on the original.
  - For each modified function, it lists same-name defs, overrides, sync/async twins and call sites (catches tenacity_694 and pyglove_838930644).
  - It prints a PASS/FAIL table and the diff stat.
- **Prompt rule:** "call presubmit before `submit_patch`; never submit while it shows FAIL, and never edit tests to make it pass. Put one assert per issue example or expected output into /tmp/repro.py."
- **Expected effect:**
  - The readers marked ≈96 extrapolated runs as fixable by test feedback or by checking against the issue's own examples. A realistic conversion of 10–20% gives **+10–19 runs/304 (~+3–6 pp)**, at a cost of about +30–60 s per task.
  - Caution: earlier *prompt-only* verification variants (C9b reprofail, C14b, C9d/C14d importcheck) were null within noise. Only a deterministic, enforced check is worth testing.

### 2. Process degeneration: malformed `edit_file`, analyzer loops into context overflow, submit loops
- **Size:**
  - 7+10+11+12 ≈ 33 runs primary (18%).
  - 63 runs carry malformed edits; 17 analyzer overflows kill the task outright.
  - About 30% of failed-run time goes to malformed calls plus repeats.
- **Smallest intervention:**
  - **(a) Single-string edit skill.** Remove `edit_file` from the root `tools:` list in `agent.yaml`. Add a skill `apply_edit` that takes one string argument in SEARCH/REPLACE block form, asserts a unique match, writes the file, and prints the hunk.
    - Single-string calls (`run_command`) are essentially never malformed. The two-string `new_string`/`old_string` call is what breaks.
    - The C9ae prompt-only fallback failed because `edit_file` stayed available.
    - Expected (within-task): **+6–8 runs/304 (~+2–3 pp)**, and about 15–20% less agent time.
  - **(b) Analyzer containment.**
    - Give the analyzer the existing `repo-locate` skill as its first call.
    - Restrict reads to 40 lines.
    - Root prompt: "if `code_analyzer` returns nothing useful, continue yourself".
    - If the harness permits it, set a per-sub-agent LLM-call cap of about 15.
    - Expected: up to 5.7 runs/304 (within-task).

### 3. Hidden requirements not stated in the issue (13)
- **Size:** ≈23 runs (12%, CI 4–23%).
- **What the tests want:** exact error messages (jinja_1663, jinja_1706), new public names (`metavar_highlighter`, `Discriminator` re-export, `ETagSet.contains_strong`), private helpers called by name, and behaviour the issue never mentions (sqlmodel_2095).
- **Fixability:** mostly not fixable.
- **Smallest intervention:** a prompt rule: "reuse identifiers and message wording from the issue verbatim; when adding a public symbol, also export it where siblings are exported (`__init__`, `__all__`); keep existing error types".
- **Expected effect:** 2–5 runs. Treat these ~12% plus the 40 never-solved tasks as the ceiling.

**Recommended single first intervention: 2(a), the single-string edit skill replacing `edit_file`.**
- It is deterministic and its mechanism is directly measurable: the malformed share should fall from 84% to about 0.
- It reduces runtime, which is the binding constraint.
- It needs only one proxy pair (s1, s2) to validate.
- Run the pre-submit gate (1) second. It has the larger ceiling, but its conversion is uncertain and it adds runtime.
- Separately, **re-run `px_c9e_s1` shard s3** before any further C9e-vs-X comparison, because the 13 stalled runs bias C9e down.
