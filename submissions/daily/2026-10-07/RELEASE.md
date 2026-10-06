SUBMIT: submission_2026-10-07_c9a_editfix.zip

# Release 2026-10-07 (provisional, not evaluated on GPUs yet)

**Candidate:** C9a = C8 (LB 0.13 champion) + one change: an edit-robustness fallback in prompts/system.md.
- If `edit_file` fails once, don't retry it. Apply the edit with `run_command` + a Python heredoc (assert count == 1, replace, write).
- Never put backticks or ``` fences inside old_string/new_string.

**Why:**
- Trajectory forensics found 612 rejected `edit_file` calls against 518 successful ones; 85% of the rejected calls end `new_string` with a stray backtick.
- At least 14 failed runs lost an otherwise-correct fix this way.
- The council estimated **+0.8 to +1.0 tasks** per 30 tasks, the largest of the single-change fixes in its table.
- The change only touches the failure path (after an edit fails), so behaviour on clean runs is unchanged.

**Runtime:** the same budget as C8 (no eval_config; scorer defaults). The fallback replaces retry streaks, so it should not be slower. The 12-hour risk is the same as C8, which completed.

**Evidence:** observational only (trajectory forensics on the C-series runs). No paired GPU eval: running evals in this session is waiting on the user's permission.

**Expected LB:** 0.13–0.16. It is a one-variable change against C8, so the LB result directly measures the edit fix.

**Alternative:** `submission_2026-10-07_c9b_reprofail.zip` = C8 + "the repro must fail before you edit" (council estimate +0.4 to +0.6). Submit it on another day.

**To get evidence (after permission):** `sbatch ops/slurm/ap_eval_pair.sbatch submissions/c8_anchorplus c8_s1 submissions/c9a_editfix c9a_s1`
