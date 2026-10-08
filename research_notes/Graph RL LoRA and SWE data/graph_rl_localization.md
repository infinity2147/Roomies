# RL and learned policies for code-graph traversal / function retrieval / fault localization (2024-2026)

Note on method: ~19 tool calls; PDFs were unreadable, so numbers come from arXiv HTML/abs pages and HF cards. Anything not seen is listed under Gaps.

## Methods and results (algorithm, reward, size, data, accuracy, budget, end-to-end delta)

### Takeaway
RL-trained small agents (7B-14B) reach roughly Claude-3.7/3.5-level function localization in 4-12 tool calls. Retrieve-then-rerank (SweRank) beats agents at ~$0.01/task. Typical end-to-end gain from better localization is only +2 to +6 points resolve. RL is mostly reward = set-overlap F1/DICE/nDCG, often plus a tool-success or turn-completion term.

### Cited Findings
- LocAgent: directed heterogeneous graph (file/class/function; contain/import/invoke/inherit) plus search tools. Fine-tuned on only 768 trajectories (SFT, no RL). SWE-Bench-Lite Acc@5 file/module/function: Qwen2.5-7B-ft 88.32/81.02/64.23; 32B-ft 92.70/85.77/71.90; Claude-3.5 94.16/86.50/73.36. BM25 only 61.68 file / 31.75 function; CodeRankEmbed 84.67 / 51.82. Avg rounds 6-9; cost $0.05 (7B-ft) vs $0.66 (Claude). Pass@10 repair with Agentless edit: 33.58 -> 36.13 (32B-ft) / 37.59 (Claude), i.e. +2.5 to +4 points — [LocAgent HTML](https://arxiv.org/html/2503.09089)
- ToolTrain / RepoSearcher (ICSE'26): 6 tools (repo structure, file imports, search class/function/method, exit). SFT on 5k Claude-3.7 trajectories then RL (~18k examples from 600 repos), reward nDCG@k on ranked function list. Qwen2.5-Coder 7B/32B. SWE-Bench-Verified function Recall@1/3/5 for 32B: 49.94/64.26/68.55; file Recall@5 88.59; 7B function R@5 62.38 vs Claude-3.7+CoSIL 66.38. 7B file R@5 ablation: base 57.73, RL-only 73.18, SFT-only 79.31, SFT+RL 83.11. End-to-end (Agentless patching) resolved: 32B 31.6 vs CoSIL 26.4 vs Agentless 25.8; 7B 14.0 vs 10.8 vs 7.6. Max turns not stated — [ToolTrain](https://arxiv.org/html/2508.03012v2)
- RepoNavigator ("One Tool Is Enough", ICML 2026): a single tool, jump-to-definition of a called symbol. GRPO from Qwen2.5-7B/14B/32B-Instruct (no distillation), ~4k SWE-smith samples, 1 epoch, group 8, max 12 tool calls. Reward = 0.5*DICE(pred, gold) + 0.5*tool-call success rate. SWE-bench Verified function F1/IoU: 7B 27.49/26.43; 14B 29.23/26.84; 32B 34.09/32.30; file F1 51.63/58.90/67.75. Best 32B baseline OrcaLoca 28.72 F1. RL-only 7B function IoU 26.43 vs SFT-only 24.01 vs none 15.46. More tools hurt: Jump only 24.28 IoU vs four tools 13.71 (7B). Tokens per task on SWE-bench Pro (14B): 2.68k vs LocAgent 48.86k, RepoSearcher 26.66k, Agentless 22.2k, CoSIL 8.44k. End-to-end Verified (14B): Agentless 10.12, LocAgent 13.01, RepoSearcher 12.47, RepoNavigator 14.74, +RL 15.03 — [RepoNavigator](https://arxiv.org/html/2512.20957) ; ICML page [here](https://icml.cc/virtual/2026/poster/63517)
- CodeScout (OpenHands, arXiv 2603.17829): bash-only (rg/find/grep/ls) plus a structured LocalizationFinish tool; explicitly no repo graph or static analysis. GSPO, Qwen3-14B, 9,600 SWE-smith instances (128 repos), 300 RL steps, max 4 turns per episode as listed on the card; reward = multi-level F1 (file+module+function) + auxiliary turn-completion reward. 1.7B is SFT-warm-started on 4K perfect 14B trajectories then RL. Instance F1 (14B): Verified file 68.57 / func 40.32; Lite 71.84 / 44.43; Pro 53.63 / 28.74. 4B: Verified 68.52/36.78. 1.7B: 55.46/28.22 — [CodeScout-14B card](https://huggingface.co/OpenHands/CodeScout-14B), [summary](https://featherless.ai/models/OpenHands/CodeScout-14B)
- A2Agent (arXiv 2608.29831, Aug 2026): action-aware RL, per-turn advantage by comparing turns sharing the same history (depth 2) blended with trajectory advantage; reward = F1 over file/module/function + "discovery-commit ratio" (explored gold actually included in answer) + per-turn credit for newly discovered gold. LoRA on Qwen3-4B/8B; SFT on 1,410 successful teacher trajectories; 6 tools including TraverseGraph; capped at 20 calls, avg 11.72 turns (LocAgent 6.2, CoSIL 17.55). 8B Verified F1 file/module/func 73.31/47.98/41.01. 4B localization + fixed repair: 38.07% resolved vs LocAgent 31.78% vs oracle 45.93% (so localization is worth up to ~8 pts there). Ablation: SFT-only loses 7.11 file F1 — [A2Agent summary](https://www.alphaxiv.org/abs/2608.29831.md) (secondary summary; not verified against paper)
- SweRank (retrieve+rerank, no agent): SweRankEmbed 137M/7B bi-encoder, SweRankLLM 7B/32B listwise reranker, trained on SweLoc (67,341 initial PR pairs from 3,387 repos). SWE-Bench-Lite function Acc@5/10: Embed-Large 71.90/82.12; LLM-Large 81.39/88.69 vs LocAgent(Claude-3.5) 73.36/77.37. File Acc@5 95.99. LocBench function Acc@10 71.25 vs 59.29. Cost $0.011-0.015/task vs $0.66 — [SweRank](https://arxiv.org/html/2505.07849)
- CoSIL: training-free, LLM walks module call graph then function call graph with pruner; Qwen2.5-Coder-32B top-1 43.3% (Lite), 44.6% (Verified); resolve gain inside Agentless +2.98% to +30.5% (relative) — [CoSIL](https://arxiv.org/abs/2503.22424)
- OrcaLoca: priority-queue of candidate actions, relevance scoring, distance-aware context pruning; SWE-bench Lite function match 65.33% (196/300), file 83.33% — [OrcaLoca](https://arxiv.org/pdf/2502.00350) (via search summary)
- SHERLOC (2606.24820): training-free reasoning LLM + compact tools + self-recovery; 84.33% file Acc@1 Lite (Qwen3-235B), 81.27% recall@1 Verified; locations + diagnoses to repair agents give +5.95 pts resolve avg on Verified; -36.7% localization tokens; states agents spend ~half their budget locating — [SHERLOC abs](https://arxiv.org/abs/2606.24820)
- LARGER (2605.16352): lexically-anchored active-set expansion over a repository graph (frontier loop from lexical anchors with confidence-filtered local retrieval, commit-aware graph maintenance); +13.9 file Acc@5 on LocBench over strongest baseline (tuned) / +11.8 (fixed hyperparams); no external graph DB needed; call cost not in abstract — [LARGER abs](https://arxiv.org/abs/2605.16352)
- RepoGraph (ICLR'25): plug-in line-level graph with k-hop ego-graph retrieval; reported ~32.8% average relative resolve gain across RAG/Agentless/SWE-agent/AutoCodeRover on Lite (secondary source; unverified) — [RepoGraph](https://arxiv.org/abs/2410.14684)
- GREPO (2602.13921): benchmark of 86 Python repos, 47,294 bug tasks, heterogeneous Directory/File/Class/Function graphs, GNNs (GAT/GATv2 best per secondary summary) beat IR baselines; metric Hit@K; numbers not retrieved — [GREPO](https://arxiv.org/abs/2602.13921v1), code https://github.com/qingpingmo/GREPO
- Agentless hierarchical localization (file -> class/function -> line, embedding + LLM): baseline in tables above, Lite function Acc@5 58.76 with Claude-3.5 — [LocAgent tables](https://arxiv.org/html/2503.09089)

### Inferences
- Reward recipe consistent across papers: set-overlap (F1/DICE/IoU) at function level, with a format/tool-success or turn-completion shaping term; nDCG only when the output is a ranked list. A2Agent's discovery-commit term is the closest to a frontier-aware reward.
- Training data scale is small: 0.8k (LocAgent SFT) to 18k; 4k-10k RL instances suffice for gains, so our 260 tasks plus SWE-smith-type external data is not absurd for a reranker or LoRA.
- Localization delta to resolve is modest (+2 to +6 pts typical; oracle gap 8 pts in A2Agent), consistent with our finding it is not the bottleneck.

### Gaps
- Not found: CORTEXA details (searches returned nothing). GFlowNet/MCTS-over-code-graph localization papers: not searched in depth, none surfaced. LocAgent/SweRank/SHERLOC PDFs unreadable; SHERLOC per-level tables, GREPO Hit@K numbers, Agentless original numbers not retrieved. "Cost-Effective Repository Exploration for Agentic Issue Localization" (2608.29675) body not readable.

## Robustness: missing/stale graphs, cross-repo, small models

### Takeaway
Evidence is thin on missing graphs, but the best-performing small agents (CodeScout, RepoNavigator) either need no graph (grep/bash) or a single language-server-like jump tool, and they generalize to SWE-bench Pro. Quantized-model results: not found.

### Cited Findings
- CodeScout uses no static analysis or graph and still matches/beats graph agents; trained on SWE-smith and tested on Verified/Pro/Lite — [CodeScout card](https://huggingface.co/OpenHands/CodeScout-14B)
- RepoNavigator generalizes from SWE-smith training to SWE-bench Pro (Python): 7B function F1 14.29, 14B 18.06, 32B 20.72 vs Verified 27-34 (a drop of roughly half) — [RepoNavigator](https://arxiv.org/html/2512.20957)
- More tools degrade small models: 7B function IoU 24.28 (1 tool) vs 13.71 (4 tools) — same source.
- CodeScout 1.7B with SFT+RL beats Qwen3-14B base by 10-18% F1 — [CodeScout 1.7B card](https://huggingface.co/OpenHands/CodeScout-1.7B/blob/main/README.md)
- LocAgent 7B fine-tuned on 768 trajectories retains most of the Claude score (Lite function Acc@5 64.23 vs 73.36) — [LocAgent](https://arxiv.org/html/2503.09089)
- LARGER maintains graph across commits (commit-aware alignment) and needs no graph DB — [LARGER](https://arxiv.org/abs/2605.16352)

### Inferences
- Performance drop on harder/unseen repos (Pro) is a domain-shift effect for everyone; no paper isolates "graph missing". A self-built ast graph at runtime (our path a) is the safest fit since it removes the dependency on organizer graphs.
- A frozen 31B model at int4 QAT with a minimal tool surface should follow the "fewer tools" lesson.

### Gaps
- No paper found ablating stale/missing graph or int4/QAT quantization effects on localization.

## Best localization per tool call under a 10-20 call cap

### Takeaway
Per call, best evidence: retrieve-then-rerank (SweRank: one retrieval + one rerank, function Acc@10 88.69 on Lite, ~$0.01) and minimal-tool RL agents (RepoNavigator ≤12 calls, 2.7k tokens; CodeScout ≤4 turns). Multi-tool agents use 6-17 turns with 10x+ tokens for similar or lower accuracy.

### Cited Findings
- Turns: LocAgent 6-9 rounds, A2Agent 11.7, CoSIL 17.6, RepoSearcher 12.5, OpenHands 13-15 — [LocAgent](https://arxiv.org/html/2503.09089), [A2Agent](https://www.alphaxiv.org/abs/2608.29831.md)
- Tokens: RepoNavigator 2.68k vs LocAgent 48.86k — [RepoNavigator](https://arxiv.org/html/2512.20957)
- SweRank rerank cost 0.011-0.015 USD vs LocAgent 0.66 — [SweRank](https://arxiv.org/html/2505.07849)
- Published curves of Hit@k vs number of calls under a hard cap: not found (A2Agent and RepoNavigator vary turn limit in figures only).

### Inferences
- With a 10-20 call cap, spending 0-2 calls on a retrieval+rerank prior and the rest on verification/jumps dominates agent-only exploration.

### Gaps
- No budget-capped Hit@k-vs-calls comparison across methods exists in what I found.

## Implementation path for our setup

### Takeaway
Given 149/171 failures already read the gold file, do (a) only, as a cheap skill; treat (b) as a low-cost optional research artifact; skip (c) for score, do it only if the paper is the goal.

### Inferences (no direct source; reasoned from above)
- (a) Training-free: a script walks /workspace with ast (defs, calls by name, imports, inheritance), BM25 over function text/docstrings/paths, seeds = top-k BM25 nodes plus identifiers/tracebacks from the issue, then expands 1-2 hops (callers/callees, same-class siblings) scoring frontier nodes by seed score * decay + lexical match, emits ranked top-10 functions with 3-line snippets in one call. Cost: 1-2 days, zero GPU, 1 tool call. Expected gain: small (localization not bottleneck); BM25 alone gives 31.75 function Acc@5 on Lite vs 64-73 for agents, so graph expansion/rerank should close part of this gap. Matches LARGER's lexical anchor + active-set idea and CoSIL/RepoGraph hop expansion. Independent of organizer graphs.
- (b) Learned frontier reranker: features per candidate (BM25, embedding sim, hop distance, edge type, in/out-degree, path match, symbol overlap with issue), label = node in patch diff. Train LightGBM/small MLP (LambdaRank, nDCG reward as in ToolTrain) on 260 tasks plus SWE-smith/SweLoc-style external patches (mining patches is cheap; labels free). A contextual-bandit variant learns which edges to expand. Cost: ~2-4 days, CPU-only, minutes to train. Expected: improvement in Hit@k at fixed calls; end-to-end effect +0 to +3 pts (extrapolating LocAgent/SHERLOC deltas of +2.5 to +6).
- (c) LoRA GRPO localization policy on the Gemma-31B: needs rollouts on 4xL4-class budget with long contexts; reference recipes use 8-16 A100-80G, 4k-10k instances (RepoNavigator, CodeScout). Cost: high (days of GPU, risk to the frozen-base constraint, interferes with main agent LoRA). Gain bounded by the localization-to-resolve gap, likely ≤ +3 for us. Not recommended for the competition.

### Gaps
- Real cost/gain for our setup unmeasured; run (a) as eval first: compute Hit@k vs calls on our 260 tasks and on the 22 non-gold-read failures.

## Novelty for a paper

### Takeaway
Gap is real: no found work reports budget-capped Hit@k vs calls curves across methods, nor RL-trained rerankers over a graph-expansion frontier as a cheap standalone module.

### Cited Findings
- Closest prior: A2Agent (per-turn advantage with TraverseGraph tool) — [A2Agent](https://www.alphaxiv.org/abs/2608.29831.md); LARGER (active-set frontier, heuristic, no learning stated) — [LARGER](https://arxiv.org/abs/2605.16352); GREPO (GNNs without agent loop) — [GREPO](https://arxiv.org/abs/2602.13921v1); SweRank (rerank without graph traversal) — [SweRank](https://arxiv.org/html/2505.07849)

### Inferences
- Candidate contributions: (1) benchmark protocol: Hit@k / nDCG vs number of tool calls (1,2,5,10,20) for BM25, SweRank-style, graph-expansion, and agents, including missing/stale-graph conditions; (2) a bandit/LambdaRank frontier reranker trained from patch->node labels, transferable across repos; (3) robustness to degraded graph (rebuilt ast graph vs organizer graph vs none) and int4 models; (4) link to the "localization is not the bottleneck" finding: show downstream resolve vs oracle localization gap at our scale.
- Risk: novelty claims depend on my limited search (~19 calls); do a proper literature check for GFlowNet/MCTS localization before claiming.

### Gaps
- GFlowNet/MCTS graph-localization literature not verified either way.
