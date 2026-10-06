
## This cycle: DAILY RELEASE (then continue with work if time allows)
1. Read ops/autopilot/STATE.md and ops/autopilot/lb_scores.tsv; harvest finished jobs first (as in a work cycle).
2. Choose today's submission. Rules:
   - Release a candidate in place of the champion only if the evidence says it is at least as good
     (calibrated proxy and/or public-task evals, ≥2 seeds, paired comparison) and it passes the D9 runtime check.
   - A submission/day is also an experiment. If no candidate clearly beats the champion, release the most
     informative candidate whose expected score is close to the champion's (a one-variable change vs the
     champion, so the LB result is interpretable). Never release something with a known runtime or validity risk.
   - Never re-release an identical zip that already has an LB score.
3. Build it: `scripts/package_submission.sh submissions/<name> submissions/daily/<today>/submission_<today>_<name>.zip`
   (it must pass the validator), and write submissions/daily/<today>/RELEASE.md with:
   - line 1: `SUBMIT: submission_<today>_<name>.zip` (the zip filename)
   - what it is, the single change vs the champion, the evidence table (task set, seeds, pass counts),
     expected LB range, runtime projection, risks, and what we learn from its LB score.
   Then point submissions/daily/LATEST at today's dir (ln -sfn).
4. Update STATE.md (record the release as "awaiting LB score"), add a DECISIONS.md entry, and commit.
5. With the remaining time, continue as a WORK cycle (steps 3–5 of the work prompt): launch the jobs that will
   produce tomorrow's evidence.
