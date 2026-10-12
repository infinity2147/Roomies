SUBMIT: submission_2026-10-11_c9e_t8.zip   (lead, 10-11 17:00; SUPERSEDES c9e_t15 and c9e_t5)

# Why 8 min (D33)
- Uncapped C9e got Notebook Timeout on Kaggle; uncapped C9ae ran ~15 h; uncapped C8 finished (0.13). C8/C9e have identical runtime
  on proxy (12.0 vs 12.5 min/task) -> the family sits at the 12 h edge; finishing was luck.
- Our L4 30-task timing (5.19 min/task incl. setup) projects 10.6 h, but the real runs show hidden tasks ~1.3-1.45x slower.
- Projected 120-task totals (hidden slowdown 1.3-1.45x): cap 15 -> 12.8-13.7 h (TIMEOUT), cap 10 -> 11.2-11.9 h (too close),
  cap 8 -> 10.3-10.9 h (safe), cap 5 -> ~8 h (LB 0.08 before).
- Cost: solves finishing after the cap ~15% of C9e's solves (proxy upper bound; capped tasks still grade their last patch).
  Expected LB ~ C8 level (0.12-0.14), but it should COMPLETE.

(superseded) c9e_t15   (lead session 01:45; replaces the autopilot's c9e_t5 draft)

# Release 2026-10-11: C9e + eval_config max_time_minutes 15
- Same agent as C9e (submitted 10-10, LB pending). Only addition: per-task cap 15 min as a runaway guard (D31).
- Why not the 5-min cap (c9ae_t5-style): on L4, 12/30 C9ae tasks take >5 min (mean 4.92, p90 12.1, max 17.3); the 5-min cap
  scored 0.08 on LB vs 0.13 (C8) and cost ~0.09 on proxy. 15 min touches ~1/30 tasks.
- Projection (L4, from C9ae-t30s): 120 tasks x 4.92 min = 10.3 h (< 12 h); the cap bounds the tail.
- Recommendation: submit ONLY if the 10-10 C9e (uncapped) errors/times out on Kaggle. If C9e completes with a score, this is a
  near-duplicate; keep the slot for C20/C21 if they pass the paired rule (>= +0.03, sign-z >= 2, <= 1.15x time).
- submission_2026-10-11_c9e_t5.zip: autopilot draft, NOT recommended (5-min cap).

## Added 02:10 (lead): submission_2026-10-11_c19_distill_t15.zip (1.55 GB, zip test OK, validate OK)
- C19 = C9ae + thinking-distillation LoRA d1 (runs/lora/e3_distill_r128, v1 data) + eval_config max_time 15.
- Held-out proxy (85-task eval half, repos never trained on), valid serving: 0.455 vs C9ae 0.355, +0.100, n=110 pairs, sign-z 2.29
  (partial: ~110/170 pairs). C9e on the same half = 0.424.
- RISK: L4 runtime with LoRA unmeasured (single-stream adapter decode ~half speed on A40; proxy per-task time ~equal to base).
- Recommended order if multiple slots: (1) c19_distill_t15 (upside + LB measurement of LoRA), (2) c9e_t15 only if the uncapped
  10-10 C9e errors/times out, (3) hold for C20/C21.
