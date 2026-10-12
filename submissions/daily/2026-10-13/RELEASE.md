SUBMIT: submission_2026-10-13_c23_t12.zip   (autopilot draft 2026-10-12 20:40; byte-identical copy of 2026-10-12 c23_t12 - no better releasable candidate exists)

# C23_t12 (unchanged): C9e with edits via rule engine + 12-min per-task cap
- Runtime gate PASSES: L4 model 3.83 min/task -> 120 tasks 7.7 h; x1.3-1.45 hidden slowdown 10.0-11.1 h (<= 11.5 h). Smoke px_c23t12smoke_s1 passed.
- Accuracy on proxy = C9e (0.385 vs 0.391, n=304 paired, z -0.25); fewer LLM calls (88 vs 105), 0 rejected edit calls.
- Only submit if the 10-12 upload of this zip was NOT made (or the user wants a 2nd seed of the same config for noise estimate).
  If 10-12 was uploaded, its public LB score goes into ops/autopilot/lb_scores.tsv first; a replacement only comes from C26 (see STATE.md) if it passes the gate.
- Challengers (all gate-blocked): C24 planner +0.099 acc but 18.8 h; C25 +0.039 acc, 11.8 h L4 (17 h at x1.45).
