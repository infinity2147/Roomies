# Research Council — Shared Brief (read fully before starting)

Project root: `/home/24b4518/projects/Gemma_RL` (git repo; commit only if your charter says so — default: do NOT commit).
Full technical report: `Gemma_RL_Technical_Report.pdf` (source `reports/report/gemma_rl_report.tex`) — read the .tex for details.
Execution plan: `PLAN.md` (v2). Rules decisions: `reports/rules.md`.

## The problem
Kaggle "Gemma 4 Developer Agent": build a declarative ADK agent (YAML + prompts + skills + optional LoRA adapters) on
the fixed model `gemma-4-31b-it-qat-w4a16-ct` that fixes real GitHub issues in Python repos. Score = fraction of hidden
tasks whose hidden tests pass after the agent's patch. Hidden set ≈120 tasks, 12 h runtime, 1 submission/day.
Public data: 129 tasks (fastapi 67, rich 48, requests 13, httpx 1), repo snapshots, per-commit code graphs, node embeddings.
Deadlines: competition 2026-12-02; separate paper track 2026-11-12.

## What exists (key files)
- Data: `data/tasks.jsonl`, `data/snapshots/<id>.tgz`, `data/graphs/`, `data/embeddings/`, `data/derived/`
  (`valid_tasks.txt` = 107 locally valid tasks; `targets.jsonl` = gold target graph nodes per task (B1);
  `mined_tasks.jsonl` = 66 verified tasks from git history (B4); `synth_mutations.jsonl` = 1628 injected bugs (B5);
  `synth_issues.jsonl` = LLM-written issues for them, generation in progress).
- Localization code: `src/retrieval/` (text, context=BM25+graph index, features, run_baselines, run_synth_check),
  `src/eval/loc_metrics.py`, `src/groundtruth/map_patch.py`, `src/graphbuild/build.py`.
- Agent scaffolds: `submissions/c1..c6b` (C6a is FROZEN = git tag `scaffold-v1-frozen`; never edit it).
  Skill scripts: `submissions/c6a/skills/repo-tools/scripts/{locate,show,tests,check}.py`.
- End-to-end results on Kaggle scorer hardware (same 30 tasks, 8 configs):
  `results/kaggle/<run>/results/<run>/{task_results.jsonl, traces/trace_<id>.json, logs/<id>.log, patches/, test_outputs/}`
  for run in c1_n30 c2_n30 c3_n30 c4_n30 c5a_n30 c5b_n30 c6a_n30 c6b_n30. Triage reports `reports/triage_*.md`.
  Traces are ATIF JSON: steps with source system/user/agent, agent steps have `tool_calls[{function_name, arguments}]`
  and `observation`. Logs are rich-formatted text (strip ANSI with `re.sub(r'\x1b\[[0-9;]*m','',s)`).
- SFT tooling: `src/sft/{format.py, build_dataset.py, capture_proxy.py, make_smoke_adapter.py}`, `reports/e0_sft_format.md`.
- Eval tooling: `src/eval/{triage.py, scoreboard.py, run_eval.py, verify_gold.py, harness_patches.py}`.
- Python envs: `.venv/bin/python` (3.13: numpy, lightgbm, unidiff, matplotlib, pymupdf), `.venv-harness/bin/python`
  (3.12: torch 2.10, vllm, transformers 5.13, safetensors), `.venv-eval/bin/python` (3.13: harness, no torch).
  Model files: `external/models/gemma-4-31b-it-qat-w4a16-ct/` (config.json, chat_template.jinja, model.safetensors 23 GB).

## Established findings
1. pass@1 ≈ 0.29–0.33 on the 30-task pilot; 8 runs jointly solve 14/30 (pass@8 = 0.467): 4 tasks solved in all 8 runs,
   10 only sometimes. Biggest failure bucket = "right file, wrong fix"; then timeouts; "wrong location" only 2–5/30.
2. Localization (LORO, 117 tasks): BM25 MRR 0.398 ≈ LambdaMART ranker 0.397; graph smoothing doesn't help;
   embedding pseudo-query 0.112. Learned ranker is data-limited (3 repos).
3. Fixed failure modes: backtick-broken skill calls, test-file edits that make hidden tests fail to apply,
   thinking-driven timeouts (r=0.72 thinking vs time), empty submissions at tight tool budgets.
4. Thinking off + 100 tool calls (C6a) = same accuracy as thinking on, 34% faster.
5. ADK compacts context >14,336 tokens; 35/46 passing trajectories exceed it → SFT must use captured per-call prompts.

## Hard constraints for every council member
- **Do not use the GPUs**, do not start/stop vLLM, do not push Kaggle kernels or submissions, do not kill processes you
  didn't start. Other users share this machine. CPU work is fine (≤16 cores).
- **Never modify** `submissions/c6a`, `data/` originals, or running jobs' outputs. Write new code under
  `src/analysis/<your_area>/` (or the path your charter names) and your report under `reports/council/`.
- Every claim must cite evidence (file path + number, or command you ran). Separate facts from hypotheses.
  Quantify uncertainty (n is small: 30 tasks ⇒ ±2.5 tasks is one standard error).
- Think like a senior researcher: state the question, hypotheses, method, result, decision implication.
  Prefer analyses that change a decision. No fluff.
- Final message: a concise summary (≤300 words) of findings + top recommendations with expected impact, and the path of your report.
