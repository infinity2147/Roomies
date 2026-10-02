# Localization headroom: is there room for a learned graph traverser over BM25?

Author: council / localization scientist. Date: 2026-10-02. CPU only (12 procs at most).
Code: `src/analysis/localization/{common,oracle,file_vs_node,cheap_baselines}.py`.
Raw outputs: `experiments/council_localization/{per_task.pkl, oracle.md, file_vs_node.md, cheap_baselines.md, cheap_baselines.json, e2e_per_task.json}`.
To reproduce: `.venv/bin/python -m src.analysis.localization.common` (builds the cache in about 12 s), then run `oracle`, `file_vs_node` and `cheap_baselines --seeds 3`.

## Question
Is there real, learnable headroom for an RL graph traverser over BM25 for node-level fault localization on unseen
repositories? How large is it? Would better localization move the competition score?

## Hypotheses
- **H1 (graph headroom):** many gold nodes that BM25 misses lie a few hops from BM25 or anchor seeds, so traversal adds coverage that ranking alone cannot reach.
- **H2 (learnability):** cheap learned or tuned systems already beat BM25 under leave-one-repo-out (LORO) evaluation, which suggests an RL policy could do better still.
- **H3 (relevance):** node or file localization limits end-to-end pass rate.

## Setup
- 117 tasks have at least 1 gold node (`data/derived/targets.jsonl`): fastapi 60, rich 45, requests 11, httpx 1.
- Candidates are the non-test graph nodes. The query is the issue plus its hints.
- BM25, the anchors and the graph come from `src/retrieval/context.py` and `features.py`. Metrics come from `src/eval/loc_metrics.py`.
- My BM25 numbers reproduce `reports/localization_baselines.md` exactly: MRR 0.398, R@5 0.384.

## 1. Oracle / upper-bound analyses (no learning)

### (a) BM25 top-N, n=117, 95% bootstrap CI
| N | recall@N | hit@N |
|---|---|---|
| 1 | 0.183 [0.12,0.25] | 0.282 |
| 5 | 0.384 [0.30,0.47] | 0.513 [0.43,0.61] |
| 10 | 0.457 | 0.573 |
| 20 | 0.569 | 0.692 |
| 50 | 0.685 | 0.803 |
| 100 | 0.771 | 0.846 |

### (b,c) Expanding seed sets over the undirected graph, compared with BM25 at an equal candidate budget
The equal-budget column takes, for each task, the BM25 top-|C| where |C| is the size of the expanded set C.

| seeds | hops | size median (p90) | recall | hit | BM25 equal-budget recall | BM25 equal-budget hit | tasks where gold is reachable only via the graph (not in BM25 top-100) |
|---|---|---|---|---|---|---|---|
| BM25 top-5 | 1 | 14 (29) | 0.474 | 0.598 | **0.503** | **0.641** | 4 |
| BM25 top-5 | 2 | 53 (206) | 0.621 | 0.709 | **0.687** | **0.786** | 18 |
| BM25 top-10 | 1 | 29 (52) | 0.566 | 0.667 | **0.592** | **0.709** | 8 |
| BM25 top-10 | 2 | 97 (300) | 0.730 | 0.812 | **0.744** | **0.821** | 25 |
| BM25 top-20 | 1 | 55 (90) | 0.660 | 0.761 | **0.680** | **0.786** | 13 |
| BM25 top-20 | 2 | 149 (411) | **0.832** | **0.897** | 0.782 | 0.846 | 31 |
| anchors | 0/1/2 | 0/0/0 (7/35/90) | 0.191/0.250/0.297 | 0.256/0.291/0.316 | 0.209/0.336/0.398 | 0.291/0.402/0.444 | 3/6/7 |
| anchors + BM25 top-5 | 2 | 68 (228) | 0.668 | 0.744 | **0.707** | **0.795** | 21 |

**Fact:** graph expansion has lower recall than BM25 at the same candidate budget everywhere except the very large BM25 top-20 + 2-hop set (median 149 nodes, p90 411).
- Only 58/117 tasks have any anchor seed. Anchor seeds alone hit gold on 26–32% of tasks.
- The graph is sparse: median non-test degree is 1–2, and 36% of fastapi non-test nodes are isolated (computed inline from `graph_index`).

### (d) Undirected distance from BM25 seeds to the nearest gold node (task counts)
| distance | from top-1 | from top-5 (min) | from anchors (min) |
|---|---|---|---|
| 0 | 33 | 60 | 30 |
| 1 | 11 | 10 | 4 |
| 2 | 14 | 13 | 3 |
| 3 | 9 | 10 | 7 |
| 4 | 18 | 8 | 4 |
| 5–6 | 6 | 8 | 10 |
| unreached (>8 hops, or no seeds) | 26 | 8 | 59 |

### The RL-addressable set
BM25 misses every gold node in its top-5 on **57/117 tasks (48.7%)**. Breaking those 57 down:

**Where BM25 still ranks the gold node (pure re-rank, no graph needed):**

| case | tasks | share of all 117 |
|---|---|---|
| gold in BM25 ranks 6–20 | 21 | 17.9% |
| gold in BM25 ranks 21–50 | 13 | 11.1% |
| gold in BM25 ranks 51–100 | 5 | 4.3% |
| **total, ranks 6–50** | **34** | **29%** |

**How close the gold node is in the graph:**

| case | tasks | share of all 117 |
|---|---|---|
| gold ≤1 hop from top-5 or anchor seeds | 14 | 12.0% |
| gold ≤2 hops from top-5 or anchor seeds | 27 | 23.1% |
| ≤2 hops away and **not** in BM25 top-50 (only the graph can reach it) | **6** | **5.1%** |
| ≤1 hop away and not in BM25 top-50 | 1 | 0.9% |
| unreachable: >2 hops and not in BM25 top-100 | 13 | 11.1% |

### Ceilings: an oracle re-ranks each candidate set perfectly (BM25: hit@5 0.513, R@5 0.384, MRR 0.398)
| candidate set | median size | oracle hit@5 (= MRR ceiling) | oracle R@5 |
|---|---|---|---|
| BM25 top-20 | 20 | 0.692 (+0.18) | 0.559 (+0.17) |
| BM25 top-50 | 50 | 0.803 (+0.29) | 0.660 (+0.28) |
| BM25 top-5 + 2 hops | 53 | 0.709 (+0.20) | 0.605 (+0.22) |
| anchors + top-5, +2 hops | 68 | 0.744 (+0.23) | 0.637 (+0.25) |
| re-rank pool: BM25 top-50 ∪ 1-hop(top-10) ∪ anchors | 64 | 0.821 (+0.31) | 0.683 (+0.30) |

**Interpretation:**
- The headroom is large: about +0.3 hit@5 and R@5, and +0.42 MRR at most.
- About 85–90% of it is re-ranking headroom: the gold node is already in BM25 top-50.
- The headroom that only graph traversal can supply is ≤6/117 tasks (≈+0.05 hit@5 at most).
- H1 is rejected as stated: the graph mostly re-finds what BM25 already ranks.

## 2. File vs node level, and whether it matters end to end

### Offline file vs node accuracy (n=117 common tasks)
| system | file@1 | file@3 | file@5/6 | node@1 | node@5 |
|---|---|---|---|---|---|
| BM25 (node ranking collapsed to files) | 0.496 | 0.667 | 0.786 | 0.282 | 0.513 |
| deployed `locate.py` skill (`results/locate_skill_eval.jsonl`) | 0.487 | 0.667 | 0.795 | 0.282 | 0.479 |

The skill script is byte-identical in c1 and c6a.

### End to end (8 Kaggle runs × 30 tasks = 240 task-runs; `results/kaggle/*_n30`)
- **Right file is necessary:**
  - 166 task-runs produced a non-test patch, and 140 of them (84%) touched a gold file.
  - P(resolved | touched a gold file) = 68/140 = **0.49**.
  - P(resolved | touched only non-gold files) = **1/26**.
- **But right file is far from sufficient:** half of the right-file patches still fail.
- **Failure buckets across all 240 runs** (from `reports/triage_c*_n30.md`):

  | bucket | task-runs |
  |---|---|
  | right_file_wrong_fix | 72 |
  | agent_error (mostly timeouts) | 46 |
  | **wrong_location** | **25 (10%)** |
  | no_patch | 23 |
  | touched_tests_only | 5 |

  15 of the 25 wrong_location runs come from the same 8 tasks. Those are tasks where the agent touches a gold file in ≤2/8 runs, and their solve rate is 0.03. In 5 of those 8 tasks BM25 already ranks the gold file in its top 3.
- **The agent barely uses the localizer:**
  - `locate.py` was called 99 times in 240 task-runs, almost all in c1 and c2.
  - In C6a it was called 6 times in 30 tasks. The agent localizes with grep (`run_command`).
- **Offline localization quality hardly predicts outcomes (n=29–30 tasks):**
  - Tasks where the skill gets file@3 right solve 0.355 vs 0.188 when it misses (Δ=+0.17, permutation p=0.29).
  - The same comparison for BM25 node@5 gives Δ=+0.09 (p=0.57).
  - Spearman correlation between solve rate and BM25 MRR is 0.10.

**Conclusion for the agent:** file-level localization is the level that matters, and it is mostly good enough already. Node-level ranking does not reach the agent, because the agent does not consume it.

**Optimistic ceiling for the competition:** suppose perfect localization turned every wrong_location run into a right-file run at the observed 0.49 conversion rate. That gives ≈12/240 task-runs, or **≤ +5 pp pass@1**. Realistically it is much less, because these 8 tasks are hard tasks with timeouts.

## 3. Cheap baselines without RL (LORO over fastapi/rich/requests; httpx is trained on all three; LightGBM uses 3 seeds)
| system (ALL n=117) | R@1 | R@5 | hit@5 | MRR | file@1 | file@3 |
|---|---|---|---|---|---|---|
| BM25 | 0.183 | 0.384 | 0.513 | 0.398 | 0.496 | 0.667 |
| RRF: BM25 + name-BM25 + anchor + module/dotted bonus (tuned LORO) | 0.205 | 0.387 | 0.521 | **0.431** | 0.521 | **0.701** |
| RRF + embedding cosine | 0.182 | 0.392 | 0.530 | 0.405 | 0.487 | 0.675 |
| 2-stage LambdaMART re-rank of the 64-node pool, no embeddings | 0.169±0.007 | 0.366±0.014 | 0.490±0.015 | 0.386±0.005 | 0.479±0.028 | 0.695±0.011 |
| same, all 38 features | 0.163±0.015 | 0.358±0.004 | 0.487±0.007 | 0.385±0.011 | 0.476±0.008 | 0.670±0.008 |
| (oracle re-rank of the same pool) | 0.537 | 0.683 | 0.821 | 0.821 | 0.829 | 0.829 |

The 2-stage LambdaMART re-rank pool is BM25 top-50 ∪ 1-hop(top-10) ∪ anchors.

**Paired bootstrap vs BM25 (ALL):**

| system | ΔMRR [95% CI] | ΔR@5 [95% CI] |
|---|---|---|
| RRF, no embeddings | +0.032 [−0.006, +0.073] | +0.003 |
| RRF + embeddings | +0.007 [−0.035, +0.048] | — |
| LambdaMART, no embeddings | −0.011 [−0.066, +0.044] | — |
| LambdaMART, all features | +0.002 [−0.056, +0.060] | — |

**Per repo:**
- LambdaMART helps rich (MRR 0.358→0.38–0.39) and requests (0.616→0.69), but hurts fastapi (0.390→0.32).
- The tuned RRF weights are stable across folds: k=10, w_name=0.25, module bonus 0.5, dotted bonus 1.
- H2 is rejected: no system recovers more than about 8% of the oracle re-rank headroom (0.03 of 0.42 MRR), and every confidence interval includes 0. This matches the earlier finding that LambdaMART ≈ BM25 (`reports/localization_baselines.md`).

## 4. Synthetic transfer check
`data/derived/synth_issues.jsonl` has **52 rows, below the 150 threshold**.
- The last write was at 15:51.
- `results/synth_issue.log` ends in `HTTP Error 500`, so issue generation appears to have stopped.
- **Skipped** `run_synth_check`, as the brief instructs.

## Decision

**Facts (summary):**
- Total headroom over BM25 is large: up to +0.31 hit@5, +0.30 R@5 and +0.42 MRR inside a 64-node pool.
- It is almost entirely re-ranking headroom.
- Gold nodes that only graph traversal can reach exist in ≤6/117 tasks, a ≤+0.05 hit@5 ceiling.
- At equal budget, graph expansion loses to BM25 for sets under about 100 nodes.
- With 3 repos of data, no learned or tuned system beats BM25 significantly. The best is RRF at +0.03 MRR (CI includes 0).

**Phase D (RL graph traverser as the thesis core): no-go as specified.** Keep it only as a conditional go, reframed as "learned re-ranking / navigation", and only if a data gate passes first.

- **Gate:**
  - Using synthetic issues (≥150; ideally ≥500 across new packages) plus `mined_tasks.jsonl` (66), a no-embedding re-ranker must beat BM25 on real-repo LORO.
  - The bar is ΔMRR ≥ +0.05 with a CI that excludes 0, measured with `run_synth_check --seeds 3`.
  - If that fails, an RL policy using the same features has no evidence it can do better. The supervised ranker is already an upper-level proxy for its learnable signal.
- **Expected ceiling if the gate passes:**
  - Realistic: +0.05–0.10 MRR and +0.03–0.08 R@5 (H, unverified). That is roughly 10–25% of the oracle headroom, which is typical for learned re-rankers over BM25.
  - Graph-specific contribution: ≤ +0.05 hit@5.
- **Data required:**
  - At least 10 distinct repos of training signal, because LORO over 3 repos flips sign by repo.
  - Today's 117 tasks are not enough.
- **Risks:**
  - The graph is sparse and partly isolated (36% of fastapi nodes have no edges).
  - Gold sets are multi-node and heavy-tailed: median 1, maximum 131.
  - Synthetic issues may leak identifiers (the mention-rate issue).
  - Fold variance is ±0.03–0.07 MRR.

**Competition: not worth more localization effort.**
- wrong_location is 10% of task-runs.
- The agent rarely calls the localizer.
- File@3 is already 0.67.
- The upper bound is ≤ +5 pp, and the realistic gain is ≤1 task in 30, which is below the ±2.5-task standard error.
- The only cheap item worth doing: optionally switch `locate.py` to the tuned RRF (+0.03 file@3 / +0.03 MRR). Do it in a new scaffold, never c6a, and only if the agent is also pushed to call it.
- Effort is better spent on "right file, wrong fix" (72/240 task-runs) and on timeouts (46/240).

**Paper:** the strongest honest result is the negative/diagnostic one.
- Headroom is re-ranking, not traversal.
- Equal-budget graph expansion does not beat lexical retrieval on these repos.
- Learned rankers do not transfer across 3 repos.
- Localization is not the end-to-end bottleneck, since P(resolve | right file) is only 0.49.
