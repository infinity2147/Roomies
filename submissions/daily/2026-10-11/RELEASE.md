SUBMIT: submission_2026-10-11_c9e_t15.zip   (lead session 01:45; replaces the autopilot's c9e_t5 draft)

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
