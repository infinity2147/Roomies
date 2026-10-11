# What Claude Code and SOTA SWE scaffolds do, and what transfers to our Gemma-4-31B ADK setting (2026-10-11)

**Question.** How are Claude Code and the leading SWE-bench scaffolds built, and which of their ideas can we use under our constraints? The constraints:
- one fixed Gemma-4-31B int4 model;
- decode-bound (about 36 tok/s at batch 1, 78–85 % of wall time);
- about 120 serial tasks in 12 h (budget 5.93 L4-min/task, or about 4.1 if the scorer is 1.45× slower, per D28);
- a declarative ADK YAML with no callbacks and no custom tools.

The two target problems are (a) malformed tool calls and loops, and (b) wrong or incomplete fixes, which are 54 % of failures.

Inputs:
- `reports/harness_capabilities_20261010.md` (=HC)
- `reports/time_budget_20261011.md` (=TB)
- `reports/failure_analysis_20261010.md` (=FA)
- new trace and template checks done for this report (§1)
- web sources listed in §7

Throughout, "s/task" means L4 seconds per task. The cost model is 1 s ≈ 36 decoded tokens:
- a non-thinking root call ≈ 2.4 s;
- a non-thinking analyzer call ≈ 1.5 s;
- a thinking root call ≈ 6.5 s, of which about 160 reasoning tokens ≈ 4.4 s.

---

## 0. TL;DR

1. **The malformed-call root cause is structural.** The Gemma-4 chat template renders every tool schema and every past tool call with `| dictsort`, i.e. alphabetical key order (`external/models/gemma-4-31b-it-qat-w4a16-ct/chat_template.jinja:4,126,249`). So the model always emits the long code string *before* a short key that follows it alphabetically:
   - `edit_file`: `filepath, new_string, old_string`. The schema declares `filepath, old_string, new_string`, yet all 242 complete `edit_file` calls in three Kaggle L4 captures put `new_string` first and none uses the schema order.
   - `run_skill_script`: `args, file_path, skill_name`.

   When the model closes the long string badly (escaped `\n` plus a backtick), every key after it is swallowed.
   - **This is exactly why C20 apply-edit failed (−0.128).** 6 459 C20 calls were rejected with "Argument 'skill_name' is required", because the SEARCH/REPLACE payload sat in `args`, which sorts first.
   - `run_command` has a single key and was rejected **1 time in 6 747** calls.
   - Python heredocs inside `run_command` hit a SyntaxError in only about 1 % of 907–1 144 calls per seed.
   - **The fix is to make every code-bearing string the only argument of its call.** That means edits go through `run_command` heredocs to a helper that a no-argument skill call installs in `/tmp`.
2. **Claude Code's real lessons for us** are mostly about the shape of its tools, not its prompt wording:
   - exact-match `old_string` with uniqueness and read-before-edit checks;
   - absolute paths;
   - actionable errors;
   - hooks as deterministic rule engines (PreToolUse/PostToolUse/Stop);
   - subagents with a fresh context that return short summaries;
   - "give the agent a check it can run".

   We have no hooks or callbacks, but we can **emulate** them. Checks go *inside* the helper that the model must call anyway (a PostToolUse equivalent at zero extra LLM calls), and stages go into `SequentialAgent` (a Stop-hook equivalent).
3. **For correctness**, the lever with the best measured payoff in the literature is Agentless-style **sample several cheap repairs, then select by execution**:
   - reproduction-test filtering added +15/300 on SWE-bench Lite over voting alone;
   - Anthropic, OpenHands, Trae and CodeMonkeys all use parallel attempts plus selection.

   Under decode-bound batch-1 serving, K parallel *edit-only* branches cost about 1.1–1.4× one branch (decode is bandwidth-bound; `reports/council/strategy_20261007.md`). This is the cheapest test-time scaling available to us. Full parallel *solvers* (C14p) are not.
4. **Ruled out:** hooks, callbacks, custom tools, renaming or reordering tool arguments, a second model or trained critic, MCTS, per-turn thinking toggles, early-exit loops, cross-task memory and parallel tool *execution* (§5).

---

## 1. New evidence from our own data (supports §0.1)

| check | result | source |
|---|---|---|
| Key order of emitted `edit_file` args (Kaggle L4 captures) | Among calls carrying both keys, `new_string` comes before `old_string` (alphabetical) in 55/55 (c9ae), 108/108 (c11n) and 79/79 (c15t512); schema order 0. In c9ae only 55 of 301 edit calls carry both keys at all. | `results/kaggle/{c9ae,c11n,c15t512}-t30s/.../capture.jsonl` |
| Chat template | `format_parameters(...)`: `for key, value in properties \| dictsort`; tool-call history is also re-rendered with `function['arguments'] \| dictsort` | `chat_template.jinja:4,126,249` |
| Per-tool rejection rate, C9e s1 | edit_file **1 571/2 014 (78 %)**; run_command 1/6 747; read_file 0/2 571; write_file 0/10 | traces `results/px/px_c9e_s1` |
| Same, thinking run C15n512 s1 | edit_file 103/585 (17.6 %); write_file 2/42; run_command 1/4 495 | `results/px/px_c15n512_s1` |
| C20 apply-edit (s1–s3), all `run_skill_script` calls | 6 459 "skill_name is required", 11 "file_path is required", 561 "identical resend" guard hits; only about 150–220 "OK: applied" in s1 (of 3 739 calls; the count depends on the heuristic) | `results/px/px_c20ae_s*` |
| Shape of C20 calls (s1–s3) | 4 431 had **only** `args` (as a list); 1 508 only `args` (as a string); 480 only `args` (as a dict); 1 669 complete | same |
| Python heredocs via `run_command` (`<<` plus `python`) | C9e: 907 calls, 8 SyntaxError, 1 "line continuation" (literal `\n`); C9ae: 1 144 calls, 7 and 2; C15n512: 984 calls, 9 and 5 | traces |
| Multiple tool calls in one turn | 0 of 8 600 L4 turns (c9ae, c11n, c15t512) | captures |

**Interpretation.**
- Gemma-4 serialises arguments in its own format (`call:NAME{key:<|"|>…<|"|>,…}`). The vLLM parser docs and a Hugging Face thread describe malformed tool calls under long context and reasoning load, and repeat loops on the broken output.
- When the string is the *only* or *last* argument, a bad terminator costs nothing: there is no key left to swallow.
- The C9a fallback ("after one failure, use a heredoc") failed for two reasons, cut the malformed share from 84 % only to 71 %, and left the pass rate unchanged:
  - it left `edit_file` available;
  - after a rejection, the model repeats the identical malformed call 97 % of the time.
- C20 removed `edit_file` but moved the payload into `args`, which sorts *first*.
- Thinking fixes most of it (78 % → 18 % malformed), but at about 160 tokens on every call (TB §1). **Part of what thinking buys is format correctness, which a structural fix delivers for free.**

---

## 2. Claude Code's architecture (Q1)

| component | how Claude Code does it | why it matters | source |
|---|---|---|---|
| Agent loop | One model in a single-threaded loop: "gather context → take action → verify results", repeated until the model stops. No fixed pipeline: the model chooses each step. | Minimal scaffold, maximal model control (also Anthropic's SWE-bench scaffold: "keep the scaffolding minimal"). | [How Claude Code works]; [SWE-bench Sonnet] |
| Core tools | Bash, Read, Edit, Write, Glob/Grep, LSP, Agent (subagent), task list (TodoWrite, now TaskCreate/TaskUpdate), WebFetch/WebSearch, Skill. MCP tools are *deferred* (only names in context until searched). | A small, orthogonal tool set; "if a human engineer can't definitively say which tool should be used… an agent can't be expected to do better". | [Tools reference]; [Context engineering] |
| Edit semantics | Exact string replacement `old_string` → `new_string`, "doesn't use regex or fuzzy matching".<br>Checks: **read-before-edit** (a partial view doesn't count); **match** ("a single character of whitespace… is enough to miss"); **uniqueness** (exactly one match, else add context or `replace_all`).<br>Write overwrites a whole file and requires a prior read of existing files. MultiEdit (several edits to one file, atomic) existed in 2025 versions. | Poka-yoke: the edit fails loudly instead of corrupting silently. Our harness does the opposite (4 fuzzy tiers, re-indents `new_string`, HC §3). | [Tools reference §Edit] |
| Edit tool history | SWE-bench scaffold `str_replace_editor` with `view/create/str_replace/insert/undo_edit`; "`old_str` should match EXACTLY one or more consecutive lines"; absolute paths only, because "the model used this method flawlessly" after the change. | String replacement was the most reliable edit format for Claude. Absolute paths remove a whole error class. | [SWE-bench Sonnet]; [Building effective agents] |
| Error messages | Specific and actionable: not found / not unique / stale file → re-read. Tool docs: "steer agents with helpful instructions" when truncating; never opaque codes. | The retry is informed, so the model doesn't repeat the same call. | [Writing tools for agents] |
| Planning | TodoWrite (task list) as structured note-taking; plan mode for explore → plan → implement → commit; "if you could describe the diff in one sentence, skip the plan". Claude 4's SWE-bench scaffold **dropped** the planning tool used by Claude 3.7. | Planning helps multi-file or uncertain tasks and costs tokens on small fixes. | [Best practices]; [Claude 4] |
| Subagents | Agent/Task tool. Each subagent has "its own context window with a custom system prompt, specific tool access", does not see the parent history, and returns only a summary (Anthropic: "often 1,000–2,000 tokens"). Built-in Explore is read-only and cheap. | Context isolation: exploration noise stays out of the main context. | [Sub-agents]; [Context engineering] |
| Hooks | `PreToolUse` (exit 2 blocks the call and stderr goes to the model; `updatedInput` rewrites the arguments), `PostToolUse` (exit 2 shows stderr to the model: linters and formatters after edits), `Stop`/`SubagentStop` (exit 2 forces the agent to continue: a deterministic "don't stop until the tests pass" gate), plus `PreCompact` and others. "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic." | A rule engine outside the model: rules that must hold every time never depend on compliance. | [Hooks]; [Best practices] |
| Context management | Just-in-time retrieval (grep/head/tail rather than whole files), tool-result clearing first, then auto-compaction (summary). Stops compacting if it thrashes. CLAUDE.md for persistent rules. | Performance degrades as context fills. | [Context engineering]; [How Claude Code works] |
| Prompt style | Short, high-signal instructions; "If Claude keeps skipping one instruction, add emphasis such as 'IMPORTANT' to that line alone"; "Bloated CLAUDE.md files cause Claude to ignore your actual instructions"; concise outputs, no narration. | Prompt length competes with attention. | [Best practices] |
| Parallel tool calls | Independent reads and greps are emitted in one assistant turn and executed together. | Fewer model turns. | [How Claude Code works] |
| Verification habit | "Give Claude a check it can run… the difference between a session you watch and one you walk away from"; show evidence (the command and its output) rather than claims; an **adversarial reviewer subagent** in a fresh context, told to "flag only gaps that affect correctness". | Self-grading is biased; a fresh context helps. | [Best practices] |
| Failed edits / loops | Uniqueness and staleness errors force a re-read; "after two failed corrections… clear and start fresh"; Sonnet 3.5 (new) "self-corrects more often… tries several solutions rather than repeating one mistake". | Repetition after a failure is the known failure mode. | [Best practices]; [SWE-bench Sonnet] |
| Thinking | Extended thinking or the "think" tool for sequential, policy-heavy tool chains: τ-bench airline 0.370 → 0.570; SWE-bench only +1.6 %. Anthropic's reported SWE-bench Verified numbers for Claude 4 used **no extended thinking**. Test-time scaling there = parallel attempts, discarding patches that break *visible* regression tests, plus a scoring model (Opus 4: 72.5 → 79.4 %). | Thinking is not the main SWE lever for strong models. Parallel attempts plus selection is. | [Think tool]; [Claude 4] |

---

## 3. What other SOTA scaffolds do that measurably helps (Q2)

| system | key mechanism | measured effect | source |
|---|---|---|---|
| **SWE-agent (ACI)** | Purpose-built agent-computer interface. The `edit` command runs a **linter and rejects edits that introduce syntax errors** (showing before and after). Windowed 100-line viewer, summarised search, last-5-observations context. | SWE-bench Lite, GPT-4T, full = 18.0 %:<br>edit without linting 15.0 (−3.0); no edit command 10.3;<br>search summarised 18.0 vs iterative 12.0;<br>viewer 100 lines 18.0 vs 30 lines 14.3 vs full file 12.7;<br>full history 15.0 vs last-5 18.0.<br>**After a single failed edit, the chance of eventually succeeding falls from 90.5 % to 57.2 %; cascading failed edits = 23.4 % of failures.** | [SWE-agent paper] |
| **Agentless** | Fixed pipeline: hierarchical localisation (files → skeleton classes/functions → lines); repair = **search/replace diffs, 4 locations × 10 samples** (1 greedy plus T=0.8); generated **reproduction tests** plus **regression tests** filter; majority vote over normalised (AST) patches. | Lite 32.0 % at $0.70.<br>Selection ablation: voting only 25.67 % → +regression 27.0 → **+reproduction 32.0** (+15 tasks).<br>Upper bound over all samples 42 %.<br>Skeleton beats full file for localisation (58.3 vs 53.7 % at 1/7 of the cost).<br>Only 94/300 generated repro tests pass on the gold patch. | [Agentless] |
| **Aider edit formats** | `whole` (rewrite the file), `diff` (SEARCH/REPLACE), `udiff`, `diff-fenced` (for Gemini, which "often fail[s] to conform to the fencing"). **Architect/Editor**: a reasoning model plans in plain text, an editor model emits the formatted edits. **Code in JSON** (tool calls) gives worse code and more Syntax/IndentationErrors than markdown, for all 4 models tested. | Architect/editor beats solo for every pairing: Sonnet+Sonnet 80.5 vs 77.4; GPT-4o 75.2 vs 71.4; o1-mini+DeepSeek 71.4 vs 61.1; 4o-mini 60.2 vs 55.6. | [Aider formats]; [Aider architect]; [Aider JSON] |
| Format research | Diff-XYZ: search/replace is best for *larger* models; "smaller open models benefit little from any formatting choice". "Let Me Speak Freely": strict formats degrade reasoning; key order in structured output matters. | Separate *reasoning* from *formatting*. | [Diff-XYZ]; [Speak Freely] |
| **mini-SWE-agent** | About 100 lines; **bash only, no tool-calling interface** (v1 parsed actions from text); linear history; each action is an independent `subprocess.run`. >74 % SWE-bench Verified (strong models); it is the official "bash-only" leaderboard harness. | For strong models, custom tools are no longer needed. For weak ones the ACI still matters (SWE-agent ablation). | [mini-SWE-agent]; [SWE-bench bash-only] |
| **OpenHands (CodeAct)** | Actions as code (bash/IPython) plus `str_replace_editor`; event stream; condenser. Inference-time scaling: 5 rollouts plus a **trained critic** (Qwen-32B), 60.6 → 66.4 %. "A dedicated critic outperformed prompt-based reranking." | Parallel plus critic is about +6 pp for strong models. | [OpenHands critic]; [OpenHands paper] |
| **AutoCodeRover** | AST-aware search APIs (`search_class`, `search_method_in_class`, …) plus spectrum-based fault localisation from tests. | SBFL raised Lite from 16 to 20 % (v1); 46.2 % Verified later. | [AutoCodeRover] |
| **Moatless / SWE-Search** | Lean, cost-efficient agent ($0.30/instance, 38.3 % Lite with Sonnet). MCTS plus an LLM value function adds +23 % relative but costs about 5× the compute. | MCTS is too expensive for us. | [SWE-Search] |
| **Trae Agent** | Generate → prune (regression tests, dedup) → LLM selector agent; selector accuracy "peaks when the sampling space is 5 or 6". 75.2 % Verified. | Selection works best with small K. | [Trae] |
| **CodeMonkeys** | Serial (iterate edits plus a self-written test) × parallel trajectories; selection = test voting plus a selection trajectory. 57.4 % with Sonnet 3.5. | The shared up-front context is reused across samples (like our prefix cache). | [CodeMonkeys] |
| **R2E-Gym / DeepSWE / SWE-Gym** (open 32B) | Hybrid verifier (execution-based plus execution-free) for best-of-N. R2E-Gym 32B: pass@1 34.4 → 51 % with hybrid best-of-26; each verifier alone plateaus at 42–43 %. DeepSWE 32B: 42.2 pass@1 → 59 % with test-time scaling. | Test-time scaling is the main lever for open ~30B models. Execution-only verification plateaus because tests have low distinguishability. | [R2E-Gym]; [DeepSWE] |
| **Kimi-Dev** | Agentless training as a "skill prior" (localisation, editing, self-verification), then light agentic SFT. | 60.4 % (workflow); 48.6 % as an agent after 5k-trajectory SFT. | [Kimi-Dev] |
| **Overthinking** (Cuadron et al.) | Analysis paralysis, rogue actions and premature disengagement. Picking the lower-overthinking candidate gives about +30 % performance and −43 % cost. | Reasoning models over-think in agent loops, as our TB shows: the post-fix tail is 27–38 % of solved trajectories. | [Overthinking] |

**Common pattern across the 2025–26 leaders.** A simple agent loop or fixed pipeline, a mistake-proof edit primitive, and execution feedback. Then **parallel candidates with execution-based filtering and a selector**. Small or open models gain most from the edit primitive (SWE-agent's −3 to −7.7 pp ablations) and from best-of-N with a verifier (+15–17 pp for R2E-Gym and DeepSWE at large N; Agentless +5 pp at fixed N from the repro filter).

---

## 4. Mapping onto our legal mechanisms (Q3)

Legal levers: prompts, `tools:` lists per agent, `sub_agents` (transfer) / `agent_tool`, `SequentialAgent` / `ParallelAgent` / `LoopAgent` (fixed iteration count), per-agent `generate_content_config` (temperature, thinking on/off and budget, `max_output_tokens`, `stop_sequences`, penalties), `include_contents: none`, `output_key`, skills (scripts run in the task sandbox, 1 counted call each; `/tmp` persists within a task), `eval_config` (`max_time_minutes`, `max_tool_calls`, `timeout_seconds`), LoRA (slow decode).

Time costs are L4 estimates from the TB cost model. "+" means added time per task.

| # | idea (origin) | our mechanism | est. time cost | feasibility / notes |
|---|---|---|---|---|
| M1 | **Mistake-proof single-string edit primitive** (Claude Code Edit checks, SWE-agent lint-gated edit, Aider SEARCH/REPLACE, poka-yoke) | Remove `edit_file` (and `write_file` for code) from root `tools:`.<br>A **bootstrap skill called with no `args`** (keys `file_path`, `skill_name` are both short) copies `sr.py` and `tb.py` into `/tmp`.<br>Every edit is `run_command`: `python3 /tmp/sr.py <<'EDIT' … path, <<<<<<< SEARCH … ======= … >>>>>>> REPLACE … EDIT`.<br>`sr.py` does: exact match, then whitespace-tolerant match only if unique; tells the model when it fuzzed; unescapes literal `\n`; refuses on not-found or ambiguous with the closest lines plus line numbers; refuses edits that fail `py_compile`; prints the edited window (±5 lines) with numbers; and refuses an identical resend. | Bootstrap: +1 counted call (≈1.5–2.5 s + 1 s exec).<br>Per edit: about +25 tokens of heredoc framing (≈0.7 s) and the edit itself.<br>**Saves:** C9e rejected-call bucket 78 s/task (2.6 h/120) plus loop buckets; C15n512 about 13 s. | **Feasible now.** The key difference from C20 is that the payload lives in `run_command.command`, the **only** key. Verify first with the existing `src/analysis/edit_replay.py` (add a variant with `edit_file` removed and toolbox instructions), then px s1–s2. |
| M2 | PostToolUse hook (lint, format, run tests after every edit) | Build it **into `sr.py`**: after a successful edit, run `py_compile` on the file, then automatically run `/tmp/repro.py` if it exists (`timeout 30`, last 15 lines). Also list **same-name defs, sync/async twins, overrides and `__all__`/`__init__` exports** of the edited function (AST), so incomplete patches show up. | 0 extra LLM calls; +2–10 s tool time and ~100 prompt tokens (prefill, ≈0.05 s). | **Feasible.** A deterministic "rule engine" the model cannot skip, because it is part of the only edit path. |
| M3 | PreToolUse hook (block bad actions) | Inside `sr.py`: refuse edits to test, conftest or config files (HC §3 predicate) and edits outside `/workspace`. You cannot block other tools. | 0 | Partly feasible: only for actions that go through our helper. |
| M4 | Stop hook / "don't stop until the check passes" (Claude Code), end-of-task protocol (TB I2b/I5) | `SequentialAgent[solver, finalizer]`.<br>The solver has **no `submit_patch`** in its tools and ends with text.<br>The `finalizer` (thinking off, `include_contents: none`, tools `run_command` + `submit_patch`) runs `python3 /tmp/tb.py check` (revert test/config edits, delete scratch files, py_compile and import the changed modules, refuse an empty diff), calls `submit_patch` once, then replies with one line. | ≈3 non-thinking calls ≈ +8–12 s.<br>**Saves:** submit loops (thinking: 48–113 s/task) and part of the post-verification tail (13–52 s). | **Feasible.** If the time cap hits during the solver, the harness grades the working-tree diff (HC §1), so there is no empty-patch risk.<br>Risk: a nudge re-runs the Sequential (HC §1). Mitigate with `disallow_transfer_to_parent`. |
| M5 | Subagent context isolation (Claude Code Explore; summaries of 1–2k tokens) | The existing `code_analyzer` AgentTool (C9e). Keep it non-thinking, and have it call `tb.py locate` (one call: multi-identifier grep → enclosing defs → skeleton) instead of 20+ greps. | Analyzer today: 71 s/task and 38 calls. A batched locate could cut that by about 30–50 % (≈ −20–35 s). | Feasible. **Caveat:** an AgentTool child has its own 500-LLM-call limit and ignores prompt caps (TB §2d), so containment has to be structural (fewer, richer tools). |
| M6 | SWE-agent summarised search, 100-line window, skeletons (Agentless) | `tb.py find <ids…>`: grouped matches with enclosing function names, capped at about 40 lines. `tb.py show path::func`: the function plus ±10 lines, numbered. `tb.py skel path`: signatures only. | Fewer root calls. Each avoided call saves 2.4 s (non-thinking) or 6.5 s (thinking). | Feasible (`run_command` with one string arg, so safe). |
| M7 | Parallel tool calls (Claude Code) | Gemma emitted 0 multi-call turns in 8.6k L4 turns, and our tools run serially anyway. Equivalent: **compound commands** in one `run_command` (`grep …; sed -n …; python …`). | Saves a call per merged step. | Prompt-level; low risk. |
| M8 | Agentless sampling plus execution-based selection; Trae and CodeMonkeys | After localisation and repro (shared prefix, prefix-cached): `ParallelAgent[editor_1..K]` (K=3, T≈0.7, thinking off, tools = `run_command` only). Each branch writes its SEARCH/REPLACE blocks to `/tmp/cand_k.sr` with one heredoc, **without touching `/workspace`**, and replies "done".<br>Then **one** skill or `tb.py select` call: for each candidate, create a git worktree from the current tree, apply, py_compile, run repro (must FAIL on base and PASS on the candidate) and the nearest test file; keep regression-clean candidates; majority-vote on the AST-normalised diff; apply the winner to `/workspace` and print a scoreboard. | K parallel edit generations of ≈300–600 tokens each ≈ 10–20 s wall, at 1.1–1.4× one branch (bandwidth-bound decode), plus the selector at 20–40 s of tool time.<br>**≈ +35–60 s/task**, applied only once the first candidate is in place. | **Feasible.**<br>Conditional variant: a root prompt rule "invoke `alt_editors` (AgentTool wrapping the ParallelAgent) only if the repro still fails after the first fix" (HC §6A).<br>Selection is weak when the repro is wrong: FA found 89/132 failed patches with a green self-check. |
| M9 | Aider architect/editor; Anthropic "think" | **Tool-less thinking planner**, invoked once after localisation and repro: AgentTool `planner` with `tools: []`, thinking budget about 1–2k, `include_contents: default`. It returns a plain-text fix plan (sites, edge cases, exact strings to reuse). The root stays non-thinking and executes. | One thinking generation ≈ 1–2k tokens ≈ 30–55 s.<br>Compare: a thinking root adds about 306 s/task (TB); the C17 thinking analyzer with tools was 2.11× time. | **Feasible, hypothesis.** Format errors are solved by M1, so thinking would be spent only on reasoning. C22 (analyzer think budget 256, *with tools*) hurt, which says nothing about a tool-less, larger-budget planner. |
| M10 | Fresh-context adversarial reviewer (Claude Code best practices); OpenHands critic | AgentTool `reviewer`, `include_contents: none`. The root passes it the issue, `git diff` and repro output; it returns ≤5 correctness gaps ("missed site / async twin / export / message wording / example in the issue not covered") or "OK". Thinking optional. | 1 call ≈ 200–400 tokens ≈ 6–12 s (non-thinking), or ≈ 30 s (thinking).<br>A follow-up fix adds 2–4 calls. | Feasible. Risk of over-engineering: the docs warn reviewers "will usually report some" gaps. A *trained* critic is impossible (one model; a LoRA critic has slow decode). |
| M11 | Repro-first verification (Anthropic SWE prompt, Agentless repro tests, CodeMonkeys) | `tb.py ab /tmp/repro.py`: runs the repro on a `_swegemma_baseline` worktree and on `/workspace`, and prints `BASE: FAIL NOW: PASS`. Prompt: "encode every example and expected output in the issue as an `assert`; reuse message wording verbatim". | 1 call ≈ 3–6 s per use. | Feasible. Prompt-only variants were null (C9b/C14b); the deterministic A/B print is the new part. |
| M12 | Concise observations (SWE-agent last-5 observations) | Not needed: TB §2e shows observations cost 3–7 s/task thanks to the prefix cache. | — | Skip. |
| M13 | Forbid narration (Claude Code style) | Already ≤ 0.5 h/120 (TB §4). | — | Skip. |
| M14 | TodoWrite / NOTES.md | Write `/tmp/plan.md` via `run_command`. Costs decode tokens and gives no measured benefit on short tasks; Claude 4 dropped its planning tool. | +5–15 s | Not recommended. |
| M15 | Compaction control | The harness compacts on its own (root only). Use `include_contents: none` for stage agents so their contexts start clean. | — | Partial. |
| M16 | Overthinking / early stopping | `max_time_minutes` cap (TB I8: 8 min, −2.9 % of tasks); "submit early, re-submit" (last submit wins). | Tail control | Feasible, already analysed. |
| M17 | Distillation (Kimi-Dev, DeepSWE RL) | LoRA trained on our own resolved trajectories (C19). | Slow decode on L4; C19/C20-mix gave no gain | Feasible, but deprioritised by the evidence so far. |

**Ruled out here:**
- PreToolUse/PostToolUse/Stop **hooks and callbacks** (registry empty): emulate them with M2–M4.
- **Custom tools**, or changing `edit_file`'s arguments, names or order (they are dictsorted by the template).
- `updatedInput` rewriting of a malformed call; "never feed malformed turns back into history".
- A **second model** (true architect/editor, a trained critic or scoring model, an embedding retriever model).
- **MCTS / value-function search** at our budget.
- `LoopAgent` early exit.
- Per-turn thinking toggles (thinking can only be set per agent).
- **Parallel tool execution** (`tool_lock`; only decode overlaps).
- Checkpoint/rewind (use git instead).
- Cross-task memory or adaptivity.
- Agentless at full scale (40 samples, 40 repro tests).
- Raising `max_tool_calls` above 100 is documented but unverified on the scorer.

---

## 5. Ranked top-5 transferable ideas

### (a) Eliminating malformed tool calls and loops

| rank | idea | mechanism (§4) | expected effect | time Δ (L4 s/task) |
|---|---|---|---|---|
| 1 | **The code payload is the only argument**: remove `edit_file`; edits run through the `run_command` heredoc → `/tmp/sr.py` installed by an argument-less bootstrap skill | M1 | Edit rejections fall from 78 % to about 1–2 % (heredoc baseline). The malformed loop (FA: ≈ +8 solves/304 within-task, ≈ +2.7 pp) and most of the 27 % rejected-call time should disappear. It also removes the reason to pay for thinking on format. | C9e: **−40 to −78**; C15n512: about −13; cost +3–5 |
| 2 | **Checks inside the edit helper** (PostToolUse equivalent): py_compile refuses a bad edit; identical-resend refusal; closest-lines hint with line numbers; numbered window after the edit (no re-read needed) | M1/M2 | Breaks the "repeat the same failed call" pattern (SWE-agent: recovery falls from 90.5 % to 57.2 % after one failed edit). Removes a verification read per edit. | −5 to −15 |
| 3 | **Finalizer stage** (Stop-hook equivalent): the solver lacks `submit_patch`; `Sequential[solver, finalizer]` runs check, submits once and ends with text | M4 | Removes submit loops and post-submit wandering (C15t512: 113 s/task measured; FA: 26 C9e failures in a submit loop). Deterministic patch hygiene (test/config revert, scratch removal, non-empty diff). | Thinking: **−50 to −110**; non-thinking: about −5 to −10; cost +8–12 |
| 4 | **Batched, structure-aware search** (`tb.py find/show/skel`) for root and analyzer, plus "compound commands" | M5/M6/M7 | Fewer calls, so fewer chances to loop. Also attacks the analyzer's 20-call overrun and identical-`sed` loops that lead to context overflow (17 overflows, 15 of them empty patches). | −20 to −40 (analyzer), more with thinking roots |
| 5 | **Safety nets**: `max_time_minutes` (8 for thinking, 15 for C9e), "submit early, re-submit", "on BudgetExceeded reply at once" | M16 | Bounds the tails that remain. | −10 to −100 (tail-dependent) |

### (b) Improving fix correctness

| rank | idea | mechanism | expected effect | time Δ |
|---|---|---|---|---|
| 1 | **Cheap parallel repair sampling plus execution-based selection** (Agentless/Trae/CodeMonkeys), K=3 edit-only branches on the shared prefix, followed by one deterministic select call | M8 | Literature: repro-filtered selection +5 pp on Lite at fixed N (Agentless); open 32B models gain +15–17 pp with large N and a verifier.<br>For us, plausibly **+2 to +5 pp**, coming mostly from coverage of the 104 near-misses (variants that touch the missed site). | +35–60 (unconditional); about +15–25 if invoked only when the repro still fails |
| 2 | **Repro A/B tool plus issue-examples-as-asserts** | M11 | Targets "ignored failing evidence" (23/37 misinterpreted) and invalid repros (11/49), and is the oracle that #1 needs. | +5–10 |
| 3 | **Sibling, twin and export listing printed on every edit** | M2 | Targets incomplete patches (18 %: async twin, sibling implementation, `__all__`). The model can't miss it, because it arrives in the edit result. | +1–3 |
| 4 | **Tool-less thinking planner, invoked once** (architect/editor split) | M9 | Brings the reasoning that made thinking +0.11 into a single call instead of a 160-token tax on about 60 calls. Hypothesis; must be measured. | +30–55 (vs +227 for a thinking root) |
| 5 | **Fresh-context reviewer of the diff against the issue**, flagging correctness gaps only | M10 | Targets false confidence: 52 of the 104 near-misses had their last pytest passing. | +6–30 |

**Budget check.**
- Start from C9e (4.92 min).
- (a)#1 + #3 + #4 give about 3.5 min (TB-style estimate).
- Adding (b)#1 conditional, #2, #3 and #4 gives about 4.6–5.0 L4-min/task. That fits 5.93, but not the 4.1 L4-min of the D28 slow-scorer scenario unless capped. The `max_time_minutes` cap is mandatory.

---

## 6. Recommended next steps (in line with the STATE.md "one problem at a time" program)

1. **Step 2 (edit reliability): build C23 = C9e + M1/M2.** No other changes.
   - **Offline gate first:** add an `edit_replay` variant to `src/analysis/edit_replay.py` (job 348014 is pending) that replays the captured edit requests with `edit_file` removed from `tools` and the toolbox paragraph in the system prompt. Score heredoc syntax validity plus `sr.py` apply success. Pass if ≥ 95 % well-formed.
   - Then px s1–s2 versus C9e. Primary metrics: badTC/task → ≈ 0 and min/task. Secondary: pass@1 not lower.
   - Implementation notes:
     - The bootstrap script copies itself with `shutil.copy(__file__, "/tmp/sr.py")`. Skill files are materialised in a temp dir that is deleted after the run (`google/adk/tools/skill_toolset.py:571-706`).
     - Use a heredoc delimiter unlikely to appear in code (`'SR_EOF'`).
     - In the prompt, name the exact command template once and nothing else.
     - Never put code in `run_skill_script` `args`.
2. **Step 1 add-on: C9e + M4 finalizer.** Validate it on thinking candidates first, where the gain is large.
3. **Step 3 (fix quality): M8 conditional plus M11 on top of C23.** Then M9 as a separate arm, compared against C17's +0.06 at 2.11×.
4. Do **not** spend more on prompt-only verification (C9b/C14b/C21 were null) or on per-agent thinking budgets with tools (C22 −0.048).

---

## 7. Sources

Anthropic / Claude Code:
- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [Tools reference (Edit/Write/Read/Bash behaviour)](https://code.claude.com/docs/en/tools-reference)
- [Hooks](https://code.claude.com/docs/en/hooks)
- [Sub-agents](https://code.claude.com/docs/en/sub-agents)
- [Best practices](https://code.claude.com/docs/en/best-practices)
- [Raising the bar on SWE-bench Verified (SWE-bench Sonnet)](https://www.anthropic.com/engineering/swe-bench-sonnet)
- [Building effective agents (ACI, poka-yoke, code-in-JSON escaping)](https://www.anthropic.com/engineering/building-effective-agents)
- [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [The "think" tool](https://www.anthropic.com/engineering/claude-think-tool)
- [Claude 4 announcement (SWE-bench methodology footnotes)](https://www.anthropic.com/news/claude-4)

Scaffolds and papers:
- [SWE-agent (arXiv 2405.15793, ACI ablations)](https://arxiv.org/html/2405.15793v3)
- [Agentless (arXiv 2407.01489)](https://arxiv.org/html/2407.01489)
- [Aider edit formats](https://aider.chat/docs/more/edit-formats.html)
- [Aider architect/editor](https://aider.chat/2024/09/26/architect.html)
- [Aider: LLMs are bad at returning code in JSON](https://aider.chat/2024/08/14/code-in-json.html)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)
- [SWE-bench bash-only leaderboard](https://swebench.com/verified)
- [OpenHands critic / inference-time scaling](https://openhands.dev/blog/sota-on-swe-bench-verified-with-inference-time-scaling-and-critic-model)
- [OpenHands paper](https://arxiv.org/html/2407.16741v3)
- [AutoCodeRover](https://arxiv.org/html/2404.05427v3)
- [SWE-Search / Moatless](https://arxiv.org/pdf/2410.20285)
- [Trae Agent](https://arxiv.org/html/2507.23370v1)
- [CodeMonkeys](https://arxiv.org/pdf/2501.14723)
- [R2E-Gym hybrid verifiers](https://arxiv.org/abs/2504.07164v1)
- [DeepSWE](https://huggingface.co/agentica-org/DeepSWE-Preview)
- [Kimi-Dev](https://arxiv.org/pdf/2509.23045)
- [The Danger of Overthinking](https://arxiv.org/pdf/2502.08235)
- [Diff-XYZ](https://arxiv.org/abs/2510.12487v2)
- [Let Me Speak Freely?](https://arxiv.org/pdf/2408.02442)

Gemma-4 tool-call format:
- [vLLM gemma4 utils](https://docs.vllm.ai/en/latest/api/vllm/tool_parsers/gemma4_utils/)
- [HF forum: Gemma 4 tool-call malformation](https://discuss.huggingface.co/t/gemma-4-bug-fixes-and-research-request/176979)
- [vLLM issue #44522](https://github.com/vllm-project/vllm/issues/44522)

Internal sources: HC, TB, FA; `results/px/px_c20ae_s*`, `px_c9e_s1`, `px_c15n512_s1` traces; `results/kaggle/*-t30s/capture.jsonl`; `chat_template.jinja`. The analysis scripts used for §1 are throwaway (session scratchpad) and simple to re-create from the table definitions.
