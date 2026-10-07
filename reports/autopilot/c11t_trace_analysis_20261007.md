# C11t (thinking on, root only) trace analysis vs C9ae, 2026-10-07

Data: results/px/px_c11t_s1 (s0..s2, 43 tasks with traces; s3 still running) paired with px_c9ae_s1 by instance_id.
43 pairs: C11t 22/43 (0.512) vs C9ae 19/43 (0.442), 5 wins / 3 losses.
Scripts: /tmp/c11t_an/an*.py (throwaway, read-only). Trace format: ATIF; thought parts are steps with
`extra.event_type == "thinking"` (message = thought text, metrics = usage of that LLM call).

## Q1. Is thinking active? How long are the thoughts?
- Yes. 2486 thought parts across 2496 root LLM calls (1.00 per call). All 43/43 tasks have them. C9ae has 0.
  The analyzer has 0 thought parts, as expected (include_thoughts:false).
- Thoughts are short. Chars per thought: median 89, p90 945, mean 388, max 13,259.
- Completion tokens per root call (thought + tool call): C11t median 53 / p90 435 / p99 1452 / max 4616.
  C9ae: median 24 / p90 200 / p99 548 / max 8192 (one C9ae call hit max_output, a degenerate repetition).
- Hitting the budget is rare. 2/2496 calls reached 4096 or more completion tokens: werkzeug_3243 4616 and typer_1405 4125.
  typer_1405's thought ends mid-code, which looks like the budget cut it off. Both calls still emitted a valid tool call.
  0 calls reached 8192.
- Harness "token limit while thinking" or "tool call cut off" nudges: 0 in C11t. C9ae had 2 "tool call cut off" nudges on the same tasks.
  Continuation nudges fell overall: 25 vs 72.

## Q2. Cost per paired task (C11t vs C9ae, n=43)
| metric | C11t median (mean) | C9ae median (mean) | per-task ratio, median (IQR) |
|---|---|---|---|
| wall s | 743 (844) | 397 (958) | 1.40 (0.58-3.02) |
| root LLM calls | 26 (58) | 24 (65) | 1.00 (0.53-1.92) |
| root output tokens | 7570 (9430) | 3418 (6705) | 2.05 (1.05-3.74) |
| total output tokens (root + analyzer) | 8162 (9998) | 4872 (8968) | 1.62 (0.86-2.88) |
| analyzer LLM calls | 5 (12) | 17 (51) | 0.22 |
| tool calls | 34 (44) | 47 (55) | 1.00 |
- Totals over the 43 pairs:
  - output tokens: 430k vs 386k (+11%)
  - prompt tokens: 25.4M vs 48.5M (-48%), because there are fewer analyzer runs and fewer runaway loops
  - wall time: 10.1 h vs 11.5 h
- Excluding pairs where either arm timed out: 8.3 h vs 7.4 h (+12%). Mean min/task over all rows: 14.1 (C11t, 43) vs 12.8 (C9ae, 152), i.e. 1.10x.
- Timeouts at 60 min: C11t 0, C9ae 3 (click_3818, sqlmodel_997, werkzeug_3243).
  Tasks hitting the 100 tool-call limit: 4 vs 7.
- Caveat: wall times come from shared vLLM servers on mixed GPUs, and C11t was interleaved with C10, so the wall ratios are noisy.
  The typical task is about 1.4-2x longer (more decode tokens per call). The mean is only about 1.1x because C11t avoids the long runaway tails.

## Q3. Wins and losses (what thinking changed)
Wins:
- attrs_1571: C9ae's analyzer ran away (393 analyzer calls), overflowed the context and left an empty patch. C11t made 5 analyzer calls, then implemented `ne` plus the stub.
- click_3821: C9ae made `get_help_spec` return a tuple (wrong API). C11t returned the spec `str` and refactored `get_help_record` correctly.
- etils_684740718: C9ae fixed only `__eq__`. C11t thought for 2.8k tokens about enum eq/hash semantics and also fixed `_missing_` and `__hash__`, which is the complete fix.
- jinja_1979: C9ae edited tests/test_loader.py, so the test_patch failed to apply. C11t kept the patch to src/.
- sqlmodel_997: C9ae looped on edit_file (115 edits, 150 root calls) until the 60-min timeout and left an empty patch. C11t solved it in 15 root calls (344 s).

Losses:
- click_3704: C11t edited 4 test files (19.6 kB patch) despite the hard rule, so the test_patch failed to apply. C9ae kept to src/docs.
- jinja_1852: the analyzer used 86 of the 100 tool calls. The root ran out of budget before its first edit and left an empty patch.
  Its final text has a raw `<|channel>thought` leak, but the patch was not affected.
- typer_1820: the analyzer ran away (83 calls), hit ContextWindowExceeded at a 28.7k prompt + 4096 output, and left an empty patch.
  The root made only 1 call.

Summary: 3 of the 5 wins are C9ae runaway or rule-violation failures that C11t avoided. 2 wins (click_3821, etils) are genuinely better fixes.
2 of the 3 losses are analyzer runaways, which are independent of root thinking. 1 loss is test editing, which happened in both arms.

Behaviour change: with thinking on, the root skips `code_analyzer` entirely in 17/43 tasks. C9ae always calls it (26 tasks once, 17 tasks 2-6 times).
Pass rate when skipped is 10/17 vs 12/26 when used (confounded by task difficulty).

## Q4. New error types?
- No thought text leaked into tool arguments or patches (special-token and channel scan of all tool args: 0). No template or parse errors in run_eval.log.
- Raw channel tokens in message text (`<|channel>thought`) appear in 3/43 C11t tasks: 2 final messages and 1 thought.
  C9ae has the same class: 6 of its 152 tasks have `<|channel>` or `<|tool_call>` in final text. This is not new.
- In tenacity_609 one thought contained a raw `call:get_status{}<tool_call|>`, so that tool call was swallowed into the thought and never executed. It was harmless, and it happened once.
- ContextWindowExceeded: 2 in C11t (fiddle_989220482, typer_1820). Both are in the analyzer (4096 output request), the existing D16 class. Root max_output 8192 caused none.
- Post-submit `submit_patch` loops (the model keeps calling submit_patch after the patch is in):
  - C11t: 8 tasks, 1044 calls after the first submit (typer_1812 ×399, pyglove_833501879 ×454)
  - C9ae: 6 tasks, 983 calls
  These are not new, but they cost wall time (about 3.3 k s in C11t).

## Q5. Recommendation
- Thinking budget of 8192: not worth a slot. The 4096 budget binds on 0.08% of calls (p99 = 1452 tokens), so raising it changes almost nothing.
  If anything, 2048 would be a cheap L4 time saver. Do not raise max_output_tokens either.
- Thinking on the analyzer: low priority. The analyzer's failure mode is runaway exploration, not shallow reasoning:
  - 2 of the 3 C11t losses are analyzer runaways
  - analyzer runaways cause 2 ctx errors and 1 tool-budget exhaustion here (typer_1821: 97 analyzer calls)
  - the root now skips the analyzer in 40% of tasks

  Higher expected value: a harder analyzer cap (for example ≤ 15-20 tool calls or LLM calls per invocation, plus an output cap that keeps prompt + output under 32k).
  This targets 2 of the 3 losses directly at near-zero runtime cost.
  If analyzer thinking is tested anyway, use budget ≤ 1024: analyzer calls are about 36 tokens each, so the cost is small, but each runaway step gets slower.
- Runtime: C11t is about 1.1x C9ae in mean task time and about 1.4-2x in median, inside D19's 1.3x mean rule. The L4 decision still depends on the
  pending Kaggle timing runs. Applying the C9ae L4 mean ×1.1-1.2 should be checked against the 4.2 min/task budget.
  Decode tokens per task rise about 1.6x at the median, which matters more on L4 than on A100.
- Verdict: keep C11t on track for replacement under D19 (need ≥ 60 pairs). The next candidate should be C11t + an analyzer runaway cap
  (one change), not more thinking.
