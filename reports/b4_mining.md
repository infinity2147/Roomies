# B4 — tasks mined from git history (2026-10-02)

Pipeline: `src/mining/mine.py` → `src/mining/build_snapshots.py` → `src/eval/verify_gold.py --name mined_` (gold + empty) → `src/eval/valid_set.py mined_`.

| repo | commits before cutoff | candidates (src+test, ≤5 files, ≤300 lines, no eval-function overlap) | snapshot+verified (gold ✓, empty ✗) |
|---|---|---|---|
| rich | 2902 | 260 (200 checked) | **62** |
| fastapi | 5881 | 55 | **4** |
| requests | 4654 | 280 (200 checked) | **0** |
| httpx | — | snapshot has only 4 commits | — |

**Total verified: 66** → `data/derived/mined_tasks.jsonl`. Weak (short commit-message) statements: 48/66 → need generated issue text (Gemma, `synthetic_statement=true`) before SFT use.

## Why below the 200 target (Gate B allows a documented reason)
- requests: old history imports `cgi` (removed in Python 3.13, 151 tasks) and old urllib3 APIs (`SNIMissingWarning`, 44) → cannot run in the 3.13 sandbox with the competition wheels.
- fastapi: ~96% of commits are docs/translations; remaining old ones need `passlib` or pydantic-v1 APIs.
- rich: 22 more candidates had tests that already pass without the fix (non-discriminating) → excluded.

## Leakage guard
Snapshot histories are rebuilt (fast-export), so eval `base_commit` SHAs are not resolvable; cutoff = earliest eval PR `created_at` − 60 days per repo, plus dropping any commit whose hunk headers touch a function changed by any eval gold patch.
