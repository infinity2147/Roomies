"""B4 step 1: mine candidate SWE tasks from git history inside the competition snapshots.

Candidate = non-merge commit touching >=1 non-test .py source file AND >=1 test .py file, small
(<= MAX_FILES files, <= MAX_LINES changed lines), not docs-only. Split diff into `patch` (source)
and `test_patch` (tests). Problem statement = commit subject + body (flag `synthetic_statement`
stays False; short messages are flagged `weak_statement`).

Leakage guard: per repo, keep only commits strictly older than the earliest eval task's PR
creation time minus 60 days (base SHAs are rewritten in the snapshots), and drop commits whose source diff touches the same
functions as any eval gold patch hunk header (extra safety).

Usage: .venv/bin/python -m src.mining.mine  -> data/derived/mined_candidates.jsonl
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from unidiff import PatchSet

from src.dataio.loaders import DATA, load_tasks

MINING = DATA / "derived" / "mining"
REPOS = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich", "psf/requests": "requests"}
MAX_FILES, MAX_LINES = 5, 300


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace").stdout


def is_test(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    return base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py" or any(
        p in ("tests", "test", "testing") for p in parts[:-1])


def hunk_funcs(patch: str) -> set[str]:
    """Function/class names appearing in hunk headers (@@ ... @@ def foo)."""
    return {m for m in re.findall(r"^@@[^@]*@@\s*(?:async\s+)?(?:def|class)\s+(\w+)", patch, re.M)}


def main() -> None:
    tasks = load_tasks()
    out_rows = []
    stats = defaultdict(Counter)
    for repo_name, short in REPOS.items():
        repo = MINING / short
        evals = [t for t in tasks if t.repo == repo_name]
        # Snapshot histories were rebuilt with fast-export, so eval base_commit SHAs are not
        # resolvable here; use the earliest eval PR creation time minus a 60-day safety margin.
        import datetime as _dt
        earliest = min(_dt.datetime.fromisoformat(t.created_at.replace("Z", "+00:00")) for t in evals)
        cutoff = int(earliest.timestamp()) - 60 * 86400
        eval_funcs = set().union(*(hunk_funcs(t.patch) for t in evals))
        eval_funcs -= {"__init__", "__call__", "__repr__", "__eq__"}
        log = git(repo, "log", "--no-merges", "--format=%H%x1f%ct%x1f%s%x1f%b%x1e", f"--before={cutoff}")
        for rec in log.split("\x1e"):
            rec = rec.strip()
            if not rec:
                continue
            sha, ct, subj, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
            stats[short]["commits"] += 1
            if int(ct) >= cutoff:
                stats[short]["after_cutoff"] += 1
                continue
            numstat = git(repo, "show", "--numstat", "--format=", sha).strip().splitlines()
            files, lines = [], 0
            for ln in numstat:
                parts = ln.split("\t")
                if len(parts) == 3:
                    a, d, p = parts
                    files.append(p)
                    lines += (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
            py = [f for f in files if f.endswith(".py")]
            src = [f for f in py if not is_test(f) and not f.startswith(("docs/", "docs_src/", "scripts/"))]
            tst = [f for f in py if is_test(f)]
            if not src or not tst:
                stats[short]["no_src_or_test"] += 1
                continue
            if len(files) > MAX_FILES or lines > MAX_LINES:
                stats[short]["too_big"] += 1
                continue
            diff = git(repo, "show", "--format=", "--no-color", "-M", sha)
            try:
                ps = PatchSet(diff)
            except Exception:  # noqa: BLE001
                stats[short]["unparseable"] += 1
                continue
            src_patch = "".join(str(f) for f in ps if f.path.endswith(".py") and not is_test(f.path))
            test_patch = "".join(str(f) for f in ps if is_test(f.path))
            other = [f.path for f in ps if not f.path.endswith(".py")]
            if not src_patch.strip() or not test_patch.strip():
                stats[short]["empty_split"] += 1
                continue
            if hunk_funcs(src_patch) & eval_funcs:
                stats[short]["overlaps_eval_funcs"] += 1
                continue
            parent = git(repo, "rev-parse", f"{sha}^").strip()
            if not parent:
                continue
            statement = (subj + ("\n\n" + body.strip() if body.strip() else "")).strip()
            stats[short]["kept"] += 1
            out_rows.append({
                "instance_id": f"mined_{short}_{sha[:10]}", "repo": repo_name, "base_commit": parent,
                "commit": sha, "patch": src_patch, "test_patch": test_patch, "problem_statement": statement,
                "hints_text": "", "created_at": ct, "source": "git_history", "synthetic_statement": False,
                "weak_statement": len(statement) < 60, "non_py_files": other,
            })
    out = DATA / "derived" / "mined_candidates.jsonl"
    with open(out, "w") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    for k, v in stats.items():
        print(k, dict(v))
    print(f"kept {len(out_rows)} candidates -> {out}  (weak statements: {sum(r['weak_statement'] for r in out_rows)})")


if __name__ == "__main__":
    main()
