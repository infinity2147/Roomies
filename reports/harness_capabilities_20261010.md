# Harness capabilities audit: what a bundle can legally do (2026-10-10)

`H/` = `.venv-eval/lib/python3.13/site-packages/` (swegemma, adk_submission, adk_eval_core and google.adk; `.venv-harness` holds the same swegemma).
`README` = `data/HARNESS_README.md` (organiser doc). `KP/` = competition pages fetched read-only on 2026-10-10 with the Kaggle API (`competition_list_pages`). They are not stored in the repo; re-fetch them to re-check.
Builds on `reports/autopilot/harness_knobs_20261007.md` (= KNOBS) and `reports/autopilot/l2_spike_20261007.md` (= SPIKE). Where this audit contradicts either of them, it says so.

## 1. Intra-task parallelism and multiple candidates

**Schema.** Four agent classes are supported: `LlmAgent` (default), `SequentialAgent`, `ParallelAgent` and `LoopAgent` (H/adk_submission/schema.py:257-361; README:104-124).
- Workflow agents accept only `name`, `description`, `sub_agents` and callbacks, and swegemma drops the callbacks (KNOBS Q1).
- `LoopAgent.max_iterations` is bounded 1..500.
- **LoopAgent cannot exit early.** No `exit_loop` tool exists in the registry. The README "Model Selection…" page allows only the harness tools plus `agent_tool`, so a loop always runs exactly `max_iterations` times.
- `LlmAgent.sub_agents` enables `transfer_to_agent` (H/google/adk/flows/llm_flows/agent_transfer.py:29-57). Transfer is a sequential hand-off, and ADK does not count it against the budget.
- After a nudge, the harness re-runs the root unless every ancestor sets `disallow_transfer_to_parent` (H/google/adk/runners.py:1082; SPIKE Q4).

**Tools and budget.**
- One `SwegemmaContext` builds every tool (H/swegemma/tools/__init__.py:34-46). The 100-call counter is therefore shared by all agents, AgentTool children and skill scripts:
  - `check_budget` increments `tool_calls_used` (H/swegemma/context.py:467-550).
  - Skill scripts pass through `budget_check_fn=context.check_budget` (H/swegemma/harness/agent_runner.py:326-332; H/adk_eval_core/sandbox/base.py:179-180).
- **Stale memory note:** "skills are not budget-gated" is wrong. Each `run_skill_script` call costs 1 call. `load_skill` and `load_skill_resource` are free.
- `get_status` and `submit_patch` are not counted (H/swegemma/tools/execution.py:76,106).
- The root gets `RunConfig(max_llm_calls=500 - used)` (agent_runner.py:516). AgentTool children get their own default of 500 and no compaction (KNOBS Q1/Q2).
- `max_time_minutes` is enforced by `asyncio.timeout` around the whole loop (agent_runner.py:440). Every tool also returns `TimeoutExceeded` once the time is spent (context.py:526-547), and that includes `submit_patch`.

**Concurrency.**
- `ParallelAgent` runs its branches as asyncio tasks in one TaskGroup (H/google/adk/agents/parallel_agent.py:51-87). Branch histories are isolated, but session state, `/workspace` and the container are shared.
- Two function calls emitted in one model turn also run concurrently (H/google/adk/flows/llm_flows/functions.py:389-405). For example, two `agent_tool` calls would overlap.
- swegemma tools are synchronous. The harness sets no `tool_thread_pool_config` (functions.py:972-984), so each tool runs inline on the event loop (H/google/adk/tools/function_tool.py:231-238) and holds `tool_lock` (H/swegemma/tools/base.py:82-93).
- **Net effect: only LLM decoding overlaps. Tool execution is serialised and blocks the other branch.**

**submit_patch and the final diff.**
- `submit_patch` runs `git add -N . && git diff --binary _swegemma_baseline` and stores the result (execution.py:86-99). It can be called again, and the last call wins.
- It does **not** end the run. The loop breaks when (a) a text-only final event from a non-user author arrives after a submit (agent_runner.py:566-579), or (b) `run_async` returns with `patch_submitted` set (agent_runner.py:635-637).
- **The scored patch is the last submit_patch snapshot, not the tree at the end** (agent_runner.py:758). Edits made after the last submit are lost.
- The working-tree diff is used only if submit was never called (agent_runner.py:761-776).
- Consequence: under a time cap, "submit early, re-submit after each improvement" is safe. The one risk is that a text-only message after a submit ends the task.

**Git-based candidate selection is legal.**
- `run_command` has no path or cwd restrictions (execution.py:20-47).
- The baseline is the tag `_swegemma_baseline` (H/swegemma/harness/container_setup.py:581).
- `git diff > /tmp/cand_X.diff`, `git reset --hard _swegemma_baseline && git clean -fdq`, `git apply`, `git worktree add` and `cp -a` all work.
- Anything under /tmp never enters the diff. The file tools reach only `/workspace` (H/swegemma/tools/workspace.py:22-55).

**C14p (`submissions/c14p_bestof2`).**
- Structure: `Sequential[Parallel[solver_a, solver_b] -> selector]` (agent.yaml:1-8; sub_agents/parallel_solvers.yaml).
- **solver_a**: full tools in /workspace, repro-first, cap of 40 calls stated in the prompt (prompts/solver_a.md:12-21). It saves `/tmp/patch_a.diff`.
- **solver_b**: shell only. It copies /workspace to `/tmp/ws_b` and works there with a `PYTHONPATH` prefix, test-first, cap of 35 calls (prompts/solver_b.md:4-24).
- **selector**: `include_contents: none` and only `run_command`/`get_status`/`submit_patch`. It follows 5 scripted steps (prompts/selector.md:12-28):
  1. Snapshot /workspace and reset it.
  2. Build a scoreboard: apply each diff, py_compile it, run both repros and test_b.
  3. Run the nearest existing tests.
  4. Rank by repro/test passes, then fewer test failures, then the smaller diff.
  5. Apply the winner and submit.
- Sampling = C11t with thinking on (configs/sampling.yaml).
- **Legal**: schema-valid, single model, harness tools only (SPIKE Q2; validated by package_submission.sh).
- **Robustness risks**:
  1. The call caps are prompt-only; 40+35+12 = 87 of the shared 100. If the solvers overrun, the selector gets `BudgetExceeded`. The fallback is then solver_a's tree, or **an empty tree if step 1 had already reset it**.
  2. Wall time: both solvers run every time, with serialised tools plus selector pytest runs. SPIKE estimates 1.3-1.7x C11t, and C11t is already about 1.8x C9ae.
  3. solver_b can test the wrong tree if it forgets the prefix.
  4. A nudge re-runs the entire Sequential.
  5. `{identifier}` in any prompt raises a templating KeyError.
- **Evidence**: +0.263 on n=19 (STATE.md:72, "tiny; run seeds before believing it"). There is no Kaggle timing run.

## 2. Time awareness and adaptive effort

**Per-task signals (legal and free).**
- `get_status` returns `tool_calls_used/remaining`, `time_seconds_remaining`, `agent_elapsed_seconds`, `max_time_minutes` and `command_timeout_seconds` (execution.py:106-132). It is not counted.
- The task prompt lists the time and tool-call allowances whenever they are set (agent_runner.py:69-83).
- From 10 calls remaining onward, every counted tool response carries a `budget_warning` (base.py:47-69).
- `date` through `run_command` works but costs a call, so prefer `get_status`.

**No global signal.**
- `task_index`/`total_tasks` go only to the display manager (agent_runner.py:350-366). The agent never sees them.
- Each task gets a fresh sandbox, and container reuse wipes `/tmp /var/tmp /root /workspace` (H/swegemma/sandbox/docker.py:778-783).
- Cross-task timing state is therefore unavailable. Do not try to smuggle it through other host paths: that is a rules risk.
- **Global adaptivity is possible only through a fixed per-task cap.**

**eval_config.yaml.**
- Organiser text: "You may … set per-task time limits in your submission's `eval_config.yaml`" (KP/Evaluation:33).
- The README lists keys under `evaluation:`: `max_time_minutes`, `max_tool_calls`, `max_turns` and `timeout_seconds` (per-command timeout), all loaded by the scorer's `scripts/inference.py` (README:98, 524-546).
- swegemma itself has no reader. The scorer notebook does the parsing, and our runners mirror it (src/eval/run_eval.py:30-44; scripts/kaggle_eval/kernel_template.py:215).
- **This corrects KNOBS Q1** ("none of these can be set from a submission"): they can.
- `max_time_minutes` is honoured on the LB (C6a_t5 / C9ae_t5; DECISIONS.md:126).
- **Raising `max_tool_calls` above 100 is documented but unverified on the scorer.**
- Sampling settings are not eval_config keys. Temperature, seed, top_p/k, penalties, `max_output_tokens` and `thinking_config` belong in `generate_content_config` in agent.yaml (README:146-151).
- Caveat: `include_thoughts: false` forces thinking off and ignores `thinking_budget` (H/adk_submission/resolvers/generation.py:290-301).

## 3. Patch-validity safeguards: what exists and what is missing

**Harness behaviour that matters.**
- `edit_file` (workspace.py:216-294 → H/adk_eval_core/editing/edit.py:401-454) tries four tiers in order:
  1. Exact substring match.
  2. Flexible match: line-window match with rstrip, then full strip. It **re-indents `new_string`** to the matched block (edit.py:138-236, 93-106).
  3. Regex match: token-level, whitespace-insensitive, whole lines (edit.py:239-305).
  4. JSON-unescape fallback (edit.py:353-398).
- Error messages:
  - not found: "Failed to replace: old_string not found. Ensure you're not escaping…" (edit.py:446-454)
  - multiple matches: "Expected N occurrence(s)… set 'allow_multiple'" or "Target string (flexibly) matches N locations…" (edit.py:118-128, 179-187; H/swegemma/edit.py:56-67)
  - empty file: "use write_file" (workspace.py:252-255)
  - identical strings: "old_string and new_string are identical" (edit.py:416-422)
- **No syntax check after any edit.** The response includes a `strategy` field; any value other than `exact` should be followed by py_compile.
- The 612 rejected calls versus 518 accepted were mostly not match failures. They were ADK "mandatory input parameters are not present" errors (H/google/adk/tools/function_tool.py:179-188), caused by a stray backtick that swallows `old_string` (reports/council/trajectory_forensics.md:174-177).
- In verification:
  - An empty patch is never applied or tested, so it scores 0 (H/swegemma/harness/verification.py:308).
  - A non-empty patch goes through 4 apply passes (README §8.2).
  - Any test or config file the patch touched is then reset (verification.py:60-83, 390-415). This covers `test_*.py`, `*_test.py`, `.py` under `tests/`, `test/` or `testing/`, `conftest.py`, `pytest.ini`, **`pyproject.toml`, `setup.cfg`, `tox.ini`** and `*.pth`.
  - So test or config edits are **discarded, not fatal**. The C8 lineage prompt says otherwise: system.md:20 claims a test edit means "the task then scores zero". Edits that a fix genuinely needs in pyproject or setup.cfg are silently lost.

**Inventory.** All bundles are prompt-only; none has a skill or adapter that checks the patch.

| bundle | parent | safeguard | where |
|---|---|---|---|
| C8 (base of all) | anchor | no test/conftest/CI/packaging edits; scratch files to /tmp; always submit ("best-effort beats no patch"); py_compile after every edit; `git status`/`git diff` plus revert of test/scratch files before submit; retry a failed edit twice with a smaller snippet | c8_anchorplus/prompts/system.md:5-9,19,20,25 |
| C9a editfix | C8 | after 1 failed `edit_file`, switch to a heredoc `python3` replace with `assert src.count(OLD)==1`; no backticks/fences in edit strings | c9a_editfix/prompts/system.md:25-27 |
| C9b reprofail | C8 | repro must FAIL on unmodified code; if it passes, the hypothesis is wrong (vary input shape, check `isinstance`/`in`) | c9b_reprofail/prompts/system.md:17 |
| C9c timebox | C8 | first real edit before 40% of time/calls; brute-force/property check in /tmp for arithmetic/offset bugs | c9c_timebox/prompts/system.md:23-24 |
| C9d importcheck | C8 | `python -c "import <top-level package>"` before submit | c9d_importcheck/prompts/system.md:19 |
| C9e analyzercap | C8 | analyzer limited to ≤20 calls and ≤60-line reads, no repeated calls; analyzer sampling 4096 out / thinking off | c9e_analyzercap/prompts/analyzer.md:16-21; configs/analyzer_sampling.yaml |
| C9ae | C9a + C9e | union of the two | c9ae_editfix_analyzercap/ |
| C11t | C9ae | **only** change: root `include_thoughts: true` (thinking on; analyzer stays off) | c11t_c9ae_think/configs/sampling.yaml:7 |
| C14b / C14c / C14d | **C11t (thinking)** | exactly the C9b / C9c / C9d one-line edits applied to C11t's system.md (lines 17 / 23-24 / 19); no eval_config, so uncapped thinking | `diff -r c11t_c9ae_think c14*` |
| C11tc | C11t | eval_config `max_time_minutes: 5`, `max_tool_calls: 100`, `timeout_seconds: 300` | c11tc_timecap/eval_config.yaml |
| skills/graph-locate, C13l/C13t `repo-locate`, C16 | — | localisation only (1 counted call); no patch checks | skills/graph-locate/scripts/graph_locate.py; c13l_c9ae_locskill/skills/repo-locate/SKILL.md |

**Gaps.** Every safeguard is a prompt instruction the model may skip. None is deterministic.

| failure | current cover | gap |
|---|---|---|
| malformed edit_file (missing args) | C9a heredoc fallback after 1 failure | the first failure is still spent; nothing prevents backticks in heredoc text |
| failed or ambiguous fuzzy match | C9a fallback; the harness message asks for more context | silent mis-indentation from the flexible/regex tiers is never flagged |
| syntax errors | "py_compile after every edit" (prompt) | not enforced; no check right before the final submit |
| import failures | C9d/C14d prompt line only | no check of the module(s) actually changed |
| tests/config modified | prompt rules; the harness resets these files anyway | real `pyproject`/`setup.cfg` fixes are lost without warning |
| empty submission | "always submit" (prompt) | no check that the diff is non-empty before the final text |
| scratch files in patch | "scratch to /tmp" plus `git status` review (prompt) | no automatic removal of `repro*.py`, `*.orig`, `*.rej`, `*.bak` |
| edits after the last submit | none | lost silently (§1) |

## 4. Reproduction, timebox and import prompts versus parents
- **C9b vs C8, and C14b vs C11t**: identical one-sentence addition to step 3. The repro (`/tmp/repro.py`, created by heredoc) "must FAIL on the unmodified code before you edit anything; if it passes, your hypothesis is wrong: change the input shape and check type facts in Python (`isinstance`, `in`) instead of assuming them."
  - No attempt or call bound.
  - No rule for the case where the repro cannot be made to fail.
  - It doesn't tell the model to rerun the repro after the fix, though step 5 already says to.
- **C14c vs C11t**: the C9c timebox lines (commit-early before 40%; "runs that never edit always score zero"; brute-force/property check).
- **C14d vs C11t**: the C9d import line.
- All C14x bundles inherit C11t thinking (`include_thoughts: true`, budget 4096) with no `eval_config`. That means the 60-minute scorer default and the 1.8x runtime problem (D29).

## 5. Kaggle submission rules
- Rules §2 (KP/rules:27-33, fetched today):
  - **1 submission per day**.
  - **Up to 2 Final Submissions**.
  - Team of at most 5, mergers allowed. To merge, the combined team's submission count must not exceed (submissions/day × days running).
- Timeline: team-merger and entry deadline 2026-11-25; final deadline 2026-12-02 (KP/Timeline). The same limits are recorded in reports/rules.md:12-13.
- `kaggle competitions submission-limits gemma-4-developer-agent` (today): **Submissions today 0, Remaining today 1**, lifetime 4.
- **The belief of "3 submissions per 24 h" is not confirmed.** Both the rules page and the CLI say 1 per day for the CLI-authenticated account.
- reports/council/paper_plan.md:35 says "5 per day", but that is the *paper* competition.
- Side finding from `kaggle competitions submissions`: c9ae_t5 (2026-10-08) scored **0.08** on the public LB. C9ae scored 0.10 and C8 0.13.

## 6. Legal mechanisms for: selective best-of-2, bounded reproduction, deterministic patch checks, adaptive effort

**A. Selective best-of-2.** The design is sequential and conditional, inside one root agent. `ParallelAgent` cannot be conditional; it always runs every branch.

```yaml
# agent.yaml (root = C11n/C9ae-style LlmAgent)
tools: [run_command, read_file, edit_file, write_file, get_status, submit_patch,
        {agent_tool: {config_path: sub_agents/alt_solver.yaml, skip_summarization: true}}]
skills: [skills/patch-tools]          # select.py + check.py below
# eval_config.yaml: evaluation: {max_time_minutes: 6, max_tool_calls: 130, timeout_seconds: 120}  # >100 unverified on scorer
```

Prompt rule:

> After the first fix, run `check.py` and `submit_patch` (candidate A is now banked). Call `get_status`. If the repro still fails, **and** `time_seconds_remaining > 50%` and `tool_calls_remaining > 45`:
> 1. `git diff --binary _swegemma_baseline > /tmp/cand_a.diff && git reset -q --hard _swegemma_baseline && git clean -fdq`
> 2. Call `alt_solver` with the issue and "approach A failed because …".
> 3. `run_skill_script patch-tools scripts/select.py`: it applies each `/tmp/cand_*.diff` plus the current tree, runs `/tmp/repro.py` and the named tests with `timeout 60`, re-applies the winner and prints the scoreboard.
> 4. `submit_patch`.
>
> Otherwise submit A.

The worst case is A, which is already banked by the submit. The extra cost falls only on unresolved-looking tasks.

**B. Bounded reproduction.** Replace C9b's sentence with:

> Reproduce in at most 2 attempts / 6 calls. `/tmp/repro.py` must exit non-zero on the baseline (`timeout 60`). If it still passes after 2 attempts, write `UNREPRODUCED` in your plan and fix from the code reading. Never spend more calls on it.

A deterministic helper, `scripts/repro_ab.py` (one call):
- `git worktree add -f /tmp/base _swegemma_baseline` (once);
- run the repro under `PYTHONPATH=/tmp/base:/tmp/base/src`, then under `/workspace`;
- print `BASE: FAIL|PASS  NOW: FAIL|PASS`.

The worktree metadata stays out of the diff.

**C. Deterministic patch checks.** `skills/patch-tools/scripts/check.py`, run once before every `submit_patch` (1 counted call). It runs in the shared sandbox (KP/"Model Selection…"):
1. `git add -N .`, then list the files in `git diff --name-only _swegemma_baseline`.
2. Delete scratch files: new untracked files that match `repro*|debug*|scratch*|*.orig|*.rej|*.bak` or sit at the repo root and are not imported anywhere.
3. Report protected paths, using the same predicate as verification.py:60-83. Revert `test_*`/conftest files. **Warn**, without reverting, on `pyproject.toml`/`setup.cfg` that the harness will discard them.
4. `python -m py_compile` on every changed `.py` file.
5. `python -c "import <dotted module of each changed file>"`, mapped from its path and handling src layout.
6. `EMPTY` if the diff is empty.
7. Print `OK` or a list of `FAIL:` lines. The prompt says: "Never call submit_patch on FAIL or EMPTY; fix and re-run check (max 2 times), then submit anyway."

Prompt additions:
- If an `edit_file` response has `strategy` other than `exact`, run py_compile on that file immediately.
- Never send backticks inside edit arguments (C9a).

**D. Adaptive effort.**
- Global: a fixed per-task cap through `eval_config.yaml` (`max_time_minutes` ≈ 5-6 → ≈ 12 h / 120 tasks with setup). This is the only legal global lever.
- Per task, keyed on free `get_status` readings:
  - **≤25% time used**: full workflow, including analyzer and repro.
  - **>40%** with no edit yet: edit now (C9c).
  - **>60%**: no new exploration; verify, check, submit.
  - **>85%**: `submit_patch` immediately, without emitting text in between.
- Pair this with "submit early, re-submit after each improvement", since the last submit wins and a timeout keeps the banked patch (§1).
- Thinking cannot be switched per turn. It can differ per agent, as in C17: thinking on only in the analyzer.
