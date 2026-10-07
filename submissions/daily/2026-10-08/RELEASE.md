SUBMIT: submission_2026-10-08_c9ae_editfix_analyzercap.zip

# Release 2026-10-08: DRAFT (rewritten 2026-10-07 10:45 IST; gate updated 11:50 by D25). The default switches to C11t once its L4 timing passes (DECISIONS D24).

**Planned pick = C11t** (`submission_2026-10-08_c11t_c9ae_think.zip` = submissions/c11t_c9ae_think, validated). Every proxy condition in D19 is met:
- proxy s1, all 152 tasks, clean: +0.112 vs C9ae (24W/7L, sign-z +3.05); +0.20 vs C8.
- time: 1.25× C9ae on the same GPU types (D19 allows up to 1.3×).
**Remaining gate (D25, replaces D9's 150-task rule):** Kaggle kernel `gemma-rl-eval-c11t-t30s` (30 tasks, serial, 4×L4) must be COMPLETE with ≥ 25 tasks and its total-time ratio vs `gemma-rl-eval-c9ae-t30s` must be ≤ 1.10: `.venv/bin/python scripts/kaggle_eval/capture_task_times.py c11t-t30s c9ae-t30s`. C9ae on L4: 4.92 min/task (≈10.3 h at 120 tasks). Model-based prediction for C11t: ≈1.04×.
If C11t is over 1.10 but C11n's kernel (`gemma-rl-eval-c11n-t30s`, running since 11:45) is ≤ 1.10 and C11n is ≥ −0.01 vs C11t on the proxy, submit `submission_2026-10-08_c11n_think_noanalyzer.zip` instead.
The next cycle that sees the kernel pass changes line 1 to `SUBMIT: submission_2026-10-08_c11t_c9ae_think.zip`.
If the kernel fails D9, or errors and cannot be rerun before 12:00 on 2026-10-08, keep C9ae (line 1 as is).

Possible upgrades (only with paired evidence vs C11t of ≥ 60 pairs, D21/D23): C11n (C11t without the analyzer) or C13t (C11t + repo-locate skill). Each needs its own zip and an L4 timing check, or must be clearly faster than C11t on the proxy.
If the 2026-10-07 LB score of C9ae comes back ≤ 0.09, do not resubmit C9ae: submit C11t if it passes the gate, else C8.
