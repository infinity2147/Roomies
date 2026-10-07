# repo-locate (C13l) offline localization eval — 2026-10-07

Script: `submissions/c13l_c9ae_locskill/skills/repo-locate/scripts/locate.py` (invoked as `locate.py --issue "<problem_statement>"`, cwd = repo, as ADK `run_skill_script` does).

## Method
- 48 tasks from `data/derived/proxy/tasks.jsonl`, all 13 repos (4 per large repo, 2-3 for tqdm / requests-oauthlib / sqlparse; seeded shuffle).
- Workspace per task: `git -C data/derived/proxy/repos/<repo> archive <base_commit> | tar -x` into `/tmp/locate_eval/ws/<id>` (data/ untouched).
- Gold files = non-test `.py` files in the gold `patch`; gold lines = removed/insertion-point old-file lines.
- Metrics: rank of first gold file among numbered list + "Also:" line; range hit = any printed `L<s>-<e>` range in a gold file covers a gold line; range@top1 = first range of the #1 file covers a gold line.
- Baseline: grep code-like identifiers (snake_case / CamelCase / Capitalized, len>=4) from the issue, rank non-test files by number of distinct identifiers hit.
- Harness: `/tmp/locate_eval/tools/run_eval.py`; raw results `/tmp/locate_eval/r1.jsonl`.

## Results (n=48, after fixes; file-rank numbers identical before fixes)
| metric | locate.py | grep baseline |
|---|---|---|
| gold file top-1 | 34 (71%) | 21 (44%) |
| gold file top-3 | 42 (88%) | 31 (65%) |
| gold file top-5 | 46 (96%) | 38 (79%) |
| gold file anywhere in output (top-10) | 47 (98%) | 40 (83%) |
| a printed range covers gold line | 39 (81%) | n/a |
| first range of #1 file covers gold line | 24 (50%) | n/a |
| runtime median / max | 0.30 s / 0.65 s | — |
| output lines median / max | 21 / 22 | — |
| crashes / timeouts | 0 / 0 | — |

Top-1 by repo (locate / grep): starlette 3/1, sqlparse 2/2, sqlmodel 4/3, typer 3/1, tenacity 3/2, marshmallow 2/1, click 3/3, flask 2/2, jinja 3/3, werkzeug 2/0, attrs 2/1, oauthlib 2/1, tqdm 3/1 (n=4 per repo, small-n).

## Bugs found and fixed (in place)
1. **@overload qualname collision** in `rank_defs`: defs were aggregated by qualname only, so hit lines from several `@overload` stubs were attributed to the last def's range (e.g. `L1117-1833 Argument [hit lines 1007,...]`, `L733-767 retry [hit lines 694,...]`). 22 printed range lines across the 48 outputs had hit lines outside their own range -> 0 after fix. Now keyed by (qualname, start line); `@overload`-decorated stubs get score x0.3 so the implementation is listed first.
2. **Non-deterministic "matches:" order** (set iteration under hash randomization, ties in sort) -> sorted before ranking; two runs now byte-identical.
No crashes or garbage output observed.

## Failure examples
- `requests_oauthlib_537` ("Preparing the 2.0.0 to replace 1.4.0"; gold = version bump in `__init__.py`): no usable terms; unsolvable for any localizer.
- `marshmallow_2892`: no code identifiers in issue ("terms: plain words only"); gold `validate.py` at rank 2 via word "handle".
- `starlette_2858` (gold `middleware/errors.py`, rank 7): prose-only issue about event loop blocking; ranks `testclient.py` first.
- `flask_6133` (add `query()` route shortcut, gold `sansio/scaffold.py` rank 5): the new method doesn't exist yet, word "query" matches testing/app first.
- `typer_1791`: right file `typer/core.py` rank 3 behind `params.py` (huge `Argument`/`Option` defs, ranges 700+ lines long are not useful to `sed`).
- Ranges are often whole classes (e.g. `L110-1628 Flask`) — low value; first range of #1 file is right only 50% of the time.

## Caveats
- Proxy tasks come from the same repos the skill may have been tuned on; hidden-task performance likely somewhat lower.
- The relevant comparison on GPU is vs the agent's own grep/find exploration, not this trivial baseline; benefit = fewer exploration turns/context, risk = anchoring on a wrong #1 file (29% of tasks).

## Recommendation
Worth a GPU A/B (C13l vs C9ae): it is fast (<1 s), compact (<=22 lines), never crashes, and beats the grep baseline by +27 pts top-1 / +23 pts top-3. Measure resolve-rate and turns-to-first-edit; watch for anchoring failures on tasks where #1 is wrong.
