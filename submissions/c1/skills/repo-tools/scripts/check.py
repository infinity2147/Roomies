"""Compile every changed .py file, then run a targeted pytest and print a compact verdict.

Usage: [--tests "<pytest target(s)>"]   e.g. --tests "tests/test_markdown.py -k table"
Without --tests it only compiles and lists changed / untracked files (scratch files end up in the patch!).
"""

import argparse
import os
import py_compile
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clip, repo_root  # noqa: E402


def run(cmd: list[str], cwd: str, timeout: int = 240) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", default="")
    a = ap.parse_args()
    root = repo_root()
    out = []
    _, status = run(["git", "status", "--porcelain"], root)
    changed = [ln[3:].strip() for ln in status.splitlines() if ln.strip()]
    ignore = {"pytest.ini", "conftest.py"}
    changed = [c for c in changed if c not in ignore]
    out.append("Changed/untracked files: " + (", ".join(changed) if changed else "(none — nothing to submit yet)"))
    untracked = [ln[3:].strip() for ln in status.splitlines() if ln.startswith("??")]
    if untracked:
        out.append("WARNING untracked files will be in the patch (delete scratch files): " + ", ".join(untracked))
    bad = False
    for c in changed:
        if c.endswith(".py") and os.path.exists(os.path.join(root, c)):
            try:
                py_compile.compile(os.path.join(root, c), doraise=True)
            except py_compile.PyCompileError as e:
                bad = True
                out.append(f"SYNTAX ERROR in {c}: {str(e).splitlines()[-1][:300]}")
    if not bad:
        out.append("All changed .py files compile.")
    if a.tests.strip():
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--no-header", "-rfE"] + shlex.split(a.tests)
        code, text = run(cmd, root)
        lines = text.strip().splitlines()
        summary = [ln for ln in lines if ln.startswith(("FAILED", "ERROR", "E   ")) or " passed" in ln or " failed" in ln or "error" in ln.lower()[:20]]
        out.append(f"pytest exit code {code} ({'PASS' if code == 0 else 'FAIL'})")
        out.extend(summary[-25:] if summary else lines[-25:])
    print(clip("\n".join(out)))


if __name__ == "__main__":
    main()
