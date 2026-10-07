# Failure forensics: proxy runs c8 / c9a / c9e / c9ae (seed 1), 2026-10-07

Snapshot taken about 06:35. c8 and c9a are complete (114 tasks each). **c9e (66) and c9ae (54) are partial**: shards s3, s4 and s5 were still running.
Inputs: `results/px/px_*_s1/s*/{task_results.jsonl,traces,patches,test_outputs}`. All of this is read-only log analysis.
Scripts used (outside the repo): `/tmp/forensics/classify2.py`, `/tmp/forensics/sub.py`, `/tmp/forensics/mal.py`.

## 1. Failure-mode counts (primary cause, one per failed task)

| mode | c8 | c9a | c9e | c9ae |
|---|---|---|---|---|
| ContextWindowExceeded, **sub-agent** (code_analyzer) | 11 | 16 | 3 | 2 |
| ContextWindowExceeded, root agent | 0 | 0 | 0 | 0 |
| Tool-budget (100) exhausted, empty patch | 2 | 3 | 2 | 1 |
| LLM-turn cap exhausted | 1 | 1 | 1 | 0 |
| 60-min session timeout | 2 | 0 | 0 | 0 |
| No submit_patch and no diff | 1 | 1 | 0 | 0 |
| Empty patch, analyzer used up the shared tool budget | 5 | 4 | 2 | 4 |
| Empty patch, edit/tool-call failures (malformed args) | 2 | 1 | 2 | 0 |
| Empty patch, never edited (explore/repro loop) | 0 | 5 | 1 | 0 |
| Empty patch, agent reverted its own fix (`git checkout -- .`) | 0 | 1 | 0 | 1 |
| Empty patch, other | 0 | 1 | 0 | 0 |
| test_patch failed to apply (agent edited test file) | 2 | 2 | 0 | 0 |
| Patch breaks test collection (Import/Name/SyntaxError) | 4 | 2 | 2 | 0 |
| Wrong fix: quick and shallow (<6 min, <45 calls) | 9 | 6 | 8 | 10 |
| Wrong fix: interface/API mismatch or runtime error in own code | 10 | 10 | 4 | 4 |
| Wrong fix: analyzer used up the budget, root rushed | 9 | 8 | 3 | 1 |
| Wrong fix: wrong/incomplete semantics after long effort | 22 | 12 | 7 | 5 |
| **total failed / n** | **80/114** | **73/114** | **35/66** | **28/54** |

Cross-cutting tags on failed tasks. A task can carry several tags.

| tag | c8 | c9a | c9e | c9ae |
|---|---|---|---|---|
| analyzer_runaway (≥50 analyzer tool calls or ≥10 identical calls) | 25 | 31 | 13 | 10 |
| malformed tool args (≥3 calls with keys like `start_line"`) | 14 | 21 | 5 | 3 |
| submit_loop (≥10 submit_patch calls) | 15 | 9 | 5 | 6 |
| edit_loop (≥5 identical or ≥8 failed edits) | 2 | 1 | 0 | 1 |
| final patch touches real test files | 3 | 4 | 0 | 0 |

The "test_patch can't find file" case (agent deleted or renamed a file) did not occur. The 4 test_patch failures are all "patch does not apply" on `tests/test_filters.py` or `tests/test_*.py`, caused by the agent editing tests (click_3704, jinja_1984, in both c8 and c9a). C9e and C9ae have none.

### Mechanisms found in traces
1. **The analyzer shares the root agent's 100-call budget.** `tool_calls` in task_results counts code_analyzer calls. In the worst cases the analyzer used 90–100 calls (typer_1821 100/100, jinja_1702 99, jinja_2022 98, click_3767 90, typer_1405 90). The root agent then had 0–10 calls left.
   The runaway is almost always a **degenerate identical-call loop on an empty observation**. A `grep` that matches nothing returns `stdout:""` with exit 1 (or exit 0 when piped through `head`), and the model re-issues the exact same command:
   - click_3767: `grep -rn "def pager" …` ×77
   - typer_1821: `grep -rn "UNSET" . | head` ×94
   - jinja_1702: ×74
   - typer_1405: ×53

   The C9e "max 20 calls / never repeat" prompt cap is ignored in these loops. It still helped on average: the runaway tag fell from 31 (c9a) to 10–13.
2. **Sub-agent context overflow comes from malformed `read_file` args.** Gemma emits keys `start_line"` / `end_line"` (592 + 406 occurrences across runs), so the range is ignored and the first 150 lines of the file come back. The analyzer then re-asks for the same range until 32k overflows (fiddle_624968231: 7 identical calls). Every ctx error in every run is in the sub-agent; the root agent never overflowed because it has compaction.
3. **Submit loop.** `submit_patch` does not end the run, and the model keeps calling it, up to 238 times in pyglove_838930644. It is mostly harmless, but it sometimes re-invokes code_analyzer after submitting and edits again. Time after the first submit: c9ae 47 min total over 10 tasks.
4. **Harness contamination on node cn17-dgx (job 337610).** Every patch from c9ae s1, c9ae s2 and c9e s5 (all on 337610) contains harness-injected `conftest.py` / `pytest.ini` ("# Hermetic test discovery hook for SWE-gemma"). `git status` in the trace shows them staged (`A conftest.py`), so `setup_baseline_commit`'s `git add -A` ran but its `git commit` failed silently. Likely cause: no git identity or HOME on that node. As a result `submit_patch` diffs against HEAD.
   - Scoring is mostly unaffected, because verification resets conftest.py and pytest.ini.
   - It caused **jinja_1984 (c9ae)**: the agent saw the spurious files, ran `git checkout -- .`, and wiped its own fix.
   - It also costs root tool calls in other tasks, for example attrs_1428 `git checkout -- conftest.py && rm pytest.ini`.
   - 20 of c9ae's 28 failures come from these two shards. On those shards C9ae scored 17/37 vs C9a 19/37, so the C9ae estimate is somewhat biased low.
   - Fix this in `ops/slurm/ap_worker.sbatch` (export GIT_AUTHOR_/GIT_COMMITTER_ NAME/EMAIL, or check `git commit` on cn17), not in the submission.

## 2. Top-3 remaining C9ae failure modes (n=54, 28 failed)

### #1 The analyzer's identical-call loop uses up the shared tool budget: 10 tasks
- **Tasks:** typer_1821, jinja_1702, jinja_2022, attrs_1428, pyglove_820048200 (empty patch); click_3767, typer_1405, jinja_1664, ml_collections_861237487, ml_collections_744076940 (rushed wrong fix).
- **Examples:** jinja_1702 (99/100 calls by the analyzer; passes in c8 and c9a), typer_1821 (100/100, `grep UNSET` ×94), click_3767 (`grep "def pager"` ×77, root had 9 calls left).
- **Proposed fix (one change, `submissions/c9ae_combo/configs/analyzer_sampling.yaml`):** add `presence_penalty: 0.6`. Optionally also raise temperature to 0.5. Neither is used by the root agent. ADK LiteLlm forwards `presence_penalty`/`frequency_penalty` (lite_llm.py:1960). The low-temperature, zero-penalty setup is what lets the exact command repeat.
- **Prompt alternative (`prompts/analyzer.md`):** "end every search with `; echo '[end of results]'`; an empty result means the identifier does not exist, change the query." This gives the model a non-empty observation to react to.
- **Expected recovery:** about 3 tasks. jinja_1702 (passed by c8 and c9a), attrs_1428 (passed by c9e) and ml_collections_861237487 (passed by c9a). The others fail in every variant.

### #2 Quick shallow fix, submitted early with most of the budget unused: 10 tasks
- **Tasks:** click_3821, click_3728, jinja_1663, marshmallow_2854, attrs_1606, etils_684740718, click_3860, flask_6096, jinja_1706, werkzeug_3273. Median 3 min and about 20 of 100 calls used, typically one edit and a `-k` test run.
- **Pattern:** the hidden tests check behaviour that the issue text describes but the fix ignores.
  - click_3821: `get_help_spec` should return a str, the fix returns a tuple.
  - werkzeug_3273: "showing a warning for any extra attribute" was never implemented (DID NOT WARN).
  - attrs_1606: `__replace__` still bound as `C1.__replace__`.
  - jinja_1706 and jinja_1663: exact error wording.
- **Proposed fix (one change, `prompts/system.md` step 5 Verify):** "Before submitting, re-read the issue. For every sentence that states a behaviour, name, return type, warning or message, add an `assert` for it to /tmp/repro.py and make all of them pass. Then run the whole test file of each module you changed (`pytest tests/test_<module>.py -q`, no `-k`)."
- **Expected recovery:** 1–3 tasks. These tasks fail in all four variants, so they are hard; werkzeug_3273 and click_3821 are the likeliest.

### #3 Wrong fix after real effort (incomplete semantics, own runtime bugs, hidden-API mismatch): 9 tasks
- **Tasks:** marshmallow_2909, pyglove_833501879, pyglove_838930644, typer_1695, ml_collections_744076940, plus the 4 interface cases jinja_1664, typer_1508, click_3767, ml_collections_861237487.
- **Examples:**
  - ml_collections_861237487: `NameError: name 'field_type_args' is not defined`, a bug in the agent's own code.
  - click_3767: `TypeError: write() argument must be str, not bytes`.
  - marshmallow_2909: the agent flip-flopped through 73 `edit_file` calls (65 "identical" no-ops) because an existing test asserted the old behaviour. C9a and C9e passed it.
  - typer_1508 and jinja_1664 need hidden-test names that are not in the issue (`metavar_highlighter`, `parse_primary_with_namespace`), so they are not recoverable.
- **Proposed fix (one change, `prompts/system.md` Hard rules):** "If an existing test asserts the old behaviour that the issue asks to change, the hidden tests replace it: implement the issue and do not revert to satisfy the old test. Never repeat an `edit_file` that returned 'identical'."
  - Combined with the full-module test run from #2, this also catches the NameError and TypeError cases.
- **Expected recovery:** 1–2 tasks (marshmallow_2909, ml_collections_861237487).

### Cheap extras, not top-3 by count
- **Remove `read_file` from `sub_agents/code_analyzer.yaml` tools.** The analyzer still has `run_command sed -n`. This targets c9ae's 2 sub-agent ctx errors (fiddle_624968231, fiddle_698053641) and the dominant ctx mode in c8 and c9a (11 and 16 tasks). Direct pass gain on c9ae is about 0–1, because both fiddle tasks fail elsewhere too.
- **One prompt line:** "never run `git checkout -- .`, `git stash` or `git clean`; revert individual files only." This would have saved jinja_1984 (c9ae) and ml_collections_873267666 (c9a).

## 3. Runtime

| run | n | mean min/task (all) | mean / median / p90 / max on the 41 tasks common to all 4 runs | tasks >40 min | >20 min |
|---|---|---|---|---|---|
| c8 | 114 | 14.4 | 11.4 / 8.0 / 26.2 / 54.1 | 11 (2 hit the 60-min timeout) | 24 |
| c9a | 114 | 11.9 | 10.9 / 8.1 / 24.2 / 39.5 | 6 (typer_1695 51, tenacity_653 56, jinja_1706 48, …) | 17 |
| c9e | 66 | 6.2 | 5.0 / 3.7 / 8.0 / 25.3 | 0 | 3 |
| c9ae | 54 | 6.1 | 5.8 / 4.8 / 11.4 / 16.8 | 0 | 0 |

Pass rates on the 41 common tasks: c8 17, c9a 20, c9e 20, c9ae 23.

Caveats and risks:
- **Wall time is confounded by node and concurrency.** c8 and c9a ran 04:15–06:00 on a40/l40 nodes. c9e and c9ae ran later, partly on cn17-dgx with conc=10. The 2x speed-up of c9e/c9ae is probably partly real (less analyzer churn, fewer timeouts) but is not a clean agent effect.
- **Long-tail risk is concentrated in C8/C9a** (60-min timeouts; tenacity_653, attrs_1457 and marshmallow_2909 ran 54 min or more). C9ae shows no task over 17 min so far, but its slow shards (s3–s5) are still running.
- **The budget is tight.** At about 120 hidden tasks in 12 h, the allowance is 6 min/task if run serially. C9ae's 6.1 min mean is at that line, so any regression in analyzer loops or submit loops (up to 4.7 min wasted after the first submit) matters.
