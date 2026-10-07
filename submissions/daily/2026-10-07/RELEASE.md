SUBMIT: submission_2026-10-07_c9a_editfix.zip

# Release 2026-10-07: PROVISIONAL (as of 06:00 IST). The cycle around 10:30–11:30 IST finalizes it by DECISIONS D17.

**Candidate:** C9a = C8 (LB 0.13 champion) + one change to the root system prompt: an edit-failure fallback.
- After one failed `edit_file`, apply the edit with a Python heredoc that asserts the old text occurs exactly once.
- Never put ``` fences in `old_string`/`new_string`.

**Evidence (proxy benchmark, 16 unseen repos, seed 1, partial, 05:40 IST):**
| run | n | pass | rate | ctxErr |
|---|---|---|---|---|
| C8 | 77 | 22 | 0.286 | 10 |
| C9a | 65 | 25 | 0.385 | 8 |

Paired C9a vs C8: 63 tasks, diff **+0.095**, 7 wins / 1 loss, sign-z +2.12.

**Runtime:** about the same as C8 (10.9 vs 11.0 min/task on the same proxy tasks). C8 completed on the scorer.

**Still being evaluated (may replace C9a at finalization):**
- `submission_2026-10-07_c9ae_editfix_analyzercap.zip`: C9a + the C9e analyzer context cap (DECISIONS D16). It targets the ContextWindowExceeded failures, about 13% of proxy tasks.
- `submission_2026-10-07_c9e_analyzercap.zip`: C8 + the analyzer cap only.

Also in this dir: `submission_2026-10-07_c9b_reprofail.zip`.
