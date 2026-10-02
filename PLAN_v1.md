# Gemma-4 SWE Agent — Research & Execution Plan

**Project:** RL-guided graph retrieval + lightly-tuned Gemma-4-31B for autonomous bug fixing
**Target:** Kaggle "Gemma 4 Developer Agent" competition (submission deadline Dec 2) + paper track (Nov 12)
**Thesis framing:** "Reinforcement-learned graph traversal for fault localization in repository-scale code, paired with a small instruction-tuned LLM for repair."

This file is written to be executed step-by-step with Claude Code. Each phase lists concrete
deliverables, commands, file layouts, and pass/fail gates. Do not advance past a gate that fails.

---

## 0. Ground rules (read once, keep forever)

1. **Two deliverables, one codebase.** The localization research (RL traverser) is the paper.
   The full agent (traverser + Gemma repair loop) is the competition entry. Every experiment
   must log metrics usable for both.
2. **Generalization is the metric.** Test repos are private and unseen. All validation is
   leave-one-repo-out (LORO) over {fastapi, rich, requests, httpx}. Never tune on the repo
   you report on.
3. **Localization has free supervision.** Gold `patch` → changed lines → graph nodes. No test
   execution needed to train the retriever. Exploit this everywhere.
4. **Cheap before expensive.** BM25 → embeddings → supervised ranker → RL traverser, in that
   order. RL must beat the supervised ranker on held-out repos or it doesn't ship (it can
   still be a paper ablation).
5. **The harness is the law.** Anything that doesn't survive `adk-eval-core` local evaluation
   doesn't exist. Re-read `HARNESS_README.md` whenever behavior surprises you.

---

## 1. Repository layout (create this first)

```
swe-gemma/
├── PLAN.md                     # this file
├── data/                       # symlink → server folder with Kaggle data
│   ├── tasks.jsonl
│   ├── snapshots/  graphs/  embeddings/  wheels/  docker/
│   ├── sandbox/  sample_submission/  HARNESS_README.md
├── src/
│   ├── dataio/                 # loaders: tasks, graphs, embeddings, snapshots
│   ├── groundtruth/            # patch → node mapping
│   ├── retrieval/              # bm25.py, embed.py, ranker.py (supervised), features.py
│   ├── rl/                     # env.py (MDP), policy.py, bc.py (imitation), pg.py (REINFORCE/PPO)
│   ├── graphbuild/             # own AST graph builder (for external repos + sandbox fallback)
│   ├── agent/                  # prompts, yaml templates, skill scripts
│   ├── sft/                    # trajectory collection, formatting, LoRA training
│   └── eval/                   # localization metrics, end-to-end harness driver, reports
├── experiments/                # one folder per run: config.yaml, metrics.json, notes.md
├── submission/                 # the actual submission.zip tree (agent.yaml at root)
├── scripts/                    # run_*.sh entry points, one per phase
└── reports/                    # tables/figures for paper + decision memos
```

Conventions:
- Every experiment gets `experiments/<date>_<name>/` with `config.yaml`, `metrics.json`,
  `notes.md`. Metrics JSON schema fixed in Phase 2 so all runs are comparable.
- Python 3.13 (match sandbox), `uv` or venv, `pytest` for our own code.
- Git: `main` always runs end-to-end; branches per phase.

---

## 2. Phase A — Environment, harness, baseline agent (gate before everything)

**Goal:** a one-command local evaluation of any submission folder, plus a measured baseline.

### A1. Data audit
- [ ] `src/dataio/audit.py`: load `tasks.jsonl` (expect 129), verify every `instance_id` has a
      snapshot, graph, embedding archive. Print per-repo counts, graph sizes (nodes/edges),
      embedding dims (expect 256), patch sizes (files/hunks changed).
- [ ] Sanity: unpack one snapshot, `git log -1` matches `base_commit`; apply gold `patch` +
      `test_patch`, run pytest → must pass (pass-to-pass); `test_patch` alone → must fail
      (fail-to-pass). Script this for 5 random tasks per repo.

### A2. Harness up
- [ ] Build `swebench-sandbox:latest` from `data/docker/`.
- [ ] Run `sample_submission/` on 3 tasks via the local CLI from `HARNESS_README.md`.
- [ ] Then full 129-task run. Record: resolve %, wall time/task, tokens/task, tool-call
      error rate. This is **baseline B0**.
- [ ] Write `scripts/eval_submission.sh <submission_dir> <task_subset>` — the single
      entry point used for the rest of the project.

### A3. Serving check
- [ ] Serve `gemma-4-31b-it-qat-w4a16-ct` (vLLM w/ compressed-tensors, or the harness's own
      server). Measure tok/s and max context at our VRAM. Budget: ~6 min/task if serial over
      120 tasks in 12h — confirm from HARNESS_README whether tasks run parallel.
- [ ] **LoRA smoke test now, not later:** train a 10-step dummy LoRA, load it on the QAT
      checkpoint through the harness `adapter:` mechanism, verify generation changes and
      nothing crashes. QAT + LoRA interactions are the #1 silent risk.

### A4. Sandbox capability probe (decides Option A vs B from our design)
- [ ] Dummy skill with a script that: prints `sys.version`, tries `import numpy`, lists
      `/workspace` and any mounted data, attempts to read a graph JSON, writes/reads a file,
      times out behavior. Run via `run_skill_script` in local harness.
- [ ] **Decision memo `reports/optionAB.md`:**
      - numpy + file persistence available → **Option A**: RL policy ships as skill script
        (pure-python/npz weights) called by Gemma.
      - else → **Option B**: RL goes into a Gemma LoRA (GRPO over graph tools) and the
        analyzer sub-agent plays the traverser.
      Everything in Phase D is written to work under either; only the deployment shim differs.

**Gate A:** `eval_submission.sh` reproduces B0 within ±2 tasks on a rerun; LoRA smoke test green; Option A/B memo written.

---

## 3. Phase B — Ground truth & localization baselines (the cheap science)

**Goal:** target-node labels for every task + three baselines the RL must beat.

### B1. Gold localization labels
- [ ] `src/groundtruth/map_patch.py`: parse gold `patch` with unidiff → changed (file, line)
      spans → match to graph nodes whose `text` covers those lines (re-locate node line spans
      by searching `node.text` in the file at `base_commit`; cache offsets).
- [ ] Output `data/derived/targets.jsonl`: `{instance_id, target_nodes[], target_files[]}`.
- [ ] QC: % of tasks where every changed span maps to ≥1 node; manually inspect 10 misses
      (new-file additions won't map — record them, they need file-level fallback).
- [ ] Stats for the paper: distribution of #target nodes/task, and **graph distance from
      seeds to targets** (computed after B2) — this motivates traversal depth.

### B2. Seeds + baselines (all evaluated LORO, metrics: Recall@{1,5,10,20}, MRR, nDCG@10)
- [ ] **Seeding:** union of (a) embedding top-k vs issue text (`embeddings/*.npz`, cosine),
      (b) BM25 over node texts, (c) lexical anchors — symbols/paths/error strings regex'd
      from `problem_statement` + `hints_text` matched to node ids/names.
- [ ] **Baseline R1 — BM25 only.**
- [ ] **Baseline R2 — embedding only.**
- [ ] **Baseline R3 — supervised ranker:** LightGBM/LambdaMART (or logistic) over
      `src/retrieval/features.py`: lexical overlap, trigram sim, embedding cos, anchor hits,
      node degree/type, file path signals, seed-distance. Train LORO.
- [ ] Also compute **1-hop and 2-hop graph expansion of R3's top-k, re-ranked** (R3+G) —
      this is the "graph helps, no RL yet" ablation and the number RL must beat.
- [ ] `reports/localization_baselines.md` with the LORO table.

### B3. External data for scale (feeds Phases D & E)
- [ ] Pull SWE-bench train / SWE-Gym / SWE-smith task metadata (issue + gold patch + repo@commit).
      **Check competition rules on external data first; log provenance.**
- [ ] `src/graphbuild/`: our own AST call/dependency graph builder (python `ast` + import
      resolution), schema-identical to Kaggle graphs. Validate: build graphs for the 4 known
      repos at their base commits, compare node coverage vs provided graphs (target ≥90%
      node-id overlap on functions/classes).
- [ ] Run B1 mapping on external tasks → large `targets_ext.jsonl` (aim: 5–20k instances).
- [ ] Embeddings for external repos: organizers' 256-d model is unspecified → **policy
      features must degrade gracefully without embeddings.** (Ask on Kaggle forum; if model
      identified, backfill.)

**Gate B:** targets for ≥95% of mappable tasks; LORO baseline table exists; external set ≥5k instances with graphs.

---

## 4. Phase C — Scaffold v1: prompts, workflow, skills (competition floor)

**Goal:** a strong non-RL agent. This alone must beat B0 clearly; it's also the vehicle
that any retriever plugs into.

### C1. Agent architecture (ADK YAML)
```
submission/
├── agent.yaml                  # root coder (Gemma, adapter: edit_lora later)
├── sub_agents/analyzer.yaml    # read-only localizer AgentTool (adapter: loc_lora later)
├── prompts/{system.md, analyzer.md, repair.md}
├── configs/sampling.yaml       # temp ~0.2–0.4 coder, 0.6 analyzer; max_tokens tight
├── skills/
│   ├── locate/                 # SKILL.md + scripts: find_def.py, find_tests.py, (policy later)
│   └── pyhelpers/              # run_focused_pytest.sh, strip_scratch.sh
└── eval_config.yaml            # per-task time limits
```

### C2. Workflow encoded in prompts (6 stages, hard step caps)
1. **Parse issue** → anchors (symbols, error strings, expected behavior). ≤2 steps.
2. **Localize** → call analyzer tool; it uses grep → `search_similar_code` →
   `get_code_neighbors`/`get_code_subgraph` → `read_file` top-3; returns ≤400-token report
   (locations + why + sibling code paths sharing the logic). ≤12 analyzer steps.
3. **Reproduce** → minimal script from the issue example; must fail. Skip after 2 attempts.
4. **Fix** → minimal `edit_file`; **fix every flagged sibling path (sync/async, subclasses)**;
   **use the issue's exact names/messages** (hidden tests call the described API).
5. **Verify** → rerun repro; `grep` tests dir for the module → `pytest -x` that file; one
   repair cycle on failure.
6. **Submit** → delete scratch files (submit_patch stages untracked!), never edit existing
   test files, **always call `submit_patch`** (empty = guaranteed 0). Budget watchdog: on
   `get_status` low-time, jump to 6 with best patch.

### C3. Measure
- [ ] Full 129 LORO-style eval (prompts tuned only on 3 repos, reported on 4th, rotate) → **C1 score**.
- [ ] Failure taxonomy script `src/eval/triage.py`: buckets = {wrong location, right place/wrong
      fix, malformed tool call, loop/timeout, no patch, repro-ok-but-hidden-test-miss}.
      Iterate prompts on the top bucket; 2–3 iterations max before moving on.

**Gate C:** C1 ≥ B0 + 10pts absolute (or best-effort documented); tool-call error rate <5%; mean time/task ≤ 6 min.

---

## 5. Phase D — The RL traverser (thesis core)

**Goal:** a policy that, given issue + seeds, walks the code graph and emits target nodes;
beats R3+G on LORO Recall@5 / MRR.

### D1. MDP (`src/rl/env.py`) — frozen spec before any training
- **Episode:** one task. Horizon H=20 steps (tune from B1 distance stats).
- **State:** issue features (anchor set, embedding if available) + frontier = visited nodes
  with per-node feature vectors (features.py from B2 — shared with ranker, deliberately).
- **Actions:** `EXPAND(node, edge_type ∈ {calls, called_by, imports, contains})`,
  `MARK(node)`, `STOP`. Action space = per-candidate scoring (pointer-style), so variable
  frontier size is fine with a shared scorer — no fixed action dim.
- **Reward:** terminal F_β(marked, targets) with β favoring recall (repair can filter, can't
  recover misses) − λ·steps. Shaping (flagged, ablatable): +Δ(min graph distance frontier→targets).
- **Observation builder is pure-python + optional numpy** → runs under Option A sandbox.

### D2. Policy (`src/rl/policy.py`)
- v1: linear/MLP scorer over [issue ⊕ node ⊕ edge-type] features (ships anywhere, tiny).
- v2 (if v1 plateaus): 2-layer message-passing over frontier (GNN-lite). Keep weights <5MB.

### D3. Training
- [ ] **BC warm start (`rl/bc.py`):** shortest paths seeds→targets (from B1) as expert
      trajectories; teach EXPAND-toward-target + MARK-on-target + STOP. Train on external set
      (targets_ext), validate LORO on Kaggle tasks.
- [ ] **Policy gradient (`rl/pg.py`):** REINFORCE + learned baseline first; PPO only if
      variance hurts. Curriculum: near targets (≤2 hops) → far. Entropy bonus early.
- [ ] Log per epoch: Recall@k, MRR, steps/episode, on train and LORO val. Early-stop on LORO MRR.

### D4. Ablations (paper table, run all LORO)
| ID | System |
|----|--------|
| R1/R2/R3 | BM25 / embed / supervised ranker |
| R3+G | ranker + k-hop expansion |
| BC | imitation only |
| BC+PG | full method |
| −embed | full method, no embedding features (unseen-repo realism) |
| −shaping | terminal reward only |

### D5. Deployment
- **Option A:** `skills/locate/scripts/traverse.py` + `weights.npz` resource; input = issue
  text + seed node ids (Gemma passes anchors), output = ranked nodes + induced subgraph
  summary. Graph source: provided tools' data if reachable, else `graphbuild` over /workspace
  (cache per task).
- **Option B:** distill the policy into Gemma — generate traversal trajectories in harness
  tool-call format from the trained policy, SFT `loc_lora`; optionally GRPO on top with the
  localization reward (group size 8, reward = Recall@5 of nodes the agent reads).
- [ ] End-to-end A/B inside Scaffold v1: analyzer-with-traverser vs analyzer-without, LORO
      resolve rate → **D score**.

**Gate D:** BC+PG > R3+G on LORO Recall@5 by a margin > run-to-run noise (3 seeds); end-to-end D ≥ C1. If RL ≤ R3+G after honest effort: ship R3+G in the agent, write RL as negative/ablation result in paper — that is still a thesis chapter, not a failure.

---

## 6. Phase E — Gemma fine-tuning (kept light, as designed)

**Goal:** `edit_lora` (coder) + `loc_lora` (analyzer, if Option B) that raise resolve rate
without wrecking generality.

### E1. SFT via rejection sampling
- [ ] Run Scaffold+retriever on external executable tasks (SWE-Gym/smith envs) with
      temp 0.6–0.8, n=4–8 samples/task. Keep only **test-passing** trajectories; dedupe;
      prefer shortest per task (speed is scored implicitly via the 12h cap).
- [ ] `src/sft/format.py`: render trajectories in the **exact harness chat template &
      tool-call JSON** — validate by round-tripping one through the local harness parser.
- [ ] Train LoRA (r=16–32, lr 1e-4, 1–2 epochs, loss on assistant tokens only). Check it
      loads on the QAT checkpoint (A3 pipeline).
- [ ] Eval LORO end-to-end → **E1 score**. Watch regression on tool-format errors (should ↓).

### E2. Expert iteration ×2
- [ ] Re-sample with E1 model, keep new passes (harder tasks now solvable), retrain. Stop
      when LORO gain < noise.

### E3. (Stretch) GRPO on the coder
- Reward: +1 tests pass, +0.3 patch applies & repro passes, +0.1 patch applies, −len penalty.
- Only if E2 plateaus and compute allows; 31B GRPO is expensive — consider trajectory-level
  RAFT/RRHF-style instead of full PPO machinery.

**Gate E:** E ≥ D on LORO; no repo overfitting (per-repo variance not exploding); time/task not worse.

---

## 7. Phase F — Integration, hardening, submission

- [ ] **Assemble final tree** in `submission/`; `zip -r submission.zip .` from inside it
      (agent.yaml at root). Validator script: yaml parses, every `!include` resolves, no
      `../`/symlinks, adapters have config+safetensors, total size within limits.
- [ ] **Stress tests:** task with empty hints; huge repo snapshot; graph tool returning
      nothing (traverser must fall back to grep+BM25); analyzer timeout (coder proceeds with
      partial report); clock-pressure drill (artificially low per-task limit → still submits).
- [ ] **eval_config.yaml:** per-task limit ≈ 5–6 min, global watchdog margin for sandbox setup.
- [ ] **Kaggle dry run early** (even with C1 scaffold) to validate the upload pipeline.
- [ ] Final selection = best **LORO** score, not public LB (public ≈60 tasks ⇒ 1 task ≈1.7%,
      pure noise magnet). Submit both best-LORO and runner-up if two slots.
- [ ] **Paper (Nov 12):** story = "RL graph traversal for fault localization on unseen repos";
      contributions = free-supervision labeling pipeline, MDP + pointer policy, LORO ablation
      table (D4), end-to-end deltas (C1→D→E). Figures from `reports/`. Uses the released
      graph/embedding dataset ⇒ matches organizers' encouraged topics.

---

## 8. Experiment hygiene (RL-researcher discipline)

- 3 seeds minimum for any RL claim; report mean±std. One task ≈ 0.8% — never celebrate <3-task deltas.
- Fixed metrics schema: `{recall@k, mrr, ndcg10, steps, resolve_rate, time_per_task, tool_err_rate}`.
- `notes.md` per experiment: hypothesis → result → decision. Decision memos in `reports/` at
  gates A, B, D (they become paper prose for free).
- Never train on httpx-fold while reading httpx-fold results. Automate the folds so this is
  impossible to get wrong.
- Keep a `KNOWN_RISKS.md`: QAT+LoRA compat, sandbox numpy, embedding-model mystery,
  parallel-vs-serial 12h budget, external-data legality. Each risk gets an owner + probe date.

---

## 9. Claude Code task queue (how we actually execute this file)

Work through these as discrete Claude Code sessions; each maps to checkboxes above:

1. `A1` data audit + sanity harness (src/dataio, scripts)
2. `A2–A3` harness driver + serving + LoRA smoke test
3. `A4` sandbox probe + Option A/B memo
4. `B1` patch→node ground truth + stats
5. `B2` seeds, features, R1–R3, R3+G, LORO eval harness
6. `B3` external data ingest + graphbuild parity check
7. `C1–C3` scaffold v1 (yaml+prompts+skills) + triage loop
8. `D1–D2` env + policy (unit-tested on toy graphs first)
9. `D3` BC then PG training runs
10. `D4–D5` ablations + deployment shim + end-to-end A/B
11. `E1–E2` trajectory farm, SFT format, LoRA train, expert iteration
12. `F` validator, stress tests, Kaggle dry run, paper assembly

Each session: read this file, pick the next unchecked box in the current phase, implement,
run, record metrics, tick the box, append to notes.
