"""Offline file-level recall of the C13L repo-locate skill vs. a naive grep-count baseline and the old c6a locate.py.

Extracts each snapshot's .py files to /tmp, runs the skill script standalone with the problem statement
(as the analyzer would pass it), and checks whether the gold (non-test, modified) .py files are in the top-k.
Usage: python -m src.eval.eval_c13l_locate [--tasks data/derived/proxy/proxy60_tasks.jsonl] [--limit N] [--jobs 4]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "submissions" / "c13l_c9ae_locskill" / "skills" / "repo-locate" / "scripts" / "locate.py"
OLD = ROOT / "submissions" / "c6a" / "skills" / "repo-tools" / "scripts" / "locate.py"
TEST_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|conftest\.py$")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def gold_files(patch: str) -> list[str]:
    out = []
    for m in re.finditer(r"^--- a/(\S+)\n\+\+\+ b/(\S+)", patch, re.M):
        p = m.group(1)
        if p.endswith(".py") and not TEST_RE.search(p) and p not in out:
            out.append(p)
    return out


def naive_rank(root: str, issue: str) -> list[str]:
    """grep -c baseline: identifiers that look like code (snake/camel/backticked), raw occurrence count per file."""
    terms = {w for w in IDENT.findall(issue) if "_" in w.strip("_") or re.search(r"[a-z][A-Z]", w)}
    terms |= {w for span in re.findall(r"`([^`]+)`", issue) for w in IDENT.findall(span) if len(w) > 2}
    cnt = Counter()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root)
            if TEST_RE.search(rel):
                continue
            src = open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()
            c = sum(len(re.findall(r"\b" + re.escape(t) + r"\b", src)) for t in terms)
            if c:
                cnt[rel] = c
    return [f for f, _ in cnt.most_common(10)]


def run_one(args) -> dict:
    t, snapdir = args
    gold = gold_files(t["patch"])
    issue = t["problem_statement"]
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="c13l_") as td:
        subprocess.run(["tar", "xzf", str(Path(snapdir) / f"{t['instance_id']}.tgz"), "-C", td,
                        "--wildcards", "*.py", "./.git/HEAD"], capture_output=True)
        os.makedirs(os.path.join(td, ".git"), exist_ok=True)
        t0 = time.time()
        r = subprocess.run([sys.executable, "-I", str(SKILL), "--issue", issue, "--root", td],
                           capture_output=True, text=True, timeout=120)
        dt = time.time() - t0
        ranked = re.findall(r"^\d+\. (\S+)", r.stdout, re.M)
        m = re.search(r"^Also: (.*)$", r.stdout, re.M)
        if m:
            ranked += [x.strip() for x in m.group(1).split(",")]
        naive = naive_rank(td, issue)
        o = subprocess.run([sys.executable, "-I", str(OLD), "--query", issue[:1500]], capture_output=True, text=True,
                           timeout=120, env={**os.environ, "SWE_WORKSPACE": td})
        mo = re.search(r"Most relevant files: (.*)", o.stdout)
        old = [x.strip() for x in mo.group(1).split(",")] if mo else []

    def hit(lst, k):
        return bool(gold) and any(g in lst[:k] for g in gold)

    return {"instance_id": t["instance_id"], "repo": t["repo"], "gold": gold, "top": ranked[:5], "secs": round(dt, 2),
            "lines": r.stdout.count("\n"), "err": r.stderr[-300:],
            **{f"c13l@{k}": hit(ranked, k) for k in (1, 3, 5)},
            **{f"naive@{k}": hit(naive, k) for k in (1, 3, 5)},
            **{f"old@{k}": hit(old, k) for k in (1, 3, 5)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(ROOT / "data" / "derived" / "proxy" / "proxy60_tasks.jsonl"))
    ap.add_argument("--snapshots", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    snap = a.snapshots or str(Path(a.tasks).parent / "snapshots")
    tasks = [json.loads(line) for line in open(a.tasks) if line.strip()]
    tasks = [t for t in tasks if gold_files(t["patch"]) and (Path(snap) / f"{t['instance_id']}.tgz").exists()]
    if a.limit:
        tasks = tasks[: a.limit]
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(run_one, [(t, snap) for t in tasks]))
    n = len(rows)
    for sysname in ("c13l", "naive", "old"):
        print(f"{sysname:6} " + "  ".join(f"@{k}={sum(r[f'{sysname}@{k}'] for r in rows) / n:.3f}" for k in (1, 3, 5)))
    secs = sorted(r["secs"] for r in rows)
    print(f"n={n}  secs median={secs[n // 2]:.2f} max={secs[-1]:.2f}  max_lines={max(r['lines'] for r in rows)}  "
          f"errors={sum(bool(r['err'].strip()) for r in rows)}")
    if a.out:
        Path(a.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


if __name__ == "__main__":
    main()
