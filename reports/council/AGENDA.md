# Research Council — Agenda and Decision Rules (2026-10-02)

Lead: principal investigator (synthesis + decisions). Members work in parallel on CPU only; Kaggle/GPU runs continue separately.

## Objective
Maximize the private-leaderboard resolution rate by 2026-12-02 and produce a defensible paper by 2026-11-12,
spending scarce GPU time only on interventions that the evidence says will move the score.

## Research questions, hypotheses and pre-registered decision rules

| # | Question | Hypothesis | Owner | Decision rule (fixed before seeing results) |
|---|---|---|---|---|
| Q1 | Why do stochastic tasks succeed in some runs and fail in others? | H1: failures diverge after the gold file is reached (fix completeness / spec misreading), not at localization. | Trajectory forensics | If ≥60% of stochastic failures reach a gold file → prioritize repair-side interventions + SFT (E1); else prioritize localization. |
| Q2 | Is there headroom for learned graph traversal over BM25 on unseen repos? | H2: gold is usually within 1–2 hops of BM25 top-10, but BM25 already ranks it top-5 in most tasks, so headroom is small (<10 pts Recall@5). | Localization scientist | Phase D proceeds as a competition lever only if the RL-addressable set is ≥15% of tasks AND file-level misses explain ≥20% of end-to-end failures; otherwise D is paper-only. |
| Q3 | Can we train a LoRA that vLLM applies correctly on the QAT checkpoint, at what cost? | H3: QLoRA-style training on the frozen W4A16 weights is feasible on one 80 GB GPU; bf16-base training risks mismatch. | Training engineer | Proceed to E1 when the tiny end-to-end test passes and a ≤1-day, ≤1 GPU recipe exists; user arranges hardware. |
| Q4 | Are our measurements and data valid? | H4: no critical leakage; some local-vs-scorer environment bias. | Methodology reviewer | Any "critical" issue blocks the dependent decision until fixed. |
| Q5 | What paper can we defend by Nov 12? | H5: the fallback framing (localization baselines + pass@k gap + RFT) is achievable; RL framing is high risk. | Paper strategist | Choose framing at P11 using Q2 + E1 evidence; draft structure now. |

## Running experiments (owner: lead)
- Kaggle: LoRA smoke on scorer HW; C6a×4 and B0×2 on 107 tasks (reference measurement; captures SFT data). Status: queued (Kaggle L4 congestion).
- Local: synthetic issue generation (B5), self-healing supervisor.
- Leaderboard: C4 pending; C6a to submit after 05:30 (1/day limit).

## Synthesis protocol
When all members report: (1) check each report's claims against its evidence; (2) cross-examine conflicts (e.g. forensics vs localization on how much localization matters); (3) write `reports/council/DECISIONS.md` with decisions, owners, next experiments, and expected impact; (4) update PLAN.md status board.
