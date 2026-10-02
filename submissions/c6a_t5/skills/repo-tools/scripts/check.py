"""Clean up, compile and test your change. Run it before submit_patch.

1. Reverts edits to existing test files / test-runner configs (the scorer replaces them; an edited
   test file makes the hidden tests fail to apply and the task scores zero).
2. Deletes untracked scratch files (repro*.py, test_*.py, debug files) — they would end up in the patch.
3. Compiles every changed .py file and, with --tests, runs a targeted pytest with a compact verdict.
Usage: [--tests "<pytest target(s)>"]   e.g. --tests "tests/test_markdown.py -k table"
"""

import argparse
import os
import py_compile
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clip, repo_root  # noqa: E402

PROTECTED_NAMES = {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", ".pytest.ini",
                   "sitecustomize.py", "usercustomize.py"}
SCRATCH = re.compile(r"(^|/)(repro|reproduce|scratch|debug|tmp|temp|check|verify|test)[\w-]*\.(py|txt|sh|json|log)$")


def is_test_path(p: str) -> bool:
    base = os.path.basename(p)
    parts = p.split("/")
    return (base.startswith("test_") or base.endswith("_test.py")
            or any(d in ("tests", "test", "testing") for d in parts[:-1]))


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

    _, status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    reverted, deleted = [], []
    for ln in status.splitlines():
        code, path = ln[:2], ln[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        base = os.path.basename(path)
        if code == "??":
            if base in PROTECTED_NAMES or SCRATCH.search(path) or is_test_path(path):
                try:
                    os.remove(os.path.join(root, path))
                    deleted.append(path)
                except OSError:
                    pass
        elif (is_test_path(path) or base in PROTECTED_NAMES) and path not in ("pytest.ini", "conftest.py"):
            run(["git", "checkout", "HEAD", "--", path], root)
            reverted.append(path)
    if reverted:
        out.append("Reverted edits to test/config files (never edit tests; fix the source code): " + ", ".join(reverted))
    if deleted:
        out.append("Deleted untracked scratch/test files: " + ", ".join(deleted))

    _, status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    changed = [ln[3:].strip().strip('"') for ln in status.splitlines() if ln.strip()]
    changed = [c for c in changed if c not in ("pytest.ini", "conftest.py")]
    out.append("Files in your patch: " + (", ".join(changed) if changed else "(none — make your source edit!)"))

    bad = False
    for c in changed:
        if c.endswith(".py") and os.path.exists(os.path.join(root, c)):
            try:
                py_compile.compile(os.path.join(root, c), doraise=True)
            except py_compile.PyCompileError as e:
                bad = True
                out.append(f"SYNTAX ERROR in {c}: {str(e).splitlines()[-1][:300]}")
    if not bad and changed:
        out.append("All changed .py files compile.")

    if a.tests.strip():
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--no-header", "-rfE"] + shlex.split(a.tests)
        code, text = run(cmd, root)
        lines = text.strip().splitlines()
        summary = [ln for ln in lines if ln.startswith(("FAILED", "ERROR", "E   ")) or " passed" in ln or " failed" in ln]
        out.append(f"pytest exit code {code} ({'PASS' if code == 0 else 'FAIL'})")
        out.extend(summary[-25:] if summary else lines[-25:])
    out.append("If the patch looks right, call submit_patch now.")
    print(clip("\n".join(out)))


if __name__ == "__main__":
    main()
