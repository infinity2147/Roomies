SUBMIT: submission_2026-10-07_c9ae_editfix_analyzercap.zip

# Release 2026-10-07: PROVISIONAL = C9ae (as of 09:45 IST); may switch to C11t (DECISIONS D22). The cycle at ~10:30–11:30 IST re-checks it with DECISIONS D17/D18.

**Candidate:** C9ae = C8 (LB 0.13 champion) + two changes in separate files:
- C9a, root system prompt: after one failed `edit_file`, apply the edit with a Python heredoc that asserts the old text occurs exactly once. Never put ``` fences in `old_string`/`new_string`.
- C9e, code_analyzer sub-agent: max_output_tokens 4096 and thinking budget 2048, plus a 20-call / 60-line-read budget in the prompt. This prevents the ContextWindowExceeded crashes (D16).
(`submissions/c9ae_combo` and `submissions/c9ae_editfix_analyzercap` are byte-identical. The zip was checked against the dir.)

**Evidence (proxy benchmark, 152 tasks from 16 unseen repos, seed 1, clean shards only (leak=0), refreshed 09:40 IST):**
| run | n | pass rate | ctxErr | err | min/task |
|---|---|---|---|---|---|
| C8 | 133 | 0.308 | 14 | 23 | 13.6 |
| C9a | 114 | 0.360 | 16 | 23 | 11.9 |
| C9e | 114 | 0.368 | 7 | 26 | 14.6 |
| C9ae | 152 | 0.375 | 10 | 26 | 12.8 |
| C10 | 77 | 0.429 | 1 | 6 | 11.9 |
| **C11t** (C9ae + thinking on root) | 105 | 0.524 | 3 | 7 | 14.1 |

Paired vs C8: C9a n=114 +0.061 (z=+1.61); C9e n=114 +0.070 (z=+1.63); C9ae n=133 +0.083 (16W/5L, z=+2.40); **C11t n=100 +0.200 (23W/3L, z=+3.92)**.
Paired vs C9ae: **C11t n=105 +0.105 (16W/5L, z=+2.40)**; C10 n=77 +0.039 (8W/5L).
Among the C9 variants (rule D17/D18) C9ae is still the pick. C11t beats it clearly, but D19 also requires an L4 timing check (D9) because thinking makes the typical task ~1.4× longer (the mean is only 1.10× because C11t avoids runaway loops).

**SWITCH RULE (D22), applied by the 10:28/11:28 cycles:** if Kaggle kernel `gemma-rl-eval-c11t-t30s` (30 public tasks, serial, 4×L4 scorer stack) is COMPLETE and passes D9 (150 × mean + 0.5 h ≤ 11 h, or paired time ≤ 1.05× the C9ae kernel), line 1 becomes `SUBMIT: submission_2026-10-07_c11t_c9ae_think.zip`. Otherwise C9ae stays.
The ~10:30 cycle re-runs px_report and rewrites this table; the choice changes only if the rule says so.

**Runtime:** the root agent is the same as C8's (C8 completed on the scorer). The analyzer cap only shortens sub-agent calls. Proxy min/task is not comparable across runs because the shards ran on different GPU types (A100/A40/L40).

Also in this dir: C11t (`submission_2026-10-07_c11t_c9ae_think.zip`, validated), C9a (`submission_2026-10-07_c9a_editfix.zip`, the fallback), C9e, and C9b.
