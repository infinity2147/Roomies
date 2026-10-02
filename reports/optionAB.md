# P10 — Option A vs B for shipping a learned localizer (2026-10-02)

## What we verified
- Skills work end-to-end in the official harness (Kaggle 4×L4 runs C1–C6): `run_skill_script` executes our stdlib Python scripts inside the task sandbox with the repo at the working directory; calls are not counted in `max_tool_calls` (time still counts); per-command timeout = `timeout_seconds` (we use 120 s).
- Allowed submission file types: `.yaml .yml .md .txt .py .json .safetensors`; ≤50 MiB per skill directory; ≤3 GiB total. **No `.npz`/pickle.**
- The scorer sandbox image is `python:3.13-slim` + pytest/build backends (Dockerfile.sandbox): **numpy is not guaranteed**. Scripts must be pure stdlib.
- The organizers' graph JSON / embeddings live on the host and back the `get_code_*` / `search_similar_code` tools only; a skill script **cannot read them**. A skill-side policy must build its own graph from `/workspace` (Python `ast`), as `locate.py` already does for BM25 (≈0.3–1 s on these repos).
- Gemma rarely calls skills unprompted; with plain-text call templates in the prompt (C3+), calls are well-formed. Usage is still low (C3: 4 locate calls / 30 tasks), so any shipped localizer must be either invoked by the prompt workflow explicitly or merged into the always-used `locate.py`.

## Decision
**Option A (policy as a skill script) is feasible and preferred** if a learned localizer beats BM25 on held-out repos (Gate B/D):
- weights as JSON (or a `.py` literal), linear/MLP scorer in pure Python, features from `ast` graph + BM25 computed on the fly;
- drop-in replacement for the ranking inside `scripts/locate.py` (same output format), so the frozen prompt doesn't change — **no SFT data invalidation** (P2 rule).

Option B (distil traversal into a `loc_lora`) only if a skill-side policy can't run within ~2 s or the analyzer sub-agent pattern returns.

## Open question (Gate C/P5)
Whether localization is even the bottleneck: in C-series triage "wrong location" was 3–5/30 vs "right file, wrong fix" 8–11/30. P5 on the P4 runs decides whether D matters for the competition or is paper-only.
