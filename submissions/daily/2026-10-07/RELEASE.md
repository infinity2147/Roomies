SUBMIT: submission_2026-10-07_c9ae_editfix_analyzercap.zip

# Release 2026-10-07: PROVISIONAL = C9ae (as of 07:35 IST). The cycle at ~10:30–11:30 IST re-checks it with DECISIONS D17/D18.

**Candidate:** C9ae = C8 (LB 0.13 champion) + two changes in separate files:
- C9a, root system prompt: after one failed `edit_file`, apply the edit with a Python heredoc that asserts the old text occurs exactly once. Never put ``` fences in `old_string`/`new_string`.
- C9e, code_analyzer sub-agent: max_output_tokens 4096 and thinking budget 2048, plus a 20-call / 60-line-read budget in the prompt. This prevents the ContextWindowExceeded crashes (D16).
(`submissions/c9ae_combo` and `submissions/c9ae_editfix_analyzercap` are byte-identical. The zip was checked against the dir.)

**Evidence (proxy benchmark, 152 tasks from 16 unseen repos, seed 1, clean shards only (leak=0), 07:35 IST):**
| run | n | pass rate | ctxErr | min/task |
|---|---|---|---|---|
| C8 | 119 | 0.319 | 12 | 13.8 |
| C9a | 114 | 0.360 | 16 | 11.9 |
| C9e | 101 | 0.406 | 7 | 10.0 |
| C9ae | 127 | 0.409 | 6 | 11.6 |

Paired vs C8: C9a n=114 +0.061 (13W/6L, z=+1.61); C9e n=101 +0.089 (16W/7L, z=+1.88); **C9ae n=113 +0.088 (14W/4L, z=+2.36)**.
Paired vs C9a: C9ae n=108 +0.037 (11W/7L); C9e n=101 +0.020.
Rule D17/D18: C9ae and C9e tie within 0.03 (both ≥38 clean pairs); C9ae has fewer ctxErr (6 vs 7) and the best sign-z, so **C9ae**.
The ~10:30 cycle re-runs px_report and rewrites this table; the choice changes only if the rule says so.

**Runtime:** the root agent is the same as C8's (C8 completed on the scorer). The analyzer cap only shortens sub-agent calls. Proxy min/task is not comparable across runs because the shards ran on different GPU types (A100/A40/L40).

Also in this dir: C9a (`submission_2026-10-07_c9a_editfix.zip`, the fallback), C9e, and C9b.
