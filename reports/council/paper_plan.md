# Paper plan: Kaggle "Gemma 4 Developer Agent" Paper Track

Author: Paper Strategist (research council), 2026-10-02. Companion file: `reports/council/references.bib` (40 entries; each checked against the arXiv API or the publisher's page on 2026-10-02).
Scope: plan only. I did not modify any other file, use a GPU, or run any experiment.

---

## 0. Summary

- **What the track asks for (verified from the official pages, §1).** A Kaggle Writeup of at most 3,000 words. It must have a title and subtitle, abstract, introduction, methods and experiments, and related work with citations. It is scored equally on Novelty, Quality (generality), Relevance, Verifiability and Clarity, each 0–5. Deadline: 2026-11-12 23:59 UTC. Prizes: $15k Best Paper, $10k Best New Resource, $10k Best New Application. Papers that use the organizers' graph and embedding dataset are "highly encouraged".
- **Action today:** our Kaggle account has **not joined** the paper competition. `kaggle competitions list -s gemma` returns `userHasEntered=False` for `gemma-4-developer-agent-paper`. We can't submit until we join.
- **Recommended framing: the fallback paper, strengthened.** Working title: *"It Can, But It Doesn't"*. The spine is that, for a fixed 4-bit 31B model in a declarative scaffold, the bottleneck is consistency, not localization. The paper has three parts:
  - (i) a localization study on the organizers' per-commit graphs under leave-one-repository-out (LORO), plus a graph-headroom analysis;
  - (ii) the pass@k–pass@1 gap, measured properly, and how much LORO rejection-sampling LoRA closes it;
  - (iii) a taxonomy of harness failure modes for declarative agents.
- **The RL traverser becomes a subsection** if it clears a pre-registered gate by **2026-10-22**. If it doesn't, it is reported as a headroom bound or a negative result. Our evidence (BM25 ≈ LambdaMART, graph smoothing hurts, "wrong location" in only 2–5 of 30 failures) makes the RL framing high-risk with 41 days left.
- **Novelty pressure is real and recent.** GapFT (arXiv 2609.35793, 17 Sep 2026) fine-tunes on exactly the pass@k–pass@1 gap, but for single-turn reasoning. A²Agent (EMNLP 2026), RepoNavigator (2512.20957) and ToolTrain (2508.03012) train *LLMs* with RL for localization. We have to cite these and position ourselves against them (§3).

---

## 1. What the paper track requires

**Source:** `kaggle competitions pages list --content --format json gemma-4-developer-agent-paper` (Kaggle CLI 2.2.4, run 2026-10-02). The WebFetch of the competition page returned only its title, so I used the CLI's authenticated page dump instead. Both the main and paper competitions were dumped.

| Item | Official text (paraphrased or quoted) | Status |
|---|---|---|
| Deliverable | A Kaggle Writeup "that describes your methods, experiments, and other details". Must include: title and subtitle, abstract, introduction, description of the research (methods and experiments), related work and citations | Verified |
| Length | "Scope: 3,000 words maximum, reporting original, unpublished research." Non-archival | Verified. Whether references, captions and tables count toward the limit is **not stated**, so plan for them to count |
| Optional assets | Public notebook (code) via Project Links. An arXiv-ready PDF "instead of writing your paper in the Kaggle Writeup" via Public Project Link. Private resources attached to the writeup become public after the deadline | Verified |
| Judging | Five criteria, weighted equally, each 0–5, final score is the mean. **Novelty:** new insights, or properties of existing methods. **Quality:** generality beyond the competition. **Relevance:** impact on SE and agentic learning. **Verifiability:** enough detail on method, data and analysis. **Clarity** | Verified. Note that "Quality" here means *generalization*, not rigor |
| Awards | $35,000 total: Overall Best Paper $15k, Best New Resource $10k (dataset, library or tool), Best New Application $10k. "Awarded to three Submissions with the most points" | Verified. How a writeup is assigned to the Resource or Application category is **not stated** |
| Topics | Tuning & Optimization (PEFT, RL for SWE agents); Code Comprehension (code-graph generation, parsing, embedding); Tasks & Benchmarks; Graph Reasoning (LLM reasoning over large graphs) | Verified |
| Graph dataset | Main-competition Prizes page: "Submissions leveraging the accompanying released graph and embedding dataset are highly encouraged, but not a requirement" | Verified |
| Deadline | 2026-11-12 23:59 UTC. Drafts that haven't been submitted by then are not judged | Verified (CLI shows `2026-11-12 23:59:00`) |
| Submissions | 5 per day; up to **2 Final Submissions** for judging | Verified as rule text. Whether this allows two different writeups is **not verified** |
| Winner obligations | Apache-2.0 or other OSI license for the submission and code; reproducible description with training and inference code | Verified |
| Data security | "not … publish, redistribute or otherwise provide … the Competition Data to any party not participating" | Verified. **Implication:** we cannot release task files, graphs or snapshots as a "resource". We can release code (graph builder, harness patches, miners) and the B5 synthetic data, which comes from PyPI wheels; check each package's license |
| Prestige | "Winning papers will be highlighted at a Google hosted event (such as a NeurIPS expo workshop)" | Verified |

**Not verified:**
- Whether the 3,000-word limit includes references.
- Whether two writeups (paper plus resource) may be selected.
- Whether submitted writeups are publicly visible before the main competition ends on Dec 2. That last point matters strategically: the paper may reveal our method to competitors 20 days early.

Ask on the paper-track forum this week.

**How the rubric translates into plan choices:**
- **Verifiability:** a public notebook that reproduces the localization tables from the organizers' graph dataset; all numbers come from result files; LORO; paired statistics.
- **Quality (generality):** emphasize what transfers beyond this competition:
  - unseen-repo evaluation;
  - the fact that a cheap lexical retriever is enough for localization;
  - how to measure and close the consistency gap of small models;
  - harness traps any SWE-bench-style evaluator has.
- **Novelty:** the decomposition into "can solve" vs "does solve" under a fixed quantized model, plus the measured headroom of graph traversal on organizer graphs. Don't claim RFT itself as novel.
- **Relevance:** offline, single-node, quantized open model. This is the competition's stated mission ("consumer hardware").

---

## 2. Related work survey (by theme; keys refer to `references.bib`)

**Benchmarks.**
- SWE-bench [jimenez2024swebench] introduced repository-level issue resolution scored by hidden tests. It defined the BM25 retrieval baseline and the Lite subset.
- SWE-bench Verified [openai2024verified] is a 500-task human-validated subset.
- Our setting is a SWE-bench clone with four properties:
  - repositories that are unseen at test time;
  - a *fixed* 4-bit model;
  - a 12 h total budget;
  - organizer-supplied per-commit code graphs.
- Recent work shows that single-run agent scores are noisy: tens of runs are needed to separate agents [delarubia2026identical]. This supports our ≥4-seed protocol and paired tests.

**Agent scaffolds.**
- SWE-agent [yang2024sweagent] shows that the agent–computer interface (tool design and format) matters as much as the model.
- OpenHands [wang2025openhands] is the open generalist platform. AutoCodeRover [zhang2024autocoderover] adds AST-aware code search. Moatless Tools [orwall2024moatless] is a tool-centric ReAct agent.
- Agentless [xia2025agentless] shows that a fixed localize→repair→validate pipeline competes with agents.
- Our declarative ADK setting is an extreme form of "interface is the method": no Python entry point, so all control flow goes through prompts and skills. Our tool-call format-leakage finding (markdown backticks corrupting Gemma's native string delimiters) is a concrete agent–computer-interface failure in the SWE-agent sense.

**Fault / code localization.**
- Graph-guided LLM agents: LocAgent [chen2025locagent] (heterogeneous code graph plus multi-hop tools), RepoGraph [ouyang2025repograph], CodeRAG [li2025coderag], OrcaLoca [yu2025orcaloca] (priority scheduling and distance-aware pruning), CoSIL [jiang2025cosil] (iterative call-graph search).
- Learned rankers: SweRank [reddy2026swerank].
- Lexical baseline: BM25 [robertson2009bm25], used as the SWE-bench retrieval baseline. Our learned ranker is LambdaMART [burges2010lambdamart].
- **Gap we fill:** these works report gains *on the same repositories they develop on* (SWE-bench's 12 repos) and rely on large LLMs at every step. We test lexical, embedding, learned-to-rank and graph-smoothed rankers **LORO on the organizers' graphs**. The finding that BM25 is not beaten with three training repos is informative for this community.

**RL for graph traversal and code search.**
- Knowledge-graph path-finding agents: DeepPath [xiong2017deeppath] and MINERVA [das2018minerva] (a query-conditioned walker trained with REINFORCE). Our traverser design is MINERVA transplanted onto code graphs.
- RL for code localization now trains the *LLM itself*: ToolTrain [ma2025tooltrain] (rejection-sampled SFT plus tool-integrated RL), RepoNavigator [zhang2025reponavigator] (a single jump-to-definition tool, RL from base), A²Agent [kim2026a2agent] (action-aware rewards for the "discovery–commit gap").
- **Our distinct angle:** a tiny (<5 MB) non-LLM policy that runs on CPU inside a skill script, for settings where the LLM is fixed and costly. Expert iteration [anthony2017exit] links the traverser's BC→PG schedule to the agent-level self-training below.

**Training SWE agents.**
- Environments and data: SWE-Gym [pan2025swegym] (executable environments; rejection-sampling fine-tuning of trajectories and verifiers), SWE-smith [yang2025swesmith] (synthetic bug injection at scale; our B5 is a small rule-safe analogue), R2E-Gym [jain2025r2egym] (procedural environments and hybrid verifiers).
- Training methods: SWE-RL [wei2025swerl] (RL on software-evolution data; our B4 history mining is in the same spirit), SWE-Dev [wang2025swedev] (training and inference scaling), SWE-ZERO→HERO [ludwig2026swehero] (execution-free then execution-based SFT).
- All of these fine-tune bf16 open models in research scaffolds. **None is constrained to a fixed W4A16 checkpoint plus LoRA served by vLLM inside a declarative harness with context compaction.**

**Self-training / rejection sampling.**
- STaR [zelikman2022star], RFT [yuan2023rft], RAFT [dong2023raft], ReST [gulcehre2023rest] and ReST^EM [singh2024restem] all fit the policy to its own reward-filtered samples (binary-reward EM).
- **GapFT [liu2026gapft]** (Sep 2026) chooses training problems by the pass@K–pass@1 gap and decomposes gains into recovered failures vs regressions. This is the closest conceptual prior work. It is single-turn reasoning on Llama-8B; we must cite it and adopt its decomposition vocabulary.

**pass@k vs pass@1.**
- The unbiased pass@k estimator comes from Codex [chen2021codex]. Repeated sampling scales coverage roughly log-linearly [brown2024monkeys].
- RL with verifiable rewards mostly sharpens pass@1 within the base model's pass@k support [yue2025rlreasoning]. This motivates our hypothesis: RFT moves pass@1 toward pass@k but not beyond it.

**Context compaction.**
- Summarization vs observation masking [lindenbauer2025complexity]; learned compression guidelines [kang2026acon].
- Our contribution here is narrow but useful: 35 of 46 passing trajectories exceed the harness's 14,336-token compaction threshold. Supervised data must therefore be built from the *per-call prompts actually seen*, not the full trace. That is a pitfall for anyone fine-tuning agents behind a compacting runtime.

**PEFT.** LoRA [hu2022lora] on a quantized base. Training on frozen 4-bit weights is QLoRA-like; I didn't include QLoRA to stay within the 40-reference cap. Add it if the training engineer uses the QLoRA recipe.

Extra verified items, not in the .bib, that we can swap in if needed:
- SWE-bench+ (2410.06992), SWE-bench-Live (2505.23419), CodeMonkeys (2501.14723), SWE-Search (2410.20285), CodexGraph (2408.03910), SWE-Fixer (2501.05040)
- Lingma SWE-GPT (2411.00622), long-context multi-turn SWE RL (2508.03501), SWE-rebench (2505.20411), SWE-Effi (2509.09853)
- MemGPT (2310.08560), Context-as-a-Tool (2512.22087), AgentLens (2605.12925), SHERLOC (2606.24820, EMNLP 2026)
- Cost-effective repository exploration (2608.29675), "What context does a coding agent actually need to act?" (2607.09691)
- Pass@k Training (2508.10751), "Why pass@k optimization can degrade pass@1" (2602.21189), Gemma 3 tech report (2503.19786)
- QLoRA (2305.14314), UTBoost (2506.09289), SWE-Dev feature-driven (2505.16975)

---

## 3. Positioning: what is genuinely ours

**Assets no one else in the related work has:**
1. The organizers' per-commit code graphs and embeddings. The judges explicitly encourage using them.
2. LORO evaluation on truly unseen repositories, with gold node labels mapped automatically from gold patches (117/129 tasks).
3. A pass@k–pass@1 gap measured on a **fixed, quantized** 31B model on the scorer's own hardware: pass@8 = 0.467 vs pass@1 ≈ 0.29 on 30 tasks. That is 4 stable and 10 stochastic tasks.
4. The constraints of a declarative scaffold, and harness failure modes found by reading raw traces:
   - test-patch application trap: 3–4 tasks per run in C1/C2, 0 after the fix;
   - tool-call format leakage: C2 had 30/35 malformed locate calls;
   - thinking-driven timeouts: r = 0.72 between thinking volume and time;
   - budget-bound empty submissions: 13/30 in C5b;
   - compaction mismatch for SFT.
5. A graph builder with non-test node parity 1.0 to the organizers' graphs, which extends their dataset format to any repository. Also 66 history-mined verified tasks and 1,628 synthetic bugs from 22 out-of-domain packages.

### Framing A (primary, gated): RL graph traversal for localization

Defensible contributions (only if the experiments land):
- **A1.** A MINERVA-style pointer policy over the organizers' code graphs, trained with BC on shortest paths then REINFORCE, on out-of-domain synthetic bugs. Evaluated LORO on real issues. It is tiny and CPU-only, deployable as a declarative skill. This contrasts with the LLM-RL localizers (ToolTrain, RepoNavigator, A²Agent).
- **A2.** A headroom analysis: how many tasks have gold within h hops of BM25's top-k, i.e. the ceiling for any traversal. It characterizes *when* graph structure can help, using the organizers' graphs.
- **A3.** Evidence of transfer from out-of-domain synthetic data (R3-syn vs R3) to unseen real repos.

**Gate (pre-registered, decision on 2026-10-22).** All four must hold:
- (a) R3-syn beats BM25 on LORO MRR by more than 2× seed std;
- (b) BC+PG ≥ R3+G on LORO Recall@5 beyond seed noise;
- (c) Q2's RL-addressable set is at least 15% of tasks;
- (d) the traverser runs inside the skill in under 2 s.

My prior that all four pass: **≈15–20%.**
- Ranker = BM25 today (reports/localization_baselines.md: MRR .397 vs .398).
- Smoothing hurts (.385).
- 58/117 tasks have no selective anchor (facts.json `seed_dist[-1]=58`).
- Only 52/1628 synthetic issues exist so far (`wc -l data/derived/synth_issues.jsonl`).

### Framing B (recommended): localization baselines, then consistency via rejection-sampling SFT

Defensible contributions:
- **B1. A diagnosis of where a small quantized agent fails, on unseen repos.**
  - On the organizers' graphs, LORO: BM25 node MRR .398 ≈ LambdaMART .397 ± .012 > graph smoothing .385 ≫ embedding pseudo-query .112.
  - The deployed lexical locator reaches file hit@1 .49 and hit@3 .69.
  - End to end, "wrong location" is only 2–5/30 failures, while "right file, wrong fix" is 6–11/30.
  - So localization is largely *solved by BM25*, and the binding constraint is consistency.
  - Add the graph-headroom curve (A2) here. It uses the organizers' dataset either way.
- **B2. Capability ≠ reliability: measuring the gap and closing it.**
  - pass@k vs pass@1 on 107 tasks with ≥4 seeds, split into stable and stochastic tasks.
  - Then LORO rejection-sampling LoRA on the fixed W4A16 checkpoint, built from compaction-aware per-call prompts.
  - Report the GapFT-style decomposition: stochastic→stable, unsolved→solved, stable→regressed.
  - **Novel relative to GapFT and SWE-Gym:** multi-turn, tool-using, under context compaction, a fixed quantized model, unseen-repo LORO.
  - A negative or partial result is still publishable if it is decomposed. For example: "RFT converts X of 10 stochastic tasks but adds no new tasks", which is consistent with [yue2025rlreasoning].
- **B3. A harness failure taxonomy for declarative agents, with fixes and measured effects.**
  - Test-patch trap; format leakage into native tool-call syntax; thinking-time trade-off; empty submissions under tool budgets.
  - Plus the statistical protocol: one standard error is ±2.5 tasks on n = 30; paired McNemar tests.
  - This generalizes to any SWE-bench-style evaluator (rubric: Quality, Verifiability).

**Optional second writeup for Best New Resource (if two finals are allowed):** "A scorer-faithful, Docker-free SWE harness plus an organizer-compatible code-graph builder plus a rule-safe synthetic bug generator". This releases code only, never competition data. Marginal cost is about 1 day of writing. The decision depends on the forum answer about two final submissions.

### Why B over A

- B's evidence mostly exists already.
- It is robust to E1 failing: the diagnosis plus the gap measurement plus the taxonomy still stand.
- It still uses the graph dataset.
- It answers a question practitioners in the competition's mission care about: what to spend effort on with a small local model.

A is more "novel-sounding". But a negative RL result with three training repos would score low on Novelty and Quality, and the 2026 LLM-RL localizers already occupy that space.

---

## 4. Paper outline (≤3,000 words), with figure/table → evidence mapping

Working title: **"It Can, But It Doesn't: Localization Is Not the Bottleneck for a 4-bit 31B Software Agent — Consistency Is"**
Subtitle: *Graph-based localization on unseen repositories, harness failure modes of declarative agents, and closing the pass@k–pass@1 gap with rejection-sampling LoRA on Gemma-4-31B.*

| § | Words | Content | Figures / tables | Source: exists ✔ / to run ✗ |
|---|---|---|---|---|
| Abstract | 200 | §5 below | — | — |
| 1 Intro | 450 | Problem, constraints, three findings, contributions | **Fig 1** teaser: pass@k curve plus failure buckets | ✔ `reports/report/figs/passk.pdf`, triage reports; ✗ replace with 107-task C6a×4 |
| 2 Setting & data | 250 | Fixed W4A16 model, declarative ADK, scorer protocol, 107 valid tasks, LORO folds, B1 labels | **Tab 1** data and folds | ✔ `reports/report/facts.json` (audit, b1), `data/derived/valid_tasks.txt` |
| 3 Localization on unseen repos | 550 | R1–R3+G, metrics, LORO table; anchors; seed→target distances; **headroom curve**; R3-syn; (RL subsection if gated in) | **Tab 2** LORO baselines (+R3-syn row); **Fig 2** seed→target distance; **Fig 3** headroom: P(gold within h hops of BM25 top-k) | ✔ `reports/localization_baselines.md`, `figs/seed_dist.pdf`; ✗ R3-syn (`src/retrieval/run_synth_check.py`, needs synthetic issues), ✗ headroom (Q2 owner, CPU) |
| 4 From localization to repair: where agents fail | 450 | Scaffold C1–C6a; triage buckets; harness failure taxonomy with before/after | **Tab 3** config results (30 tasks); **Tab 4** failure modes, cause, fix, effect | ✔ `reports/triage_c*_n30.md`, `reports/council/trajectory_table.csv`, `figs/thinking_time.pdf` |
| 5 Capability vs reliability | 650 | pass@k estimator; 107-task ×4 seeds; stable vs stochastic; RFT data (compaction-aware segmentation); LoRA on QAT; LORO E1 results; decomposition; McNemar | **Fig 4** pass@k (base vs E1); **Tab 5** pass@1 mean±std, pass@k, stable/stochastic, time, tool errors; **Fig 5** per-task solve-rate transition (base→E1) | ✔ protocol `src/eval/scoreboard.py`, `figs/traj_len.pdf`, `reports/e0_sft_format.md`; ✗ C6a×4/B0×2 (queued Kaggle), ✗ E1 adapters + eval |
| 6 Related work | 300 | §2 condensed | — | `references.bib` |
| 7 Limitations & conclusion | 150 | 3 repos; small n; local-vs-scorer env; synthetic issue shift; single model | — | — |
| **Total** | **3,000** | Appendix material goes into the public notebook / PDF | | |

**Public notebook (verifiability):**
- Reproduces Tab 2 and Fig 2/3 from the organizers' graph dataset on Kaggle (CPU).
- Recomputes pass@k and McNemar from released per-task result tables. These are our outputs, not competition data.

---

## 5. Minimal experiment set and timeline (backwards from 2026-11-12)

### Must-have (paper is not credible without these)

| ID | Experiment | Compute | Owner | Feeds |
|---|---|---|---|---|
| M1 | Graph headroom on organizer graphs: for each task, min hop distance from BM25 top-k (k = 1, 5, 10, 20) to gold, then cumulative curve; per repo | CPU, under 1 day | Localization scientist (Q2) | Fig 3, framing gate (c) |
| M2 | R3-syn vs R3 vs BM25, LORO, 3 seeds (needs enough mention-rate-matched synthetic issues; at least a few hundred) | Issue generation on local GPU (lead) + CPU | Lead / localization | Tab 2, gate (a) |
| M3 | Reference measurement: C6a ×4 and B0 ×2 on 107 tasks, scorer hardware | Kaggle (queued) | Lead | Fig 1/4, Tab 5 baseline; also the RFT trajectory pool |
| M4 | E1: rejection-sampling LoRA, 3 LORO folds (fastapi / rich / requests+httpx), each evaluated ×4 seeds on its held-out repo (107 tasks total per seed) | Rented 80 GB GPU (train) + Kaggle (eval, about 2 h per 107-task run) | Training engineer | Tab 5, Fig 4/5 |
| M5 | Stats: paired McNemar on per-task majority outcome; GapFT-style decomposition; bootstrap CIs | CPU | Methodology | Tab 5 |

### Nice-to-have (in priority order)

| ID | Experiment | Use |
|---|---|---|
| N1 | BC→REINFORCE traverser, LORO, 3 seeds (D3/D4) | Framing A or a §3.x paragraph |
| N2 | Extra farm samples (n = 8 per task at T = 0.7) for pass@k up to 8 on 107 tasks | Stronger Fig 4 |
| N3 | E2, one round of expert iteration | Tab 5 extra row |
| N4 | Ablation: E1 trained on full traces vs compaction-aware segments | Supports the compaction claim (a strong, generalizable point) |

### Timeline

Today is Fri 2026-10-02. Keep a 2-day buffer before the deadline.

| Date | Milestone |
|---|---|
| **Oct 2** | **Join the paper competition** (`userHasEntered=False`). Create a private draft writeup. Post forum questions: word count incl. references? two writeups allowed? visibility before Dec 2? |
| Oct 3–9 | M1 (CPU). M3 runs on Kaggle. Synthetic issue generation continues. Draft §2, §4 and §6 now: their evidence is final. Build the figure script `src/analysis/paper/make_paper_figs.py` that reads only result files |
| Oct 10 | Gate B: M2 result. E1 dataset frozen from M3 passes plus mined tasks |
| Oct 10–18 | E1 LoRA training: 3 folds plus "all" (GPU rental). N1 BC traverser on CPU in parallel, if Gate B passed |
| Oct 19–31 | E1 evaluation on Kaggle (3 folds × 4 seeds). N2 farm if quota allows |
| **Oct 22** | **Framing decision (P11)** using the §3 gate. Lock the outline |
| Nov 1–3 | M5 statistics; N3/N4 only if E1 finished by Oct 28 |
| **Nov 4** | **Results freeze.** No new runs enter the paper after this |
| Nov 4–7 | Full draft (≤3,000 words), figures regenerated from files, public notebook |
| Nov 8 | Council review: each member scores the draft on the 5 rubric criteria; fix the lowest |
| Nov 9 | Final edit; word count check; citation check against `references.bib` |
| **Nov 10** | **Submit** (Final Submission selected). Optional resource writeup the same day |
| Nov 12 23:59 UTC | Hard deadline (buffer) |

---

## 6. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| E1 is late or shows no gain beyond noise | Medium | Removes the headline "closing" result | Paper B still stands on B1 + B2 (gap measurement) + B3. Report E1 as a decomposed negative or partial result. Keep the intro's claim as "measure, then attempt to close" until Nov 4 |
| Kaggle L4 congestion or weekly GPU quota delays M3/M4 | Medium–high | Fewer seeds | Prioritize C6a×4 over B0×2. Fall back to ×3 seeds and report wider CIs. Local 2-GPU server runs one sequence at a time; usable for small checks only |
| LoRA on the QAT checkpoint misbehaves at scale (quality, 21.5→15 tok/s slowdown) | Medium | E1 invalid or too slow | Q3 owner's recipe. Measure time per task in Tab 5. Speed is a reportable trade-off |
| Novelty overlap (GapFT; A²Agent; RepoNavigator; ToolTrain) | Certain | Novelty score | Cite them explicitly. Claim the multi-turn, fixed-quantized-model, LORO, declarative-harness setting and the diagnostic, not the algorithm |
| Small n (30 → 107 tasks; 3 effective repos) | Certain | Verifiability, Quality | Report ±SE, paired tests, per-repo results. State the limitation plainly |
| Local-vs-scorer environment bias (107/129 locally valid) | Low–medium | Validity | All end-to-end numbers come from scorer hardware. Q4 reviewer audit |
| Leakage: mined tasks overlapping evaluation functions | Low | Inflated E1 | The existing guard (−60-day cutoff, function-overlap filter) is described in the paper. LORO excludes the held-out repo's mined tasks |
| Competition-data redistribution in notebook or resource | Low | Disqualification | Notebook attaches the competition dataset (participants only). Release only code and our own outputs |
| The paper reveals our competition method before Dec 2 | Unknown (visibility not verified) | Competitive | Ask on forum. RFT is generic anyway. Optionally omit exact prompts and adapter details until Dec 2 |
| Word limit (3,000) forces cuts | Certain | Clarity | Fixed word budget per section (§4). Detail goes to the notebook or PDF |

---

## 7. Draft abstract and introduction (recommended framing B; numbers in [brackets] are pending M3/M4)

**Title:** It Can, But It Doesn't: Localization Is Not the Bottleneck for a 4-bit 31B Software Agent — Consistency Is
**Subtitle:** Graph-based localization on unseen repositories, harness failure modes of declarative agents, and closing the pass@k–pass@1 gap with rejection-sampling LoRA on Gemma-4-31B

**Abstract.**
Small, locally runnable language models are the obvious route to offline coding agents, but where do they actually fail? We study a fixed, 4-bit-quantized Gemma-4-31B agent that must repair real GitHub issues in unseen Python repositories through a purely declarative scaffold (prompts, skills and LoRA adapters only). We report three findings.

First, on the organizers' per-commit code graphs and under leave-one-repository-out evaluation, plain BM25 locates the faulty function as well as a supervised LambdaMART ranker (MRR 0.398 vs 0.397). Graph smoothing and embedding retrieval do not help, and only [x]% of tasks place gold code within two hops of BM25's top-10, which bounds what learned graph traversal can add. End to end, wrong localization explains only 2–5 of 30 failures.

Second, the model is far more capable than it is reliable. Across 8 scaffold runs it solves 14/30 tasks at least once (pass@8 = 0.467) but only 0.29 per run. On 107 tasks with four seeds, [s] tasks are stable and [u] are stochastic.

Third, rejection-sampling LoRA trained on the model's own successful, compaction-aware trajectories raises held-out-repository pass@1 from [a] to [b] ([p] by paired test). This comes mostly by turning stochastic tasks into stable ones rather than solving new ones.

We also document harness failure modes that silently zero scores — test-patch application traps, markdown leaking into native tool-call syntax, and thinking-driven timeouts — together with fixes and a measurement protocol. Code and a notebook reproducing all localization results from the released graph dataset are public.

**1 Introduction.**
Coding agents that resolve real issues — SWE-agent, OpenHands, Agentless and their successors [yang2024sweagent; wang2025openhands; xia2025agentless] — are usually powered by large API models. The Gemma 4 Developer Agent setting asks a different question. Given *one fixed, 4-bit, 31B open model*, a single 4×L4 node, a 12-hour budget for ~120 hidden tasks, and a declarative agent definition with no custom control code, what limits how many issues get fixed?

The community's default answer is localization. A large body of work builds code graphs and graph-navigating agents to find the code to edit [chen2025locagent; ouyang2025repograph; yu2025orcaloca; jiang2025cosil], and recent work trains the LLM itself with RL to search repositories [ma2025tooltrain; zhang2025reponavigator; kim2026a2agent]. We set out to do the same with a lightweight learned walker over the organizers' per-commit code graphs, in the spirit of MINERVA [das2018minerva]. Before training it, we measured how much room it had.

**Localization is not the bottleneck.** We label gold functions automatically from gold patches (117/129 tasks) and evaluate leave-one-repository-out on the provided graphs. BM25 [robertson2009bm25] is as good as a 29-feature LambdaMART ranker trained on the other repositories, and better than graph smoothing or the provided embeddings. A deployable, standard-library BM25 locator finds the right file first in 49% of tasks and in the top three in 69%. When we triage eight end-to-end agent configurations on the scorer's hardware, only 2–5 of 30 failures are wrong-location failures; the dominant bucket is "right file, wrong fix". A headroom analysis bounds what any graph traversal could add on top of BM25: [x]% of tasks.

**Capability is not reliability.** The same agent solves 14 of 30 tasks in at least one of 8 runs but only 8.6 per run on average (7–10). pass@k [chen2021codex] keeps rising while pass@1 stays flat, and most solvable tasks are *stochastic*. This is the regime in which self-training on one's own successes — STaR, RFT, RAFT, ReST, expert iteration [zelikman2022star; yuan2023rft; dong2023raft; gulcehre2023rest; anthony2017exit] — should help. Prior evidence [yue2025rlreasoning; liu2026gapft] suggests it sharpens pass@1 within the base model's pass@k support rather than expanding it. We test this for a multi-turn, tool-using agent, which brings two complications absent in single-turn settings:
- a fixed quantized checkpoint that only accepts LoRA adapters;
- a runtime that compacts the context once it exceeds 14,336 tokens, so 35 of 46 successful trajectories are *not* what the model actually saw.

**Harnesses fail silently.** Several of our largest early gains came from fixing failure modes invisible in aggregate scores:
- agent edits to test files that make the hidden test patch fail to apply;
- markdown backticks in instructions leaking into Gemma's native tool-call string delimiters (30 of 35 calls malformed in one configuration);
- thinking-driven timeouts;
- empty submissions under tight tool budgets.

**Contributions.**
1. A leave-one-repository-out study of lexical, embedding, learned-to-rank and graph-based localization on the organizers' code-graph dataset, with a headroom bound for graph traversal.
2. A measurement of the pass@k–pass@1 gap of a fixed quantized agent on 107 tasks with multiple seeds, and LORO rejection-sampling LoRA with compaction-aware data construction, decomposed into stabilized, newly solved and regressed tasks.
3. A taxonomy of declarative-harness failure modes with fixes and effects, plus a measurement protocol (multi-seed, paired tests) that makes one-task differences interpretable.

---

## 8. Facts vs hypotheses

**Facts** (with sources):
- Paper-track requirements in §1 (Kaggle CLI page dump, 2026-10-02).
- `userHasEntered=False` (CLI list).
- Localization numbers (`reports/localization_baselines.md`, `reports/report/facts.json`).
- C-series results (`reports/triage_c*_n30.md`; report Tab "End-to-end results").
- 52/1628 synthetic issues written so far (`wc -l`).
- 40 references verified.

**Hypotheses:**
- The RL gate passes with ≈15–20% probability.
- E1 mainly stabilizes stochastic tasks.
- The headroom figure will be small. Q2's owner should confirm.
- Writeup visibility, reference counting and whether two final writeups are allowed are all unknown.
