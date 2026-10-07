SUBMIT: submission_2026-10-07_c9ae_editfix_analyzercap.zip

# Release 2026-10-07: C9ae (re-checked 10:45 IST). C11t is the stronger candidate on the proxy, but its 4×L4 timing run (the D9 runtime check) is still running and will not finish before 12:00. D22 therefore keeps C9ae today. The 11:28 cycle switches line 1 only if that kernel is COMPLETE and passes D22.

**Candidate:** C9ae = C8 (LB 0.13 champion) + two changes in separate files:
- C9a, root system prompt: after one failed `edit_file`, apply the edit with a Python heredoc that asserts the old text occurs exactly once. Never put ``` fences in `old_string`/`new_string`.
- C9e, code_analyzer sub-agent: max_output_tokens 4096 and thinking budget 2048, plus a 20-call / 60-line-read budget in the prompt. This prevents the ContextWindowExceeded crashes (D16).
(`submissions/c9ae_combo` and `submissions/c9ae_editfix_analyzercap` are byte-identical. The zip was checked against the dir.)

**Evidence (proxy benchmark, 152 tasks from 16 unseen repos, seed 1, clean shards only (leak=0), refreshed 10:40 IST):**
| run | n | pass rate | ctxErr | err | min/task |
|---|---|---|---|---|---|
| C8 | 133 | 0.308 | 14 | 23 | 13.6 |
| C9a | 114 | 0.360 | 16 | 23 | 11.9 |
| C9e | 114 | 0.368 | 7 | 26 | 14.6 |
| C9ae | 152 | 0.375 | 10 | 26 | 12.8 |
| C10 | 122 | 0.369 | 2 | 14 | 14.2 |
| **C11t** (C9ae + thinking on root) | 152 | 0.487 | 4 | 11 | 15.9 |

Paired vs C9ae: **C11t n=152 +0.112 (24W/7L, sign-z +3.05)**; C10 n=122 +0.000 (11W/11L, dropped); C8 n=133 −0.083.
Time: C11t takes 1.25× C9ae's total task time on the same GPU types (95 tasks; median per-task ratio 1.54×). That is within D19's 1.3× limit, but the scorer runs tasks one at a time, so the absolute L4 time still has to be measured before C11t ships.

**SWITCH RULE (D22), applied by the 10:28/11:28 cycles:** if Kaggle kernel `gemma-rl-eval-c11t-t30s` (30 public tasks, serial, 4×L4 scorer stack) is COMPLETE and passes D9 (150 × mean + 0.5 h ≤ 11 h, or paired time ≤ 1.05× the C9ae kernel), line 1 becomes `SUBMIT: submission_2026-10-07_c11t_c9ae_think.zip`. Otherwise C9ae stays.
The ~10:30 cycle re-runs px_report and rewrites this table; the choice changes only if the rule says so.

**Runtime:** the root agent is the same as C8's (C8 completed on the scorer). The analyzer cap only shortens sub-agent calls. Proxy min/task is not comparable across runs because the shards ran on different GPU types (A100/A40/L40).

Also in this dir: C11t (`submission_2026-10-07_c11t_c9ae_think.zip`, validated), C9a (`submission_2026-10-07_c9a_editfix.zip`, the fallback), C9e, and C9b.
