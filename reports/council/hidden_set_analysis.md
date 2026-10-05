# Hidden-set analysis and proxy benchmark (Hidden-Set Analyst)

**Question.** C6a_t5 solves roughly 0.20–0.30 of our locally valid public-repo tasks but scores 0.06 on the public leaderboard (LB). Which repositories are in the hidden set? Can we build an offline benchmark that predicts the LB?

**Short answer.** We cannot name the hidden repositories. Several independent lines of evidence say they are **private, never-published repos, very likely Google-internal Python projects** (tasks keyed by changelist (CL) number, Google test conventions). The wheel cache contains **no** information about them. As the best available stand-in, I built a **152-task proxy benchmark from 16 unseen repos in two strata**. The first stratum is GitHub-PR tasks (108). The second is Google Copybara/CL tasks (44), whose terse CL-description problem statements look like the most important distribution shift. This proxy should replace the 4-repo valid set as the primary offline metric, but only after it passes the calibration check in D11: the anchor (LB 0.12) must score above C6a_t5 (LB 0.06).

---

## 1. Facts about the hidden set (with evidence)

| # | Fact | Evidence |
|---|---|---|
| F1 | 13 benchmark repos in total; 4 are public, so **9 are hidden**. The private list was emptied before release. | `.venv-eval/.../swegemma/harness/sample_verification.py:1` ("…across all 13 repositories"), `:32-39` (`KNOWN_PUBLIC_REPOS` = fastapi, httpx, requests, rich; `KNOWN_PRIVATE_REPOS = frozenset()`). |
| F2 | The organizers say the test set "was curated from a set of **private repositories**". | Competition data page text, mirrored in github.com/sweeden-ttu/developer-agent README (WebFetch). Kaggle itself returned only the page title. |
| F3 | The public LB has **58 tasks**, and every score is k/58. So 0.06 means k = 3 or 4 (0.052/0.069), 0.12 means k = 7, and 0.17 means k = 10. One task is worth 1.7 points. At p = 0.06 the binomial SE is ±1.8 tasks, so **0.06 vs 0.12 is only about 2 SE.** | github.com/yosh95/g4-developer-agent-paper `paper/writeup_body.md` §3.8 ("every distinct public score is exactly floor(k/58)"). |
| F4 | Two other teams independently see the same drop from public to hidden: 34.5 % local → 3/58, and 28 % local → 4/58. The ratio is about **1/5**, matching ours (~0.20 → 0.06). | same file §3.8. |
| F5 | The public wheel cache is fully explained by the public repos. Every multi-version package matches a pin in the public snapshots' requirement files. Examples: `typer==0.16.0` appears in 45 snapshots, `sqlmodel==0.0.27` in 39, `flask>=1.1.2` in 49, and `starlette>=0.40.0` in 57 (fastapi `requirements-*.txt`). `Dockerfile.public` says "open-source public wheels cache only (zero private wheels…)". The scorer loads its own wheels from `…/secret/sandbox/wheels`. **Conclusion: you cannot infer the hidden repos from `data/wheels`, and tasks failing on missing wheels says nothing about the organizers' choice of repos.** | `data/docker/Dockerfile.public`; `container_setup.py:46,78`; pin census over the 129 snapshots (commands in this session). The subprocess sandbox also references a Kaggle dataset `ryanholbrook/gemma4swe-wheelhouses` (Kaggle staff; returns 404 publicly). |
| F6 | `imp.py` shim ("specifically for flasgger") **is explained by the public repos**: requests' tests use pytest-httpbin → httpbin → flasgger, which needs `imp`. Not evidence about the hidden repos. | `external/python/.../site-packages/httpbin/core.py` prints "flasgger is not installed…" in our verification logs. |

## 2. Hypotheses about what the hidden repos look like

| H | Claim | Strength | Evidence |
|---|---|---|---|
| H1 | Hidden tasks come from **Google-internal / Copybara-style repos, keyed by CL number**. | **Medium** | `deduplication.get_task_cl`: "Extracts integer **CL** or numerical issue/PR ID", including an optional `cl` task field. `identify_base_snapshot` sorts on CL first. None of the public tasks needs this: they use PR numbers and have no `cl` field. |
| H2 | Hidden repos use **Google test conventions**: `foo_test.py` files, `FooTest` classes, absltest/unittest, and `fake_gfile`. | **Medium** | The harness pytest config adds `python_files = test_*.py *_test.py` and `python_classes = Test* *Test` (`container_setup.py:893-895`, `sample_verification.py:365`). `verification._is_test_file` accepts `*_test.py`. **0/129 public test_patches touch a `*_test.py` file, and 0/129 define a `*Test` class**, so these settings exist for the hidden repos. `difficulty.MOCK_PATTERN` lists `fake_gfile`, a TF/Google-internal test fake. The agent prompt disables unittest discovery and suggests `python3 path/to/test.py` (runnable absltest files). |
| H3 | At least one hidden repo (or its dependency) imports **`telnetlib`**, and one may compile **`.proto`** files. | Weak | The `telnetlib.py` shim and the `protobuf-compiler` apt package are in both Dockerfiles. Nothing in the public repos, their test deps, the base python or `.venv-eval` imports telnetlib (grep: 0 hits), and no public repo uses protoc. |
| H4 | Specific public repos named in the harness, `pallets/flask` and `psf/requests-oauthlib`, are hidden repos. | Weak | They appear only as docstring examples in `deduplication.clean_repo_name`, next to two real public repos. They are illustrative, not data. |
| H5 | Problem statements in the hidden set are **shorter and less specific** than PR bodies: CL descriptions rather than issue reports. | Weak to medium (follows from H1) | Real Google CL descriptions in our proxy have a median of 58 chars, versus 418 for the public valid set (table §3.2). |

**Ranked candidates.** No public repo can be named with better than weak evidence. Ranked by usefulness as a stand-in:

1. Google Copybara-exported Python repos: pyglove, fiddle, ml_collections, etils, adk-python (fits H1, H2, H5).
2. pallets/flask and requests-oauthlib (H4).
3. Generic mid-size pure-Python libraries.

The proxy below covers all three.

## 3. Proxy benchmark

### 3.1 Construction (mimics the organizers' curation)

The code is `src/analysis/hidden/mine_proxy.py`; outputs are in `data/derived/proxy/`.

- **GitHub-PR stratum** (13 repos): flask, click, werkzeug, jinja, typer, sqlmodel, starlette, tqdm, requests-oauthlib, marshmallow, attrs, tenacity, sqlparse.
  - Candidates are merged PRs from 2023 onward: squash `Title (#N)`, pallets-style `(#N)` merge commits, or `Merge pull request #N`. Each diff must touch 1–4 non-test `.py` source files (≤250 changed lines) and ≥1 test `.py` file.
  - I took the 18 most recent PRs per repo.
  - Problem statement = PR title + "\n\n" + PR body, scraped from the PR page (raw HTML cached in `pr_pages/`). `hints_text` is "" and `instance_id` is `<repo>_<PR#>`, like the public tasks.
- **Google-CL stratum** (5 repos): adk-python, pyglove, fiddle, ml_collections, etils.
  - Candidates are single-parent Copybara commits carrying `PiperOrigin-RevId`, using the same diff filters.
  - `instance_id` is `<repo>_<CL>` and the problem statement is the CL description (trailers stripped).
- `patch` holds only non-test `.py` hunks and `test_patch` holds only test `.py` hunks, in public style (`--- a/` and `+++ b/` headers; 278/278 public patch files are `.py`).
- Snapshots are a fresh single-commit repo of the tree at base_commit, as a tar.gz, built like `src/mining/build_snapshots.py`. I used `read-tree`, so tests excluded by `export-ignore` are kept.
- **Validation:** the real harness (`verify_task`) runs gold and empty patches. A task is valid when gold passes and empty fails. Command:

  ```
  .venv-eval/bin/python -m src.analysis.hidden.verify_proxy --mode gold|empty --name proxyw2_
  ```

  (`--tasks data/derived/proxy/tasks_google.jsonl --name proxyg_` for the Google stratum.)

  The wrapper fixes two problems in our local sandbox. Both are faithful to the scorer, which ships the hidden repos' own wheels:
  - **(a)** It installs the proxy repos' test-only deps from `data/derived/proxy/wheels_extra{,_google}/`: hypothesis, simplejson, typeguard, tornado, trio, oauthlib, requests-mock, ephemeral-port-reserve, httpx2/httpcore2, blockbuster, coverage, absl-py, libcst, termcolor and pytest-asyncio.
  - **(b)** It fixes a **local-sandbox bug that also affects the existing public valid set (C6a's "10 env-broken src-layout tasks")**. When the editable install of a `src/`-layout repo fails, `_host_env.pth` (host site-packages) is processed before `workspace_paths.pth`. The host's copy of click, flask, werkzeug, jinja2, attrs or google-adk then silently shadows the workspace. Gold then "fails" and empty "passes": jinja was 0/18 valid before the fix and 15/18 after. The fix writes `00_proxy_workspace_src.pth`.
- With `data/wheels` only and without the fix (`results/verify_proxy_gold`), just 49/193 GitHub-PR golds passed. Almost every failure was a missing test-only dep or the shadowing bug. Neither tells us anything about the organizers' repos (see F5).

### 3.2 Composition (`.venv/bin/python -m src.analysis.hidden.proxy_stats`)

| repo | stratum | candidates | gold pass | empty pass | **valid** |
|---|---|---|---|---|---|
| google/pyglove | google-cl | 18 | 18 | 1 | **17** |
| jd/tenacity | github-pr | 18 | 18 | 2 | **16** |
| pallets/jinja | github-pr | 18 | 17 | 2 | **15** |
| marshmallow-code/marshmallow | github-pr | 18 | 18 | 3 | **15** |
| pallets/click | github-pr | 18 | 15 | 1 | **14** |
| pallets/werkzeug | github-pr | 18 | 16 | 4 | **12** |
| fastapi/typer | github-pr | 18 | 11 | 0 | **11** |
| google/ml_collections | google-cl | 18 | 15 | 4 | **11** |
| google/fiddle | google-cl | 18 | 10 | 0 | **10** |
| python-attrs/attrs | github-pr | 18 | 14 | 5 | **9** |
| fastapi/sqlmodel | github-pr | 18 | 10 | 3 | **7** |
| google/etils | google-cl | 18 | 7 | 1 | **6** |
| tqdm/tqdm | github-pr | 8 | 4 | 0 | **4** |
| pallets/flask | github-pr | 18 | 2 | 0 | **2** (old conftest uses `_pytest.monkeypatch.notset`, removed in pytest 9) |
| andialbrecht/sqlparse | github-pr | 2 | 2 | 0 | **2** |
| requests/requests-oauthlib | github-pr | 3 | 2 | 1 | **1** |
| Kludex/starlette | github-pr | 18 | 0 | 0 | 0 (harness forces `-p no:anyio`, so async tests fail) |
| google/adk-python | google-cl | 18 | 0 | 0 | 0 (needs a newer google-genai than the host env) |
| **total** | | **283** | **179** | **27** | **152** (108 PR + 44 CL) |

Task shape compared with the public valid set:

| set | n | single-file | src files med/p90 | churn med/p90 | statement chars med/p90 | years |
|---|---|---|---|---|---|---|
| public valid | 107 | 72% | 1 / 3 | 11 / 104 | 418 / 1779 | 2023:7 2024:14 2025:44 2026:42 |
| proxy valid (github-pr) | 108 | 82% | 1 / 2 | 14 / 70 | 584 / 1831 | 2023:1 2024:17 2025:6 2026:84 |
| proxy valid (google-cl) | 44 | 70% | 1 / 2 | 27 / 88 | **58 / 333** | 2024:10 2025:20 2026:14 |

Files:
- `data/derived/proxy/valid_tasks.jsonl` and `.txt`: 152 tasks, harness schema.
- `data/derived/proxy/proxy60_tasks.jsonl`: fast subset, ≤5 per repo, seed 0, **69 tasks over 16 repos**.
- `tasks.jsonl` and `tasks_google.jsonl`: all candidates.
- `snapshots/`: 1.2 GB.
- Verification results: `results/verify_proxy{w2,g}_{gold,empty}/`.

### 3.3 How representative is it? (hypotheses, untested until calibrated)

- **What it gets right:** these are repos the agent has never been tuned on, with no code graphs (same as any repo without graph files). It uses the same harness, the same patch/test split, a similar diff size, and the same "title + body" statement layout. 84/108 PR tasks are from 2026, likely after the model's training cutoff, so they are less memorized than fastapi/rich.
- **What it gets wrong:**
  1. The repos are popular public libraries; Gemma has probably seen older versions of them. The hidden repos are private, so the proxy probably **overestimates** the absolute score.
  2. If H1/H5 hold, the hidden statements look like the **google-cl** stratum (terse CLs), not PR bodies. The google-cl score is probably the more LB-like number.
  3. The test deps are ours, not the organizers'.
  4. With n = 152, one SE is about ±3.5 pp at p = 0.2. On the 69-task subset it is about ±5 pp.
- **Expectation to test:** if the hidden shift is "unfamiliar repo + terse spec", configurations should rank the same on proxy and LB. The anchor (0.12) should beat C6a_t5 (0.06), and google-cl absolute scores should sit closest to the LB. If the proxy does **not** rank anchor > C6a_t5, the gap is caused by something it does not model, such as the hidden repo environment or `*_test.py`/absltest test style.

## 4. How to use it (decision implications)

1. **Make the proxy the primary offline metric (D11)**, reported per stratum: PR, CL, and the combined score. Keep the 4-repo set as a secondary check for regressions.
   - Run command (applies the proxy provisioning and points `run_eval` at `data/derived/proxy/evaldata_<set>/`):
     ```
     .venv-eval/bin/python -m src.analysis.hidden.run_proxy_eval --set proxy60 --submission-dir submissions/X --results-dir results/proxy/X
     ```
   - `--set valid` runs all 152 tasks.
2. **Calibrate first.** Run the anchor bundle and C6a_t5 on proxy60, 2 seeds each. Adopt the proxy only if anchor > C6a_t5 there, ideally by more than 1 SE.
3. **Design for H1/H2/H5 regardless.**
   - The prompts and skills should handle terse one-line task statements and `*_test.py` / absltest test files. For example, `tests.py` should find `foo_test.py` next to `foo.py`, not only `tests/test_foo.py`.
   - The agent should be told it may run `python3 path/to/x_test.py` directly (the harness disables test discovery, not files run directly).
   - These are cheap changes and do no harm if the hypotheses are wrong.
4. **Fix the shadowing bug in `src/eval/harness_patches.py`** (one `.pth` line; see `verify_proxy.py`). It probably also explains our 10 env-broken public src-layout tasks.
5. **Do not trust single LB comparisons below about 3 tasks (5 pp)** (F3).

Code: `src/analysis/hidden/{mine_proxy,verify_proxy,proxy_stats,run_proxy_eval}.py`. Clones are in `data/derived/proxy/repos/` (not committed).
