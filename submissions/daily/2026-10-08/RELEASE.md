SUBMIT: submission_2026-10-08_c9ae_editfix_analyzercap.zip

# Release 2026-10-08: DRAFT (written 2026-10-07 08:45 IST). Later cycles must re-decide this.

Default = C9ae (same as 2026-10-07; resubmitting it also gives a second LB reading for noise).
Switch to **C11t** (`submission_2026-10-08_c11t_c9ae_think.zip`, = submissions/c11t_c9ae_think, validated OK) only if
DECISIONS D19 holds:
- paired proxy diff vs C9ae ≥ +0.03 over ≥ 60 clean pairs (s1, plus s2 if available),
- proxy min/task ≤ 1.3× C9ae's,
- Kaggle L4 timing kernel `gemma-rl-eval-c11t-t30s` gives 150 × mean task time + 0.5 h ≤ 11 h.

Status at 08:45 on 2026-10-07: C11t +0.057 vs C9ae (n=35, 5W/3L), min/task 14.0 vs 12.8 (1.09×). L4 timing kernels for C9ae and C11t are running.
If the 2026-10-07 LB score of C9ae comes back below C8's 0.13 by more than 2 tasks (≤ 0.09), do not resubmit C9ae: submit C11t if it passes D19, else C8.
