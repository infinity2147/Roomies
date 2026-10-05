# Gemma-4 SWE Agent — Research & Execution Plan (v2)

**Project:** RL-guided graph retrieval + lightly-tuned Gemma-4-31B for autonomous bug fixing
**Target:** Kaggle "Gemma 4 Developer Agent" competition (submission deadline Dec 2) + paper track (Nov 12)
**Thesis framing (primary):** "Reinforcement-learned graph traversal for fault localization in repository-scale code, paired with a small instruction-tuned LLM for repair."
**Thesis framing (fallback, see §10):** "Localization baselines on unseen repositories, and closing the pass@k–pass@1 gap with rejection-sampling fine-tuning."

This file is executed step-by-step with Claude Code. Each phase lists deliverables, file layouts,
and pass/fail gates. Do not advance past a gate that fails.

**v2 changes (Oct 2):** status recorded per phase; priorities reordered around the finding that
the model *can* solve far more tasks than it solves in a single run (pass@k ≫ pass@1), which makes
rejection-sampling SFT (Phase E) the main competition lever; Phase D re-scoped as data-gated;
two rule-safe data sources added (mined git history, wheels-based synthetic bugs); measurement
protocol tightened; paper fallback added.

---

## 0. Ground rules

1. **Two deliverables, one codebase.** Localization research (RL traverser) → paper.
   Full agent (retriever + Gemma repair loop) → competition. Every experiment logs metrics usable for both.
2. **Generalization is the metric.** Test repos are private and unseen. Validation is
   leave-one-repo-out (LORO). Never tune on the repo you report on.
3. **Localization has free supervision.** Gold `patch` → changed lines → graph nodes. No test execution needed.
4. **Cheap before expensive.** BM25 → embeddings → supervised ranker → RL traverser. RL must beat
   ranker + graph expansion on held-out repos or it ships only as a paper ablation.
5. **The harness is the law.** Anything that doesn't survive local `adk-eval-core` evaluation doesn't exist.
6. **(new) Measure with enough tasks and seeds to see real differences.** One task on a 30-task run
   ≈ 3.3%; on 107 tasks ≈ 0.9%. Version comparisons use the §8 protocol, never single 30-task Kaggle runs.
7. **(new) Freeze the scaffold before collecting training data.** SFT trajectories must come from the
   exact prompts/tool format the final agent uses. Prompt changes after data collection invalidate the data.

---

## 1. Status board (update at every gate)

| Phase | Status | Done | Open |
|---|---|---|---|
| A. Harness & baseline | Mostly done | Data audit; local harness without Docker (107/129 valid tasks); model served locally + on Kaggle; Kaggle eval pipeline; B0 smoke run | Full B0 measurement (§8); **LoRA smoke test**; Option A/B memo |
| B. Ground truth & baselines | Partly done | B1 patch→node labels (91% mapped); B2 BM25 / embedding / supervised ranker / graph smoothing over 3 LORO folds + report | B3 external data + own graph builder (rules unconfirmed); new rule-safe sources B4, B5 |
| C. Scaffold | Mostly done | C1–C6 iterations; repo-tools skill; triage tool; packaging; C4 submitted; C6a ready | Freeze C6a; formal C6a vs B0 measurement on all 107 tasks |
| D. RL traverser | Not started | — | Data-gated: ranker ≤ BM25 with 3 training repos; needs B3/B5 |
| E. Gemma LoRA | Not started | Identified as the biggest lever (8 runs solved 14 distinct tasks; single runs solve far fewer) | Everything; blocked only on LoRA smoke test |
| F. Integration & submission | Not started | — | Everything |

---

## 2. Priority queue (execute top to bottom; parallelize where marked)

| # | Item | Phase | Unblocks | Notes |
|---|---|---|---|---|
| P1 | Settle external-data legality | B3 | B3, D, E-scale | Read Rules tab "External Data and Tools"; post on forum; record answer in `reports/rules.md` |
| P2 | Freeze C6a as `scaffold-v1-frozen` (git tag) | C | E1 | No prompt edits after this without re-collecting data |
| P3 | LoRA smoke test on QAT checkpoint | A | E | Trivial adapter must load via `adapter:` and change outputs locally + on Kaggle |
| P4 | Reference measurement: C6a ×4 seeds, B0 ×2 on 107 tasks | A, C | All comparisons | Produces the baseline row in `reports/scoreboard.md` |
| P5 | Failure triage on stochastic tasks | C | D go/no-go for competition | Tasks solved in some runs but not others: wrong location vs wrong fix |
| P6 | E1 on in-house data (107 tasks LORO + B4 mined commits) | E | E2, F | Starts right after P3; does not wait for P1 |
| P7 | B4 mined-commit tasks (parallel with P6) | B | E1 volume, B2 retrain | Rule-safe: built only from competition snapshots |
| P8 | B5 wheels-based synthetic localization data (parallel) | B | D | Rule-safe; adds ~10 repos for ranker/RL |
| P9 | B3 external data (only if P1 = allowed) | B | D, E scale | |
| P10 | Option A/B memo | A | D5 | Short: skills run Python → Option A favored; open question is whether a policy is worth shipping |
| P11 | Paper-direction decision (§10) | — | Paper | Decide after first ranker results on B5/B3 data |
| P12 | Phase F hardening + final selection | F | Submission | |

---

## 3. Repository layout

```
swe-gemma/
├── PLAN.md
├── data/                       # symlink → server folder with Kaggle data
│   ├── tasks.jsonl  snapshots/  graphs/  embeddings/  wheels/  docker/
│   ├── sandbox/  sample_submission/  HARNESS_README.md
│   └── derived/                # targets.jsonl, mined_tasks.jsonl, synth_loc.jsonl, ...
├── src/
│   ├── dataio/                 # loaders: tasks, graphs, embeddings, snapshots
│   ├── groundtruth/            # patch → node mapping
│   ├── mining/                 # (new) B4: git-history task mining
│   ├── synth/                  # (new) B5: bug injection + issue generation
│   ├── retrieval/              # bm25, embed, ranker, features
│   ├── rl/                     # env, policy, bc, pg
│   ├── graphbuild/             # own AST graph builder
│   ├── agent/                  # prompts, yaml templates, skill scripts
│   ├── sft/                    # trajectory farm, formatting, LoRA training
│   └── eval/                   # localization metrics, harness driver, triage, scoreboard
├── experiments/                # <date>_<name>/{config.yaml, metrics.json, notes.md}
├── submission/                 # submission tree (agent.yaml at root)
├── scripts/                    # run_*.sh entry points
└── reports/                    # scoreboard.md, rules.md, optionAB.md, memos, paper figures
```

---

## 4. Phase A — Environment, harness, baseline

### Done
- [x] A1 data audit
- [x] A2 local harness (Docker-free; 107/129 tasks valid — list of the 22 invalid tasks and reasons kept in `reports/invalid_tasks.md`)
- [x] A3 model served locally and on Kaggle; Kaggle eval pipeline
- [x] B0 smoke run
- [x] A4 sandbox probe: skills execute Python scripts

### Open
- [ ] **P3 LoRA smoke test.** Train a 10–50 step dummy LoRA (e.g. teach a fixed phrase), place in
      `adapters/smoke/`, reference with `adapter: smoke`, verify: (a) loads on the QAT
      w4a16 checkpoint locally, (b) loads in the Kaggle eval pipeline, (c) output changes as
      expected, (d) tokens/sec penalty measured. Record target modules and rank limits that work.
- [ ] **P4 B0 full measurement** (see §8 protocol).
- [ ] **P10 `reports/optionAB.md`.** Also probe from inside a skill script: numpy availability,
      access to graph JSON, max runtime, size limit for resource files.

**Gate A:** B0 measured per §8; LoRA smoke test green locally and on Kaggle; memo written.

---

## 5. Phase B — Ground truth, baselines, data

### Done
- [x] B1 gold localization labels (91% of tasks mapped)
- [x] B2 R1 BM25, R2 embedding, R3 supervised ranker, R3+G graph smoothing, 3 LORO folds, report
      — finding: **R3 does not beat BM25 with 3 training repos** (data-limited, not method-limited)

### B3 External data (only if P1 = allowed)
- [ ] Ingest SWE-bench train / SWE-Gym / SWE-smith metadata; log provenance.
- [ ] `src/graphbuild/`: AST call/dependency graph builder, schema-identical to Kaggle graphs.
      Parity check on the 4 known repos: ≥90% node-id overlap for functions/classes.
- [ ] Run B1 mapping → `targets_ext.jsonl`.
- [ ] Embedding caveat: organizers' 256-d model unspecified → features must work without embeddings.

### B4 (new) Mined tasks from git history — rule-safe
Snapshots keep all history before `base_commit`; this mirrors the organizers' own curation pipeline.
- [ ] `src/mining/mine.py`: walk history of each repo snapshot; select commits touching both
      `*.py` source and `test_*.py`/`*_test.py`; exclude refactors, docs-only, huge diffs
      (> ~5 files or > ~300 lines), merges.
- [ ] Split each commit into `patch` (source) and `test_patch` (tests); problem statement from
      commit message + linked PR/issue text if present in message; else have Gemma write a
      bug-report-style statement from the diff **without revealing the fix** (store generator
      prompt + flag `synthetic_statement=true`).
- [ ] Verify fail-to-pass / pass-to-pass with the local harness at the parent commit, using
      `/wheels` for deps; keep only verified tasks.
- [ ] **Leakage guard:** drop any mined commit that is at or after any eval task's `base_commit`
      in the same repo, and any commit whose diff overlaps an eval task's gold patch.
- [ ] Output `data/derived/mined_tasks.jsonl` (same schema as `tasks.jsonl` + `source`, `synthetic_statement`).
- [ ] Report count per repo and verification yield.

### B5 (new) Wheels-based synthetic localization data — rule-safe
`wheels/` contains source for ~10 additional packages (starlette, urllib3, httpcore, pytest,
older pydantic, transitive deps). Localization labels need no tests.
- [ ] Unpack pure-Python wheels → source trees; build graphs with `graphbuild`.
- [ ] `src/synth/inject.py`: per package, sample functions and apply bug mutations
      (off-by-one, wrong comparison operator, dropped argument/kwarg passthrough, swapped
      branch, missing None/empty check, wrong default, wrong exception type, sync/async path
      divergence). Target node = mutated function (+ siblings sharing the logic, if any).
- [ ] `src/synth/issue.py`: Gemma writes an issue from the observable symptom (call snippet +
      wrong vs expected behavior), never naming the mutated function unless a user would
      plausibly see it in a traceback. Mix: ~40% with traceback, ~60% behavior-only.
- [ ] Filter: drop issues whose text contains the target function name more than a real issue
      would (calibrate against name-mention rate in real tasks from B1).
- [ ] Output `data/derived/synth_loc.jsonl` (`instance_id, package, issue, target_nodes`).
- [ ] **Distribution check:** retrain R3 on synthetic + 3 real repos, eval on held-out real repo.
      If synthetic helps R3 on real held-out repos → green light for D on this data.

**Gate B:** P1 answered; B4 yields ≥200 verified tasks or documented reason; R3 retrained on
B5 (and B3 if allowed) beats R1 BM25 on ≥2 of 3 LORO folds — otherwise D stays paper-only.

---

## 6. Phase C — Scaffold (competition floor)

### Done
- [x] C1–C6 iterations, repo-tools skill, triage tool, packaging; C4 submitted; C6a ready

### Open
- [ ] **P2 freeze:** tag `scaffold-v1-frozen` at C6a. Changes after this go into a new tag and
      require re-collecting SFT data for any adapter trained on the old format.
- [ ] **P4 measurement:** C6a ×4 seeds and B0 ×2 on all 107 tasks (§8). Kaggle 30-task runs
      remain a pipeline smoke check only.
- [ ] **P5 stochastic-task triage:** for every task with 0 < successes < k across runs, label
      each failing run with the triage buckets {wrong location, right place / wrong fix,
      malformed tool call, loop/timeout, no patch, repro-ok-but-hidden-test-miss}.
      Output `reports/stochastic_triage.md` with bucket shares.
      **Decision rule:** if wrong-location < ~25% of failures on stochastic tasks, Phase D is
      paper-only for the competition and all competition effort goes to E.

**Gate C:** C6a pass@1 > B0 pass@1 beyond noise (§8); tool-call error rate < 5%; mean time/task within budget.

---

## 7. Phase D — RL traverser (thesis core; data-gated)

**Starts only when Gate B passes.** Until then, no D code beyond the env spec and unit tests.

### D1. MDP (`src/rl/env.py`) — spec frozen before training
- Episode: one task. Horizon H from B1/B5 seed→target distance stats (start H=20).
- State: issue features (anchors; embeddings if available) + frontier of visited nodes with
  features from `retrieval/features.py` (shared with R3).
- Actions: `EXPAND(node, edge_type ∈ {calls, called_by, imports, contains})`, `MARK(node)`, `STOP`.
  Pointer-style scoring over candidates → variable frontier, no fixed action dim.
- Reward: terminal F_β(marked, targets), β favoring recall, − λ·steps. Optional shaping:
  +Δ(min graph distance frontier→targets) (ablatable).
- Pure Python + optional numpy, so it runs inside a skill script (Option A).

### D2. Policy
- v1 linear/MLP scorer over [issue ⊕ node ⊕ edge-type] features.
- v2 GNN-lite (2-layer message passing over frontier) only if v1 plateaus. Weights < 5 MB.

### D3. Training
- [ ] BC warm start on shortest paths seeds→targets (B5 + B3 if allowed); validate LORO on real tasks.
- [ ] REINFORCE + learned baseline; PPO only if variance hurts. Curriculum near → far. Entropy bonus early.
- [ ] Early-stop on LORO MRR on **real** tasks only.

### D4. Ablations (paper table, LORO, 3 seeds)
| ID | System |
|---|---|
| R1 / R2 / R3 | BM25 / embedding / supervised ranker (3 real repos) |
| R3-syn | R3 trained with B5 synthetic data |
| R3+G | ranker + k-hop expansion |
| BC | imitation only |
| BC+PG | full method |
| −embed | no embedding features |
| −shaping | terminal reward only |
| −synth | RL trained without B5 data |

### D5. Deployment
- Option A: `skills/locate/scripts/traverse.py` + `weights.npz`; input issue text + seed ids;
  output ranked nodes + subgraph summary. Graph from provided data if reachable, else
  `graphbuild` over `/workspace` (cache per task).
- Option B (fallback): distill traversal trajectories into `loc_lora` via SFT.
- [ ] End-to-end A/B inside frozen scaffold, §8 protocol.

**Gate D:** BC+PG > R3+G (best variant) on LORO Recall@5 beyond seed noise; end-to-end not worse
than E-best. Otherwise ship best non-RL retriever; RL becomes an ablation/negative result.

---

## 8. Measurement protocol (applies to every competition-facing claim)

- **Task set:** the 107 locally valid tasks. Report per-repo and overall.
- **Seeds:** ≥4 runs per configuration (≥2 for B0). Same sampling config across compared systems.
- **Report:** pass@1 as mean ± std across runs; pass@k (any of k runs) with k = number of runs;
  number of tasks solved in all runs ("stable") vs some runs ("stochastic").
- **Significance rule:** a difference counts only if it exceeds 2× the larger std, or holds in
  paired per-task comparison (McNemar / paired bootstrap over tasks, p < 0.05).
- **LORO for anything trained:** adapters/rankers trained on 3 repos, evaluated on the 4th; rotate.
  Untrained scaffold changes can be reported on all 107.
- **Kaggle runs:** pipeline validation and sanity only. Public LB (~60 tasks, 1 task ≈ 1.7%) is not a selection criterion.
- `reports/scoreboard.md`: one row per (system, date), columns
  `{pass@1 mean, std, pass@k, stable, stochastic, time/task, tool_err_rate, tokens/task}`.

---

## 9. Phase E — Gemma fine-tuning (main competition lever)

**Why first:** 8 runs solved 14 distinct tasks; single runs solve far fewer. The model already has
the capability; rejection-sampling SFT turns occasional successes into consistent ones.

### E0. Prerequisites
- [ ] P3 LoRA smoke test green.
- [ ] P2 scaffold frozen.
- [ ] `src/sft/format.py`: render trajectories in the **exact** harness chat template and
      tool-call JSON; round-trip one trajectory through the local harness parser. Loss on
      assistant tokens only (including tool-call tokens).

### E1. Rejection-sampling SFT on in-house data (starts now, no external data needed)
- [ ] **Trajectory farm** (`src/sft/farm.py`): frozen scaffold, temperature 0.6–0.8, n = 8–16
      samples per task, on (a) the 107 tasks, (b) B4 mined tasks. Store full trajectories +
      pass/fail + time + tokens.
- [ ] **Keep** test-passing trajectories. Per task keep up to 2–3 distinct passing trajectories,
      preferring shorter ones; cap per-task share so a few easy tasks don't dominate.
- [ ] **Hygiene filters:** drop trajectories with tool errors that weren't recovered, scratch files
      left in the patch, edits to existing test files, or near-timeout runs.
- [ ] **LORO training:** 3 folds; each adapter trained on 3 real repos + all B4 mined tasks
      (excluding mined tasks from the held-out repo), evaluated on the held-out real repo.
      Final adapter for submission: trained on everything.
- [ ] LoRA starting config: r = 16, α = 32, lr 1e-4, 1–2 epochs, attention + MLP projections
      (adjust to what P3 proved works on the QAT checkpoint).
- [ ] Eval per §8 → **E1 row** in scoreboard. Expected signature of success: pass@1 rises toward
      pass@k; tool-call errors and timeouts drop.
- [ ] **Overfitting watch:** per-repo LORO variance; if the held-out repo gains nothing while
      training repos jump, reduce epochs / increase mined-data share.

### E2. Expert iteration ×2
- [ ] Re-farm with the E1 adapter (new passes on previously unsolved tasks), retrain from base on
      the union, re-evaluate. Stop when LORO gain is within noise.

### E3. Scale-out (only if P1 = allowed)
- [ ] Farm on external executable tasks (SWE-Gym / SWE-smith envs). Same filters. Retrain.

### E4. (Stretch) Reward-weighted / GRPO on the coder
- Reward: +1 tests pass, +0.3 patch applies & repro passes, +0.1 patch applies, − length penalty.
- Prefer trajectory-level reward-weighted SFT (RAFT-style) over full GRPO on 31B unless compute is ample.

### E5. (Optional) Separate analyzer adapter
- If triage shows localization errors remain significant, train `loc_lora` on the analyzer
  sub-agent's successful localization segments (target nodes from B1/B4 as the success criterion
  — no test execution needed).

**Gate E:** E-best > C6a on LORO pass@1 beyond noise (§8); time/task not worse; no single-repo collapse.

---

## 10. Paper direction (decide at P11)

Deadline Nov 12. D has not started, so the paper has two possible stories:

| | Primary: RL traversal | Fallback: localization + consistency |
|---|---|---|
| Core claim | RL graph traversal localizes faults better on unseen repos | Graph/lexical localization baselines on unseen repos; pass@k–pass@1 gap and how much rejection-sampling SFT closes it |
| Needs | Gate B passed (B5/B3 data), D3 trained, D4 table | B2 (done), B5 R3-syn result, §8 measurements, E1–E2 results |
| Risk | High (data + engineering) | Low (mostly from work already planned) |
| Uses organizers' graph dataset | Yes | Yes |

**Decision rule:** if R3-syn beats BM25 on held-out real repos and BC trains cleanly by the
decision date, write the primary paper with fallback results as supporting sections; otherwise
write the fallback paper and include any D results as a preliminary section.

Either way, collect now: B1 mapping stats, seed→target distance histograms, B2 LORO table,
§8 pass@k/pass@1 curves, triage bucket shares.

---

## 11. Phase F — Integration, hardening, submission

- [ ] Final tree in `submission/`; zip from inside so `agent.yaml` is at root. Validator: YAML
      parses, all `!include` resolve, no `../` or symlinks, adapters have config + safetensors,
      size limits respected.
- [ ] Stress tests: empty hints; very large repo; graph tools return nothing (fallback to grep +
      BM25); analyzer timeout (coder continues with partial report); low per-task limit drill
      (still submits a patch).
- [ ] `eval_config.yaml`: per-task limit tuned from §8 time/task data plus setup margin.
- [ ] Kaggle run with the LoRA submission early (as soon as E1 exists) to validate adapter loading end-to-end.
- [ ] Final selection by §8 LORO results, not public LB. Submit best + runner-up if two slots.

---

## 12. Experiment hygiene

- ≥3 seeds for any RL claim; ≥4 runs for any end-to-end claim; mean ± std always.
- Fixed metrics schemas: localization `{recall@k, mrr, ndcg10, steps}`; end-to-end per §8.
- `experiments/<date>_<name>/notes.md`: hypothesis → result → decision.
- Decision memos in `reports/` at every gate (they become paper prose).
- Folds automated so a held-out repo can never leak into training — including via B4 mined tasks.
- `KNOWN_RISKS.md` (owner + probe date each):
  - QAT + LoRA compatibility (P3)
  - External-data legality (P1)
  - Synthetic-issue distribution shift (B5 distribution check)
  - Mined-task leakage into eval (B4 leakage guard)
  - Embedding model unknown for new repos
  - 12-hour budget: parallel vs serial task execution on Kaggle
  - SFT data invalidated by scaffold changes (P2 freeze)

---

## 13. Claude Code task queue

One session per item; each session reads this file, takes the next unchecked box, implements,
runs, records metrics, ticks the box, appends to notes.

1. **P1** rules check → `reports/rules.md`
2. **P2** freeze C6a (tag + note)
3. **P3** LoRA smoke test (local + Kaggle)
4. **P4** §8 measurement harness + C6a ×4 / B0 ×2 → `reports/scoreboard.md`
5. **P5** stochastic-task triage → decision on D for competition
6. **E0** SFT formatting + round-trip test
7. **B4** git-history mining + verification + leakage guard
8. **E1** trajectory farm → filter → LORO LoRA training → eval
9. **B5** wheels unpack → graphbuild → bug injection → issue generation → distribution check
10. **E2** expert iteration
11. **P10** Option A/B memo
12. **P11** paper-direction decision
13. **D1–D5** (only if Gate B passes)
14. **B3 / E3** (only if external data allowed)
15. **F** validator, stress tests, Kaggle adapter run, final selection