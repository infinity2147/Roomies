# Phase A notes (2026-10-01)

## Environment (this server)
- 2× RTX A5000 24 GB, **shared** (other users' jobs currently on both GPUs), 64 CPU, 125 GB RAM, driver 550 / CUDA 12.4. No Docker/podman.
- `.venv` (py3.13): research code (numpy, lightgbm, unidiff, ...).
- `.venv-harness` (py3.12): vLLM 0.19.1 + torch 2.10 cu128 (CUDA OK on driver 550) + swegemma — **model server only**.
- `.venv-eval` (py3.13, built on clean uv CPython in `external/python/`): swegemma/adk harness, no torch.
  Base interpreter mirrors `Dockerfile.sandbox` (pytest, pytest-timeout==2.1.0, typer, build backends,
  imp.py, telnetlib.py) + test-only plugins the hidden image evidently has (pytest-httpbin, ...).
- Harness wheels: Kaggle dataset `metric/gemma-4-developer-agent-wheelhouse` → `external/wheelhouse/`.
- Model: Kaggle `google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2` → `external/models/` (23.3 GB single safetensors).

## Facts that change PLAN.md
1. **Graph has a single edge type `calls`** (also used for class→method containment). No imports/contains/called_by.
   D1 action space: EXPAND(node, dir ∈ {out, in}) instead of 4 edge types.
2. **Node schema = {id, name, text}** only; no file path / line numbers. Name = dotted module path relative to
   repo root with `src/`, `docs_src/` stripped. B1 re-derives spans via `ast` (src/groundtruth/map_patch.py).
3. **`hints_text` is empty for all 129 tasks.**
4. Gold patches: median 1 file / 2 hunks, all `.py`, never touch tests. ~15% of fastapi tasks add new files.
5. **httpx has 1 task** → LORO has effectively 3 folds (fastapi 67, rich 48, requests 13); httpx = extra test point.
6. **Allowed submission extensions**: .yaml .yml .md .txt .py .json .safetensors. **No .npz** → RL policy weights
   for Option A must ship as .json / .py literal (or .safetensors read by pure python).
7. Hidden test env ≈ per-repo pinned deps we cannot see. Locally, deps resolved per task by pip from `data/wheels`
   under repo constraints (src/eval/harness_patches.py). Local "valid task set" = gold resolves ∧ empty fails.
8. Scoring hardware 4×L4, vLLM TP=4, max_model_len 32768, gpu util 0.80. Default budgets in Kaggle scorer:
   60 min/task, 100 tool calls, unless eval_config.yaml overrides.
9. Public LB top ≈ 0.17 (2026-10-01).

## Entry points
- `scripts/serve_vllm.sh [submission_dir]` — Kaggle-identical vLLM flags; TP/GPU_UTIL/PORT env.
- `scripts/eval_submission.sh <submission_dir> <run_name> [ids_file|all]` — local end-to-end eval.
- `.venv-eval/bin/python -m src.eval.verify_gold --mode {gold,empty}` — harness sanity, no LLM.
- `.venv/bin/python -m src.dataio.audit`, `.venv/bin/python -m src.groundtruth.map_patch`.

## A1 result: local valid-task set (gold resolves ∧ empty fails)
**107/129** → `data/derived/valid_tasks.txt` (fastapi 58/67, rich 39/48, requests 9/13, httpx 1/1).
- Empty patch already passes: fastapi_14077, fastapi_14851 (tests don't discriminate locally).
- Gold fails locally (20): version drift in pinned deps we can't see (rich: pygments/markdown-it output;
  requests: idna `InvalidURL`, SSL cert in 6757; fastapi 14962/14964/14186/14356/15745/15763/15785).
  These may still be solvable in the hidden env; just not measurable locally.
- Base image additions beyond Dockerfile.sandbox: pytest-httpbin, httpbin, trustme, pytest-mock, inline-snapshot, dirty-equals.
