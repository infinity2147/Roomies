# GEMMA-RL — MASTER EXECUTION PROMPT
## Finish Training, Fix Repair Failures, Improve Accuracy, and Prepare Competition Submissions

You are the principal ML research engineer, agent-systems architect, and execution lead for our Gemma-RL project.

I want you to take ownership of making real technical progress.

**Do not just give me research suggestions, another lengthy plan, or generic explanations. Inspect the actual repository, verify the existing work, implement justified improvements, complete pending experiments, evaluate results, and prepare strong submission candidates.**

I have not previously given you the improvement prompts from my discussions with ChatGPT. This is the complete instruction.

Treat previous status reports as historical information, not guaranteed current facts.

Your work must be grounded in actual code, logs, checkpoints, evaluations, and measurements.

---

# 1. OUR ACTUAL OBJECTIVE

We are participating in the Kaggle Gemma 4 Developer Agent competition.

We must use the fixed Gemma-4-31B local model to understand software bug reports, investigate Python repositories, modify source code, and submit patches that pass hidden verification tests.

The evaluation has approximately 120 hidden tasks and a strict 12-hour execution budget on the scorer's 4×L4 GPU environment.

Our best previously reported public leaderboard score is approximately 0.13.

That is not where we want to remain.

Our objective is:

**Maximize the number of correctly solved hidden tasks within the official 12-hour evaluation budget.**

Do not optimize only for:
- The number of tasks attempted.
- Training loss.
- Localization accuracy.
- Number of tool calls.
- Amount of reasoning.
- Proxy accuracy without runtime constraints.

Optimize for correct patches, reliability, and total successful tasks per unit of available time.

We want to move toward substantially higher reliability, potentially approaching 90–100% on tasks the agent is genuinely capable of solving. However, do not claim that 90–100% overall accuracy is achievable without evidence.

We need meaningful, reproducible improvements.

---

# 2. IMPORTANT NEW INFORMATION

There are two important updates to the previous technical report.

## Update A: Submission availability

I can now make **three Kaggle submissions within 24 hours**, according to my latest information.

Verify the actual active quota, relevant competition rules, submission status, and final-selection limits before using it.

Do not continue assuming the older one-submission-per-day constraint if it no longer applies.

This gives us more opportunities to test promising candidates on the real leaderboard.

However, leaderboard submissions are still valuable and limited. Do not waste them on unverified changes or broken packages.

## Update B: Additional root-cause analysis

A previous investigation classified 171 unsuccessful runs from older C1–C6 configurations.

Reported findings included:

- TIME: 32 runs involved time exhaustion or delayed edits.
- UND/API: approximately 30 runs involved incorrect assumptions about behavior, types, or APIs.
- MALF: malformed edits were a substantial failure source; 612 rejected edit calls versus 518 successful edit calls were reported.
- FIXC: incomplete fixes and non-importing patches caused additional failures.
- Repeated tool calls were frequent, especially without thinking.
- Localization accounted for a relatively small portion of failures.
- Earlier analyzer context overflow was addressed by later configurations.

Another analysis reported that 149 of 171 failed runs had already read the file containing the gold fix.

**Critical caveat:** These findings come largely from older agent configurations, not a fresh analysis of the current C8/C9e/C17 agents on the held-out proxy.

Do not assume their proportions still apply.

Reproduce or update the failure analysis using current trajectories.

These findings strongly motivate investigating patch generation, verification, and wasted execution time instead of investing primarily in better code search.

---

# 3. PHASE ONE — AUDIT THE REAL PROJECT

Start by inspecting the repository, infrastructure, live jobs, and existing experiment results.

Read the latest Gemma-RL technical report, especially the sections covering:

- End-to-end agent experiments.
- Failure analysis.
- Runtime and measurement.
- LoRA training.
- Thinking distillation.
- Proxy benchmark.
- Kaggle leaderboard results.
- Learned graph localization.
- Latest action plan.

Inspect relevant project directories including:

- `src/eval/`
- `src/sft/`
- `src/retrieval/`
- `src/graphbuild/`
- `src/mining/`
- `src/synth/`
- `scripts/`
- `submissions/`
- `reports/`
- `ops/autopilot/`, if present

Also inspect current Git status and recent changes.

Check actual training and evaluation jobs on the available compute infrastructure, including Prajna if accessible.

Determine the current state of:

1. C18 — Nebius-only LoRA evaluation.
2. C19 — Thinking distillation.
3. Mixed Nebius + SWE-Hero LoRA training.
4. C17 — Planner-only thinking and speed evaluation.
5. C16 — Graph-locate evaluation.
6. C9b — Reproduction-related variant.
7. C9e — Analyzer-capped runtime-safe candidate.
8. C14b/c/d — Reproduction, timebox, and import-check variants.
9. C14p — Best-of-2 candidate.
10. Any newer experiments not described in the report.

Classify each experiment as completed, running, failed, blocked, invalid, or not started.

Find the latest checkpoints and results rather than trusting timestamps in older conversations.

**Do not restart healthy jobs, overwrite existing adapters, or repeat completed evaluations unnecessarily.**

After the audit, give me a concise factual status report.

Then continue with execution.

---

# 4. PHASE TWO — FINISH THE EXISTING LORA WORK

This is a mandatory priority.

We have already invested significant compute in LoRA fine-tuning.

I do not want that investment wasted through incomplete evaluations, incorrectly loaded adapters, or abandoned checkpoints.

## 4.1 Nebius-only LoRA — C18

The previous report said the training run finished and the adapter was created.

The valid evaluation was still pending.

An earlier 0/152 result was invalid because the adapter was not actually loaded.

Check the current state.

Verify:
- The final adapter exists.
- The checkpoint is valid.
- The adapter is loaded into the exact intended base model.
- The serving configuration actually activates it.
- Tool calls remain parseable.
- The correct agent scaffold is used.
- The evaluation does not silently fall back to the base model.

If no valid evaluation exists, run the established held-out evaluation.

Do not interpret the invalid 0/152 result as a genuine failure of fine-tuning.

## 4.2 Thinking distillation — C19

This is one of our most important experiments.

The principle is simple:

A thinking-enabled agent can solve more bugs, but it is too slow.

We want to train the non-thinking agent on successful thinking-agent behavior so it can learn better actions without spending as many inference tokens.

Check whether training is complete.

If interrupted, resume safely from the correct checkpoint.

If complete, validate the adapter and evaluate it.

Use the existing intended held-out evaluation split.

Verify that:
- The source trajectories were genuinely successful.
- Reasoning was removed without corrupting conversation structure.
- Assistant-action targets remain correct.
- The model's tool-call format is preserved.
- Training and evaluation tasks remain isolated.
- The loss masks are correct.
- The base checkpoint and adapter are compatible.

Determine whether C19 actually improves resolution accuracy at acceptable inference cost.

A low training loss is not sufficient evidence.

## 4.3 Mixed-data LoRA

The previous training run combined Nebius and SWE-Hero data.

Find its current checkpoint and completion status.

If healthy and running, preserve it.

If interrupted, investigate and resume if appropriate.

If complete, export and validate its adapter.

Evaluate it against the correct baseline.

Verify dataset licensing, task filtering, tool-action conversion, evaluation exclusion, and training provenance.

## 4.4 Compare all adapters

Produce a controlled comparison of:

- Original baseline agent.
- Nebius-only LoRA.
- Thinking-distillation LoRA.
- Mixed-data LoRA.

Include successful tasks, accuracy, runtime, generated tokens, tool-call validity, and uncertainty.

Use the existing repository-held-out benchmark split.

Do not compare different task subsets as if they were identical.

A trained adapter that does not improve held-out resolution must not be presented as an improvement.

## 4.5 Future LoRA training

If one of the existing approaches works, investigate whether improvement can be extended through:

- More verified successful trajectories.
- Better training-data filtering.
- Stronger representation of failure-prone repair patterns.
- Shorter but valid training windows.
- Additional training epochs where justified.
- Rejection-sampling fine-tuning on newly successful trajectories.
- A second iteration using the improved model.
- Better mixing of external data and our successful runs.

Do not automatically increase epochs because training loss is falling.

Do not start another expensive multi-hour training run until the existing experiments are understood and the new hypothesis is justified.

Use the project's available compute responsibly.

---

# 5. PHASE THREE — UNDERSTAND WHY GEMMA PRODUCES WRONG FIXES

This is our highest-priority new accuracy investigation.

The important observation is that the agent frequently identifies relevant code but still fails to repair the bug.

I want to know exactly why this happens in the current agent.

Do a fresh trajectory-level failure analysis on C9e and relevant C17 runs, using the latest representative proxy evaluations.

Do not use only the older C1–C6 taxonomy.

For each failure, investigate:

- Did the agent understand the bug report?
- Did it find the relevant source file?
- Did it identify the correct function?
- Did it understand the expected behavior?
- Did it reproduce the failure?
- Did it edit the code?
- Was the edit valid?
- Did it run tests?
- Did it interpret the test results correctly?
- Did it submit a nonempty patch?
- Did the final patch fail because of a regression?
- Was there sufficient remaining time?
- Did it repeat unproductive tool calls?

Classify the actual causes of failure.

Suggested categories:

1. Wrong diagnosis.
2. Incorrect assumptions about API behavior.
3. Correct file but wrong function.
4. Correct function but wrong modification.
5. Incomplete patch.
6. Syntax/import errors.
7. Malformed tool calls.
8. Invalid reproduction.
9. Incorrect or missing verification.
10. Repeated tool-call loops.
11. Time exhaustion.
12. Context loss or overflow.
13. Hidden requirements not captured by the issue.
14. Genuine localization failure.

Allow multiple contributing causes where necessary, but distinguish a primary cause from secondary observations.

Quantify the categories.

Use concrete traces and examples.

**Deliver the top three causes that currently prevent Gemma from solving bugs.**

Then identify the smallest interventions likely to prevent them.

---

# 6. PHASE FOUR — IMPROVE PATCH GENERATION AND VERIFICATION

I want a better software-repair system, not simply a model that spends more time reading files.

Investigate a workflow based on:

**Understand → Reproduce → Diagnose → Patch → Verify → Submit**

The aim is to prevent incorrect assumptions and incomplete fixes.

## 6.1 Reproduction-first repair

Check whether a reproduction-related experiment already exists, especially C9b and C14b.

Review its results before building a duplicate.

If results are missing, run the necessary controlled comparison.

The proposed behavior is:

1. Determine expected and actual behavior.
2. Attempt a minimal reproduction when feasible.
3. Check whether the reproduction fails on the original code.
4. Identify the root cause.
5. Apply a minimal fix.
6. Check whether the reproduction now passes.
7. Run relevant existing tests.
8. Submit the final source patch.

**Do not require reproduction unconditionally.**

Some bugs cannot be reproduced cheaply, and wasting several minutes on an impossible reproduction would hurt us.

Introduce a bounded reproduction attempt with a clear fallback.

Do not allow a test that passes on the unmodified repository to be treated as evidence of a successful repair.

Measure the improvement separately from any changes to thinking settings.

## 6.2 Patch validity

Investigate lightweight safeguards for:

- Malformed `edit_file` calls.
- Failed fuzzy replacements.
- Invalid Python syntax.
- Import failures.
- Accidental modifications to tests/configuration.
- Empty submissions.
- Unintended scratch files in patches.
- Patches not matching the identified root cause.

Check which safeguards already exist.

For example, inspect the existing edit fallback and clean-up skills instead of implementing duplicates.

Prefer deterministic, low-overhead safeguards when possible.

## 6.3 Independent test generation

Investigate a lightweight test-writer or verifier that receives the issue and relevant code.

Its job is to formulate tests that distinguish broken behavior from the intended behavior.

It should not merely accept the solver's explanation.

A useful verifier should:

- Check the original failure.
- Check the proposed corrected behavior.
- Run relevant existing regression tests.
- Identify contradictions between the issue and the proposed patch.
- Report specific observed failures.

Before integration, test generated checks against known gold patches and incorrect candidate patches.

Evaluate false positives, false negatives, and runtime overhead.

Generated tests cannot guarantee hidden-test success, so do not overstate their reliability.

## 6.4 Targeted correction

When the patch fails verification, allow one targeted correction attempt based on concrete evidence.

Avoid unrestricted cycles of:

edit → test → edit → test → edit → test.

The correction must have a specific reason.

If no useful diagnostic information is available, the agent should avoid wasting further time.

## 6.5 Smallest measurable improvement first

Do not implement all these features at once.

Start with the strongest low-cost hypothesis supported by current trajectory analysis.

Run one controlled experiment against C9e.

Use paired tasks and seeds.

Track both correctness and runtime.

Keep an improvement only if the evidence supports it.

---

# 7. PHASE FIVE — MULTIPLE REPAIR CANDIDATES

The report indicates that multiple attempts sometimes solve different tasks.

A previous best-of-2 experiment, C14p, reportedly showed promising improvement on just 19 tasks.

That result is preliminary and must not be treated as proven.

Investigate whether multiple independent repair candidates can improve total resolved tasks.

Possible architecture:

**Solver A:** Produces a minimal patch.

**Solver B:** Produces an independent alternative.

**Verifier:** Runs relevant tests and checks patch validity.

**Selector:** Chooses the candidate with the strongest execution evidence.

However, we cannot simply double the inference cost.

Our scorer runs under a strict 12-hour limit.

We need to determine whether multiple candidates can be generated efficiently under the actual framework and serving constraints.

Check whether supported intra-task parallelism is permitted through declarative ADK configurations.

Do not add an unauthorized custom evaluation controller.

Consider selective best-of-2:

- Easy tasks receive one attempt.
- A second candidate is generated only when the first fails useful verification or when evidence suggests a second attempt may help.
- Clearly unproductive tasks terminate early.
- Verification and selection remain bounded.

Measure the complete cost.

If the strategy cannot improve total successful tasks under the 12-hour limit, do not ship it.

---

# 8. PHASE SIX — ADAPTIVE THINKING AND TIME MANAGEMENT

Our experiments show that thinking improves accuracy but increases runtime substantially.

Reported scorer-hardware results included:

- C9ae: 8/30 solved, approximately 4.92 min/task.
- C11t: 12/30 solved, approximately 7.67 min/task.
- C11n: 13/30 solved, approximately 8.69 min/task.

The stronger thinking variants do not currently fit a full serial evaluation within 12 hours.

C17 attempted to concentrate thinking in the planner.

Its previous partial runtime ratio was approximately 1.36× the faster baseline, exceeding the intended 1.15× safety limit.

Check its final status and results.

## 8.1 Make thinking cheaper

Investigate:

- Bounded planner reasoning.
- Smaller analyzer thinking budgets.
- Fewer unnecessary planner calls.
- Distilled non-thinking main agent.
- Distilled main agent combined with a bounded planner.
- Better observation selection.
- Repeated-tool-call detection.
- Avoidance of lengthy unproductive reasoning.

Measure actual generated tokens, total runtime, and resolution accuracy.

Do not assume fewer tool calls always means less runtime.

## 8.2 Adaptive task effort

Investigate whether the agent can spend different amounts of time depending on task difficulty and observed progress.

For example:

- Quick diagnosis for straightforward bugs.
- Longer thinking when a plausible root cause has been identified.
- Early termination of repeated tool loops.
- More verification effort for patches with specific unresolved failures.
- Limited retries when they have useful diagnostic evidence.

First determine which mechanisms the official submission format permits.

Verify whether we can legally access a global time budget, skip tasks, or control scheduling.

If not, investigate legal approximations within the per-task agent configuration.

Do not bypass or modify the official scorer.

## 8.3 Compare time-allocation strategies

Compare:

A. Fast agent that attempts all tasks.

B. Thinking agent with deeper per-task reasoning.

C. Adaptive agent that spends time selectively.

D. Selective best-of-2 agent.

Evaluate all under an equivalent 12-hour total runtime budget.

Count unattempted and unfinished tasks as failures when calculating overall score.

Include runtime overhead and variance.

The objective is **total successful repairs**, not accuracy conditional on attempting a task.

---

# 9. PHASE SEVEN — KEEP RESEARCH PRIORITIES RATIONAL

The graph-localization study found that learned rankers improved retrieval, but graph expansion and RL traversal did not provide a measurable incremental benefit in the reported comparison.

Review the actual ablation before accepting this conclusion.

If confirmed, preserve the work for research documentation but do not continue allocating substantial compute to graph RL.

Our priorities should be:

1. Correct patch generation.
2. Reliable verification.
3. Completion and evaluation of existing LoRA.
4. Efficient thinking.
5. Runtime-aware execution.
6. Alternative patch generation when affordable.
7. Localization only where evidence shows it is still limiting.

Do not replace simple, successful components with complicated methods merely because they use reinforcement learning or neural networks.

Measure end-to-end resolved tasks.

---

# 10. PHASE EIGHT — EXPERIMENT PROTOCOL

Every important change must be evaluated fairly.

Use the project's established held-out proxy benchmark and repository isolation rules.

The report describes 152 verified proxy tasks across 16 repositories and an 85-task held-out evaluation split for models trained on the other half.

Respect the correct split for each experiment.

Use matched tasks and random seeds.

Maintain the correct parent baseline.

For every candidate, record:

- Candidate name.
- Exact scaffold version.
- Exact base model.
- Adapter checkpoint, if any.
- Training-data provenance.
- Tasks and seeds.
- Total successes.
- Pass@1.
- Paired improvements and regressions.
- Statistical uncertainty.
- Generated tokens.
- Tool calls.
- Tool-call errors.
- Average and tail runtime.
- Invalid patches.
- Empty patches.
- Correct-file/wrong-fix failures.
- Full-run runtime projection.
- Known limitations.

Distinguish:

- Public leaderboard results.
- Proxy results.
- Held-out fine-tuning evaluation.
- Pilot experiments.
- Partial or unfinished runs.

Do not confuse them.

In particular, do not claim a new feature caused an improvement when multiple features changed simultaneously.

If C14b/c/d improvements are confounded by thinking, isolate their incremental effects.

Check the historical inconsistency in C8 proxy baseline numbers and reconcile evaluation populations before making comparisons.

---

# 11. PHASE NINE — USE THREE KAGGLE SUBMISSIONS STRATEGICALLY

I have three submissions available within 24 hours, subject to verification of the current Kaggle account quota and competition rules.

I want to use this opportunity intelligently.

Do not submit three arbitrary variations.

First identify the best existing runtime-safe candidate.

The older recommendation was:

`submissions/daily/2026-10-09/submission_2026-10-09_c9e_analyzercap.zip`

This was described as C8 plus an analyzer cap, with a main agent identical to C8 and approximately +0.076 on the proxy.

Check whether it exists, has already been submitted, or has been superseded.

Then build a submission strategy.

## Candidate slot 1 — Reliable improvement

Choose the strongest existing validated runtime-safe candidate.

Prefer a candidate with a demonstrated proxy improvement, valid package, and credible full-run completion estimate.

## Candidate slot 2 — Repair-quality improvement

If supported by new measurements, prepare the strongest lightweight improvement involving reproduction, patch verification, malformed-edit recovery, or targeted correction.

It must be compared fairly against the correct baseline.

## Candidate slot 3 — Higher-upside model or reasoning improvement

Consider a LoRA adapter, bounded-planner variant, or selective multi-candidate system only if:

- It has completed valid held-out evaluation.
- Its model and tools work correctly.
- Its runtime is acceptable.
- It satisfies submission constraints.
- It has convincing evidence of value.

If none qualifies, preserve the slot.

The three slots are opportunities, not an obligation to submit three candidates.

**Do not make actual Kaggle submissions without my approval.**

Prepare each qualified candidate and present:

- Exact package path.
- Change from baseline.
- Proxy result.
- Runtime result.
- Estimated scorer completion time.
- Risks.
- Recommended submission order.

Use the public leaderboard as an additional measurement, not the sole selection criterion.

The leaderboard's small public task count makes minor score differences noisy.

The prior five-minute capped submission scored approximately 0.08. Avoid reintroducing that fixed cap without strong new evidence.

---

# 12. COMPUTE AND RESOURCE DISCIPLINE

We have already spent substantial GPU time.

Protect that investment.

You may autonomously:

- Inspect code and logs.
- Write and test scripts.
- Fix reproducible infrastructure errors.
- Run lightweight unit and smoke tests.
- Analyze completed traces.
- Use already-authorized evaluation resources.
- Resume an interrupted job when it is clearly safe and within its existing allocation.
- Make incremental, reversible code changes.

Before launching major additional training or expensive evaluation workloads, verify available allocations and request approval when resources are not already authorized.

Do not:

- Kill unrelated processes.
- Delete valuable checkpoints.
- Restart healthy training.
- Overwrite working submission packages.
- Launch duplicate expensive experiments.
- Leak held-out evaluation data into training.
- Change the required competition model.
- Modify the official evaluator to obtain a better score.
- Assume a background job exists without confirming its scheduler/process state.

Make expensive experiments resumable.

Preserve logs, configurations, dataset manifests, and checkpoints.

---

# 13. EXECUTION ORDER — DO NOT STOP AT A PLAN

Work in this order.

## Stage 1 — Immediate recovery

Audit the current repository and compute environment.

Find every active or completed experiment.

Recover the status of C18, C19, mixed-data LoRA, C17, C16, C9b, and available submission candidates.

Fix invalid evaluation setup and ensure adapters load correctly.

Provide a short status update.

Then proceed.

## Stage 2 — Complete pending work

Finish or safely resume outstanding training.

Evaluate completed adapters.

Complete existing speed and proxy tests.

Do not start new expensive experiments until the existing results are understood.

## Stage 3 — Fix the main failure causes

Analyze current failed trajectories.

Choose the strongest low-cost improvement to patch correctness.

Implement it.

Run a paired evaluation.

Keep or revert based on evidence.

## Stage 4 — Improve reasoning efficiency

Finish C17 analysis.

Evaluate C19.

Test bounded thinking and other justified efficiency improvements.

## Stage 5 — Test more ambitious repair strategies

Investigate independent test generation, targeted correction, and selective best-of-2.

Prioritize experiments that may increase resolved tasks without proportional runtime growth.

## Stage 6 — Prepare submissions

Rank all qualified candidates.

Freeze the strongest one.

Validate the exact package.

Prepare up to three candidates if supported by evidence and active quota.

Request approval before submitting.

Continue other authorized useful work while long-running jobs execute.

If the working session cannot remain active, leave exact resumable state rather than pretending work will continue automatically.

---

# 14. MAINTAIN PERSISTENT PROGRESS

Use the repository's existing state-tracking conventions where possible.

Maintain a project execution status file containing:

**Completed**
What has actually been implemented, tested, or evaluated.

**Running**
Job identifiers, experiment paths, last measured progress, and resource utilization.

**Blocked**
Failures, missing resources, or decisions requiring approval.

**Results**
Measured accuracy, runtime, uncertainty, and parent comparison.

**Next**
The exact next executable action.

Update this after meaningful milestones.

Do not repeatedly produce long explanations without code or experiment progress.

Keep changes reversible and document reproduction commands.

At every major milestone, tell me what changed and what actual evidence supports it.

---

# 15. SUCCESS CRITERIA

I will judge the work by practical outcomes.

### Minimum success

- Existing training and evaluation states are recovered.
- C18, C19, and mixed-data LoRA are correctly completed or resumed.
- Available adapters are validated.
- Invalid prior evaluations are identified.
- We have reliable held-out comparisons.

### Meaningful success

- We understand current failure mechanisms using actual trajectories.
- At least one repair-quality or reasoning-efficiency improvement is implemented and validated.
- We solve more held-out tasks without unacceptable runtime growth.
- We have a reproducible experiment scoreboard.

### Competition success

- We have a validated submission candidate.
- It shows convincing improvement over our current best baseline.
- It satisfies the official submission constraints.
- It has a credible path to completing within 12 hours.
- We use available submission opportunities intelligently.

### Long-term research success

We establish which approaches actually improve bug-fixing reliability:

- Successful-trajectory SFT.
- Thinking distillation.
- Independent verification.
- Targeted correction.
- Multiple repair candidates.
- Adaptive time allocation.

Negative results are valuable when they are rigorously demonstrated.

Do not hide unsuccessful experiments.

---

# 16. THE CENTRAL QUESTION

Our agent already often finds the relevant code.

Why can it not consistently produce the correct fix?

I want us to stop assuming that more localization or more thinking time alone will solve this.

Find the actual bottleneck.

Make the agent diagnose problems more accurately, generate better patches, verify its changes more reliably, and avoid wasting time.

Train it using high-quality successful trajectories, but verify that the resulting adapter genuinely improves end-to-end agent performance.

Use execution feedback wherever it offers better evidence than model confidence.

**The goal is not to make Gemma feel confident. The goal is to make Gemma reliably correct.**

---

# 17. START EXECUTING NOW

Do not respond only with a proposal.

Begin by examining the actual project, active jobs, checkpoints, latest results, and current submission quota.

Give me a concise initial status with:

1. What is complete.
2. What is currently running.
3. What is broken or blocked.
4. What can be evaluated immediately.
5. Which candidate is currently safest to submit.
6. What concrete work you are executing next.

Then continue with the authorized implementation and evaluation tasks.

Complete existing LoRA work, investigate current failure trajectories, run the highest-value experiments, and prepare qualified submission candidates.

Do not wait for me to provide another prompt for each routine development step.

Ask only when approval is needed for major additional GPU usage, destructive actions, competition submissions, or genuinely ambiguous choices.

**Make measurable progress. Preserve reproducibility. Prioritize correct bug fixes. Keep the 12-hour limit central to every decision.**