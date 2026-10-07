# C11t failure forensics vs C9ae (152 proxy tasks, seed 1), 2026-10-07

Inputs (read-only): `results/px/px_c11t_s1/s*/{task_results.jsonl,traces,patches,test_outputs}`, same for `px_c9ae_s1`,
gold patch + test_patch from `data/derived/proxy/valid_tasks.jsonl`.
Script: `scripts/analysis/c11t_failure_forensics.py` (idempotent) -> `reports/autopilot/c11t_failures_20261007.csv`
(one row per task, C11t and C9ae columns side by side: class, subclass, tool calls by author, output tokens, thinking
steps, gold-file read/edit flags, failed edits, submit count, nudges, failing test names).

C11t 74/152 (0.487), C9ae 57/152 (0.375). Paired: both pass 50, C11t only 24, C9ae only 7, both fail 71. Union 81.

## 1. Class heuristic (first match wins, one class per task)

| class | rule |
|---|---|
| test_file_edited | error "Failed to apply test_patch" (agent edited a test file) |
| context_overflow | error ContextWindowExceeded and patch never evaluated (exit -1 or empty) |
| session_timeout / llm_turn_cap | harness error and patch never evaluated; if the patch ran, the test outcome is the class and the budget error is a tag |
| tool_budget_empty | 100 tool calls used, empty patch (sub: analyzer_ate_budget = analyzer >= 40 calls; explore_loop otherwise) |
| no_submit / empty_patch | finished with an empty diff (sub: reverted / edit_loop / analyzer_ate_budget / never_edited) |
| test_hang | hidden tests timed out (exit 124) with a patch applied |
| collection_error | exit 2/4 or Import/Syntax/Name/IndentationError in the test log (patch breaks import) |
| wrong_file | patch touches none of the gold patch files |
| regression_only | gold file touched; every failing test name is absent from test_patch (pre-existing tests broken) |
| wrong_fix | gold file touched; FAIL_TO_PASS tests from test_patch still fail |

## 2. Class counts, same 152 tasks

| class | C11t | C9ae | note |
|---|---|---|---|
| resolved | **74** | **57** | |
| wrong_fix | 50 | 47 | right file(s), hidden tests still fail |
| tool_budget_empty | 9 | 10 | C11t: 6 analyzer_ate_budget, 3 root explore_loop |
| collection_error | 6 | 7 | 3 are ImportError of a symbol the hidden test imports, 2 SyntaxError, 1 AttributeError |
| regression_only | 5 | 3 | |
| context_overflow | 4 | 10 | all 4 C11t cases are the code_analyzer sub-agent |
| test_file_edited | 1 | 3 | click_3704 |
| wrong_file | 1 | 3 | |
| session_timeout | 1 | 4 | |
| test_hang | 1 | 0 | click_3818 |
| llm_turn_cap | 0 | 2 | |
| no_submit + empty_patch | 0 | 6 | |
| **failed** | **78** | **95** | |

Grouped: "no evaluated patch" (budget/runaway/empty) C11t 14 vs C9ae 32; "patch evaluated but wrong"
(wrong_fix + regression + collection + wrong_file + hang + test edit) C11t 64 vs C9ae 63.
Thinking removed more than half of the runaway class and converted it into either passes or wrong fixes
(C9ae -> C11t transitions: context_overflow -> resolved 5, tool_budget_empty -> resolved 4, wrong_fix -> resolved 11;
in the other direction resolved -> tool_budget_empty 4, resolved -> context_overflow 2). The wrong-fix class is untouched:
33/50 C11t wrong_fix tasks are also wrong_fix under C9ae and 0/50 are resolved by C9ae.

Failing-task diagnostics (C11t, n=78): gold file read 75/78 (by the root 71/78), gold file edited 70/78,
thinking present 78/78, median tool calls 52 (22 hit the 100 cap), median root output tokens 13.1k (passes: 5.9k),
median wall 17.4 min, >= 1 continuation nudge 45/78, submit loop (>= 10 submit_patch calls) 8/78, edit loops (>= 8 failed
edit_file) 0/78. Localization is not the problem for C11t: the agent finds and edits the right file in 90% of failures.

Harness finding: `submit_patch` does not end the session. click_3865 called it 484 times and pyglove_833501879 454 times
until the 500-turn cap (both patches were evaluated and failed, so no flip, but 1.5-2 h of wasted wall time each).

## 3. Examples per major class

wrong_fix (50; 22 fail exactly one hidden test; 5 shallow < 45 calls and < 10 min; 8 hit 100 calls):
- werkzeug_3243: validation added but `DID NOT RAISE BuildError` for out-of-range values (missed the build-side check); 15 calls.
- click_3728: returns `['--help','-h']`, test expects `['-h','--help']`: fix was correct in spirit, wrong ordering convention.
- pyglove_831502697: `rename` implemented, but does not raise OSError when the destination exists (edge case in issue).
- werkzeug_3298: proxy_fix port handling right for HTTP_HOST, wrong fallback when only SERVER_NAME/PORT set (1 param case).
- marshmallow_2799: touched fields.py only, gold also changes types.py; 11 tests fail on repr/validation of new Field args (partial implementation).

tool_budget_empty (9): jinja_1852, typer_1821, tqdm_1783, sqlmodel_1607, attrs_1457, marshmallow_2903 (analyzer used 86-99 of
100 calls; root had 2-18 left and never edited); attrs_1541, click_3764, pyglove_923677252 (root spent 75-86 calls on
grep/read_file, made 1-2 edits that left no diff, then submit at call 100).

context_overflow (4): fiddle_989220482, typer_1820, sqlparse_332, marshmallow_3016: analyzer overflowed the window;
root made 2-3 calls. 2 of the 4 (sqlparse_332, typer_1820) pass under C9ae.

collection_error (6): typer_1410 (`STYLE_TYPES_SEPARATOR`), typer_1508 (`metavar_highlighter`), sqlmodel_1729
(`Discriminator` not exported from `sqlmodel/__init__.py`): hidden tests import a name the agent did not define with that
exact name; ml_collections_697555350, jinja_1664: SyntaxError left in the file after 100 calls; attrs_1428: AttributeError on
import of a renamed private attribute.

regression_only (5): werkzeug_3249 (test_parse_cookie), tenacity_629 (test_wait_exponential_jitter), pyglove_814368980,
pyglove_821342698, ml_collections_650013397: fix changed behaviour of existing tests the agent never ran.

## 4. Ranked interventions

1. Isolate the code_analyzer budget (ACI/budget change). 10 C11t failures are analyzer runaways (6 analyzer_ate_budget +
   4 analyzer overflow); 6 of those 10 pass under C9ae. Give the analyzer its own cap (<= 25 calls, own context, return partial
   LOCATION on overflow) so the root always keeps >= 60 calls. Expected flips: 5-7 of 10 (C11t resolves ~54% of evaluated
   patches). Add a root nudge at 70 calls ("stop exploring, edit now") for the 3 explore_loop cases: +1-2.
2. Spec checklist + pre-submit sanity (prompt/ACI change). Target wrong_fix with a single failing test (22) and
   collection_error (6). Prompt: before editing, list the concrete behaviours the issue states (exact symbol names to export,
   ordering, which errors to raise, edge cases), write a /tmp test per item, run it and the touched module's existing test
   file before submit. ACI: refuse submit_patch if `python -c "import <pkg>"` or py_compile of edited files fails.
   Expected flips: 6-10 (3 import-name cases + 2 syntax cases are near-deterministic; 10-15% of single-test wrong fixes).
3. Best-of-K with a cheap selector (selector change). C11t u C9ae = 81/152 (+7), and all 7 are C11t runaway/budget failures,
   i.e. the stochastic class. A second seed of C11t with selector "non-empty patch, imports cleanly, agent's own tests pass"
   should flip 5-8 of the 14 no-evaluated-patch tasks; it will not flip wrong_fix (0/50 rescued by the other config).
   Constraint: the hidden eval is ~5 min/task of a 6 min/task wall budget, so K=2 only fits as a retry for empty-patch tasks,
   not a blanket K=2. The s2 seed runs now queued (07_*_s2) will measure this directly.

Cheap fix with no flips but large wall-time savings: make `submit_patch` terminal (or stop after 2 submits with no edit in
between). 8/78 failing tasks and several passing tasks loop on submit; two burned ~500 LLM turns each.
