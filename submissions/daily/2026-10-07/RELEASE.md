SUBMIT: submission_2026-10-07_c9ae_editfix_analyzercap.zip

# Release 2026-10-07: PROVISIONAL = C9ae (as of 06:45 IST). The cycle at ~10:30–11:30 IST re-checks it with DECISIONS D17/D18.

**Candidate:** C9ae = C8 (LB 0.13 champion) + two changes in separate files:
- C9a, root system prompt: after one failed `edit_file`, apply the edit with a Python heredoc that asserts the old text occurs exactly once. Never put ``` fences in `old_string`/`new_string`.
- C9e, code_analyzer sub-agent: max_output_tokens 4096 and thinking budget 2048, plus a 20-call / 60-line-read budget in the prompt. This prevents the ContextWindowExceeded crashes (D16).
(`submissions/c9ae_combo` and `submissions/c9ae_editfix_analyzercap` are byte-identical. The zip was checked against the dir.)

**Evidence (proxy benchmark, 152 tasks from 16 unseen repos, seed 1, partial, 06:40 IST):**
| run | n | pass rate | ctxErr |
|---|---|---|---|
| C8 | 114 | 0.298 | 11 |
| C9a | 114 | 0.360 | 16 |
| C9e | 54 | 0.444 | 3 |
| C9ae | 44 | 0.477 | 2 |

Paired vs C8: C9a n=114 +0.061 (13W/6L); C9e n=54 +0.111 (9W/3L); **C9ae n=44 +0.136 (6W/0L, z=+2.45)**.
Paired C9ae vs C9a: n=45, diff 0.000 (2W/2L). On the 34 tasks that all four runs share: C8 14, C9e 16, C9a 18, C9ae 19, and ctxErr is 1/2/2/1.
Rule D17: the largest paired diff vs C8 with ≥38 pairs is C9ae. It ties C9a within 0.03 and has fewer ctxErr, so C9ae wins.

**Runtime:** the root agent is the same as C8's (C8 completed on the scorer). The analyzer cap only shortens sub-agent calls. Proxy min/task is not comparable across runs because the shards ran on different GPU types (A100/A40/L40).

Also in this dir: C9a (`submission_2026-10-07_c9a_editfix.zip`, the fallback), C9e, and C9b.
