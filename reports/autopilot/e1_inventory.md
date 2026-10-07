# E1 data inventory (2026-10-07, read-only snapshot of results/px)

## 1. Where proxy-run data lives
- Worker `ops/slurm/ap_worker.sbatch` writes each queue item to `results/px/<run>/<shard>/` (run = `px_<cand>_s<seed>`, shard = `ops/queue/shards/proxy/s0..s7.txt`, 152 tasks / 16 repos).
- Per shard: `task_results.jsonl` (resolved, patch size, error, tool_calls), `patches/`, `traces/trace_<iid>.json` (ATIF-v1.7), `logs/`, `test_outputs/`, `summary.json`. `ops/queue/px_report.py` reads the same files.
- Trace content: system prompt, harness user prompt, agent steps holding `tool_calls[{function_name, arguments(dict), extra.author}]` plus `observation`, per-call `usage`, and harness `continuation_nudge` system steps. Tool calls from the `code_analyzer` sub-agent are **interleaved in the same step list** (they can only be told apart by `extra.author`). The analyzer's final answer is an agent `message`.
- Excluded: `results/px_quarantine/` (D18 conftest leak, cn17).

## 2. Passing trajectories (all shards present, partial runs included)
| run | shards | attempted | pass | unique tasks |
|---|---|---|---|---|
| px_c8_s1 | s0-s6 | 119 | 38 | 38 |
| px_c9a_s1 | s0-s5 | 114 | 41 | 41 |
| px_c9e_s1 | s0-s5 | 103 | 41 | 41 |
| px_c9ae_s1 | s0-s7 | 128 | 53 | 53 |
| **total** | | 464 (134 distinct tasks) | **173** | **66 unique** |

Passing trajectories per repo (c8/c9a/c9ae/c9e; unique tasks): tenacity 8/10/11/7 (12), marshmallow 8/7/8/7 (9), jinja 4/4/6/2 (9), werkzeug 2/4/3/4 (6), typer 3/2/4/2 (4), click 2/1/4/2 (4), fiddle 2/1/3/3 (4), sqlmodel 2/2/2/2 (3), attrs 2/2/2/3 (3), etils 1/2/3/1 (3), tqdm 2/2/3/3 (3), pyglove 1/1/2/2 (2), ml_collections 0/1/0/2 (2), flask 0/1/1/1 (1), sqlparse 1/1/1/0 (1).
**15/16 repos have ≥1 pass.** requests-oauthlib (1 task) has not been attempted yet. The data is skewed: tenacity plus marshmallow give 66/173 trajectories, and 6 tasks pass in all 4 runs.

## 3. Trainer input and converter gap
- `src/sft/train_lora.py` expects JSONL rows `{run, instance_id, segment, input_ids, loss_mask}` that are already tokenized. The repo is taken from the `instance_id` prefix. `--holdout-repo` is documented as `fastapi|rich|requests|httpx`, but it is a free string match. For this LORO design it needs a multi-repo/org holdout (or a pre-split data file).
- `src/sft/build_dataset.py` builds those rows from **`capture.jsonl`** (exact per-call request/response written by `src/sft/capture_proxy.py`). It splits a task at compaction boundaries and maps calls to tasks by prompt-prefix matching (D5 says this needs explicit ids). Proxy runs do **not** go through the capture proxy: the worker points `--api-base` straight at vLLM. The only capture is `results/capture.jsonl` (16 calls, old C6a scaffold).
- `src/sft/format.py` has `trace_to_messages` (ATIF -> OpenAI messages) and `render`, but it was built for C6a: one session, `tools_c6a.json`, `enable_thinking=False`.
Gaps for C8/C9 trajectories:
1. **Thinking is not captured.** C8/C9 serve with thinking on (`configs/sampling.yaml`: budget 4096, analyzer 2048, `include_thoughts: false`), and the traces contain 0 thought/reasoning text. Training on tool calls alone would teach thinking-off behaviour to a model that is served with thinking on.
2. **Sub-agent sessions are mixed together.** `trace_to_messages` would splice analyzer calls into the root conversation. The analyzer session needs its own system prompt (`prompts/analyzer.md`) and tool schema, and the root sees only an AgentTool result. Every kept trajectory uses the analyzer (median 6.5 analyzer calls).
3. **Compaction is not visible** in ATIF, so we cannot reconstruct the exact per-call prompts. format.py's single-sequence render is only approximately right.
4. **No tools schema exists for the C9ae scaffold.** Only `tools_c6a.json` is on disk, so the exact template render cannot be done.
=> Recommended fix (no converter exists): run the next proxy seeds through `capture_proxy` (one proxy per worker slot, in front of each vLLM port). It records `reasoning_content`, the exact messages and tools, and the session for root vs analyzer. Add `instance_id` to the capture path/header, then extend `build_dataset.py` to emit the analyzer sessions as separate sequences. The 173 existing traces can only give approximate SFT without thinking (fallback / ablation).

## 4. D5 filters (reports/council/DECISIONS.md) and survival
D5 keeps a trajectory only if it is resolved, has a clean patch (no scratch/test/config files), has no test edit in the trajectory, has no repetition loop, and calls submit explicitly. Malformed tool-call turns are masked, not dropped. Max 2 trajectories per task.
Applied here (my proxies for D5: test/config path regex on patch + edit_file/write_file targets; loop = ≥4 identical consecutive calls):
- 173 passing -> 13 dropped by the hard filters (dirty patch 3, test edit 10, no submit 1, with overlap) -> 160.
- A repetition loop appears in 53/173 passing traces (mostly repeated identical `edit_file` calls, i.e. malformed edits that the model retried; also `submit_patch` x4+ and analyzer `run_command`).
- **Strict** (drop loops) + cap 2: **84 trajectories / 54 tasks**, ~1.4M tokens (root ~9.3k + analyzer ~3.8k median).
- **Lenient** (mask loop turns per D5's "mask, don't drop") + cap 2: **111 trajectories / 64 tasks**, ~2.8M tokens. Largest single prompt is 28k, which fits `--max-tokens 32768`.
Both clear D10's ">=30 clean trajectories" gate. Once captures exist, expect about the same counts (pass rate ~0.33-0.41 per run).

## 5. Proposed LORO design (4 folds by org/repo group, no task in both train and held-out)
| fold (held out) | repos | proxy tasks | held traj strict/lenient | train strict/lenient | train tokens (lenient) |
|---|---|---|---|---|---|
| F1 pallets | click, flask, jinja, werkzeug | 43 | 20 / 28 | 64 / 83 | ~2.0M |
| F2 google | pyglove, fiddle, ml_collections, etils | 44 | 10 / 18 | 74 / 93 | ~2.2M |
| F3 tenacity+fastapi | tenacity, typer, sqlmodel, sqlparse | 36 | 32 / 37 | 52 / 74 | ~2.0M |
| F4 rest | marshmallow, attrs, tqdm, requests-oauthlib | 29 | 22 / 28 | 62 / 83 | ~2.1M |
- Grouping by org approximates "unseen repo" better than single-repo folds, since sibling repos share style. It also keeps each held-out set at ≥29 tasks, so a pass-rate delta of about 0.1 can be seen with 2 seeds. If compute is short, run F1+F2 only (two most different held-out groups, 87 tasks).
- Metric: proxy pass rate of base C9ae vs C9ae+fold-adapter on the held-out tasks only, paired by (task, seed), with ≥2 seeds via `ops/queue` (vLLM `--enable-lora`). Also log the held-out NLL that `train_lora.py` already reports.
- Training (D10 rates: A100 ~6-9 h for 12M token-epochs, i.e. ~0.5-0.75 h per M token-epochs): per fold ~2M tokens x 2 epochs ≈ **2-3 h on 1 A100-80G** (int4 base, r=16, grad-accum 8). 4 folds + final all-data adapter ≈ **10-15 A100-h**, or ~1 day on 1 GPU / half a day on 2 GPUs (one fold per GPU). Run `--preflight --seq-len 32768` first.
- Eval cost: 4 folds x ~38 tasks x 2 seeds x 2 arms ≈ 600 task-runs ≈ 1.3x one full proxy sweep of all four candidates done so far.
- Cheapest first step: capture-enabled C9ae seeds s2/s3 (also the next release-evidence runs), then F1/F2 strict.
