# Harness knobs audit (2026-10-07)
Source: `.venv-eval/lib/python3.13/site-packages/` (`swegemma` is identical in `.venv-harness`). Paths below are relative to it.
Schema = `adk_submission/schema.py`; every model is `extra="forbid"`, so **any unknown key is a compile error**.

## Q1. Per-agent limits: none exist
- `SandboxedLlmAgentConfig` (schema.py:257-299) accepts only: name, description, agent_class, model, adapter, instruction,
  output_key, include_contents, disallow_transfer_to_parent/peers, tools, skills, sub_agents, generate_content_config,
  and the *_callbacks lists. There is **no max_tool_calls / max_turns / max_steps / timeout / token budget key**.
- `AgentToolRef` (schema.py:84-101) = `config_path` + `skip_summarization` only. ADK's `include_plugins` is not exposed.
- The only iteration cap in the schema is `LoopAgent.max_iterations` (schema.py:350-361; cap 500, builders/workflows.py:124-130).
  It counts sub-agent passes, not tool calls inside an LlmAgent, so it cannot cap the analyzer.
- Callbacks cannot help either. swegemma calls `compile_submission` without a `callback_registry` (harness/agent_runner.py:334-345).
  `resolve_callback_fields` then returns `{}` (resolvers/callbacks.py:84-85), so listed callback names are **silently ignored**.
- Sub-agent runtime: `AgentTool.run_async` builds a fresh `Runner(agent=...)` with a new InMemorySessionService and inherited plugins
  (google/adk/tools/agent_tool.py:236-249). It runs with no RunConfig (agent_tool.py:264-267), so the default
  `max_llm_calls=500` applies (google/adk/agents/run_config.py:317). The root's `RunConfig(max_llm_calls=remaining)`
  (agent_runner.py:516) does not reach the child.
- The tool budget is shared. All tools are built from one `SwegemmaContext` (tools/__init__.py:37-45). `budget_gated` → `check_budget`
  increments `tool_calls_used` (context.py:467-549), so analyzer calls drain the root's 100 calls.
  When the budget is exhausted, every tool returns `BudgetExceeded` JSON (context.py:~470-480). The root loop only checks
  the budget after `runner.run_async` returns (agent_runner.py:646-660).
- Root budgets are harness-side only (EvalConfig: `max_tool_calls`, `max_turns`, `max_time_minutes`, `timeout_seconds`, config.py:102-117).
  The scorer defaults we mirror are 100 calls / 60 min / 300 s / turns None → 500 LLM calls (src/eval/run_eval.py:30, agent_runner.py:429-431).
  None of these can be set from a submission.
- `submit_patch` is `@budget_gated(count_tool_call=False)` (tools/execution.py:76), so repeats do not use the call budget. It can be
  called many times, and the last diff wins (execution.py:80-82, 97-99). It does **not** end the episode by itself.
  The loop breaks only when (a) a text-only final model event arrives after `patch_submitted` (agent_runner.py:566-579), or
  (b) `run_async` returns while `patch_submitted` is set (agent_runner.py:635-637). Repeated submits therefore cost only turns/time.
  Unsubmitted working-tree diffs are captured as a fallback (agent_runner.py:758-776).

## Q2. Compaction for sub-agents: not configurable
- Compaction is an `App` kwarg that the harness sets (`EvalConfig.events_compaction_config`, config.py:117 → agent_runner.py:410-411).
  It is not in the submission schema.
- The AgentTool child `Runner` is built with `agent=`, not `app=`, and gets no compaction or context-cache config (agent_tool.py:241-249).
  D16 is confirmed: analyzer sessions are never compacted. `include_contents: none` does not help either. In a fresh child session the
  "current turn" starts at the request, so the analyzer still sees its whole history (google/adk/flows/llm_flows/contents.py:542-567).

## Q3. Schema knobs that C8/C10 do not use
| knob | where | expected effect |
|---|---|---|
| `frequency_penalty` / `presence_penalty` | schema.py:209-210; forwarded by LiteLlm (google/adk/models/lite_llm.py:1955-1961) | Token-level anti-repetition. Might weaken verbatim repeated calls, but can corrupt code/JSON args. Low value. |
| `stop_sequences` | schema.py:208 → `stop` | Hard-stops generation on a string. Not a call cap; risky with tool-call syntax. |
| `seed` | schema.py:212; bridged in resolvers/generation.py:321 | Deterministic sampling, so proxy A/B runs are less noisy. Neutral on score. |
| `thinking_config.thinking_level` | schema.py:171; generation.py:341-342 | Sets `reasoning_effort` when thinking is on. |
| `skills:` (SKILL.md + scripts) | schema.py:288; resolvers/tools.py:129+ | Scripts run in the sandbox; the toolset is not budget-gated (reports/optionAB.md). Moving the analyzer's grep/locate into a skill script gives a **bounded, deterministic** localizer. Best structural alternative. |
| `get_status` on analyzer | tools/execution.py:106-130 (not counted) | Lets the analyzer see the shared remaining-call budget. Low-budget warning appears only at ≤10 remaining (tools/base.py:47-69). |
| `output_key` | schema.py:283 | Stores analyzer output in state; no clear gain with `skip_summarization`. |
| `disallow_transfer_*`, `sub_agents` | schema.py:285-292 | Transfer-based delegation instead of AgentTool. It would share the root session and **get compaction**, but adds transfer-loop risk. |
| `Sequential/Loop/ParallelAgent` | schema.py:326-361 | Fixed pipelines, e.g. a mandatory localize→fix order. LoopAgent caps passes, not calls. |
| Tool allowlist | `tools:` list (already used) | Removing `run_command` from the analyzer (graph tools only) reduces flailing, but is not a hard cap. |

**Side finding:** `include_thoughts: false` forces `enable_thinking=False` (generation.py:290-301) and drops `thinking_token_budget`
(generation.py:329-337). Our `thinking_budget` values (4096 root / 2048 analyzer) are therefore dead config, and thinking is OFF for both agents.
This is consistent with the C6a wire captures (reports/e0_sft_format.md:3).

## Q4. Validation a new knob must pass
- Pydantic `extra="forbid"` at every level: an unknown key fails compile (schema.py:54,95,135,167,202,247).
- Generation (config.py:59-67): `max_output_tokens` 1..32768, `thinking_budget` 0..32768, `allowed_fields=None` (all schema fields allowed).
  Numerics must be finite and not bool (schema.py:145-152; limits.py:355-370). Defaults are merged in: `max_output_tokens` 16384 and
  `thinking_budget` 4096 when unset (limits.py:400-406).
- Structure (config.py:44-58): allowed extensions are .yaml/.yml/.md/.txt/.py/.json/.safetensors. Limits: ≤3 GiB, no symlinks,
  ≤10k files, ≤500 agents, depth ≤50, loop ≤500, ≤1M chars per instruction. No path traversal in config_path/skills
  (schema.py:61-76,306-323). Unambiguous root agent.yaml (adk_submission/discovery.py:60-120).
- Every model name must resolve in the ModelRegistry. scripts/package_submission.sh runs `src.eval.validate_submission`
  (organizer compile_submission with stub tools) before zipping.

## Bottom line
No YAML key can hard-cap the analyzer, and callbacks are dropped. Prompt-level caps (C9e) are the only in-config lever.
Structural options: (1) replace the AgentTool analyzer with a skill script (bounded, uncounted calls); (2) move the analyzer to
`sub_agents` transfer so it inherits root compaction; (3) drop or limit analyzer tools.
