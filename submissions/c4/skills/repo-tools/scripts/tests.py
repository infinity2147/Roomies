"""List existing test files / test functions that mention a name (to pick a targeted pytest run).

Usage: --name <identifier> [--k 10]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clip, iter_py_files, read, repo_root  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--k", type=int, default=10)
    a = ap.parse_args()
    root = repo_root()
    name = a.name.strip().strip("`").rsplit(".", 1)[-1]
    pat = re.compile(r"\b" + re.escape(name) + r"\b")
    found = []
    for rel in iter_py_files(root, include_tests=True):
        base = os.path.basename(rel)
        if not (base.startswith("test_") or base.endswith("_test.py") or "/tests/" in "/" + rel):
            continue
        try:
            src = read(os.path.join(root, rel))
        except OSError:
            continue
        n = len(pat.findall(src))
        if n:
            funcs = []
            cur = None
            for line in src.splitlines():
                m = re.match(r"\s*(?:async\s+)?def\s+(test\w*)", line)
                if m:
                    cur = m.group(1)
                if cur and pat.search(line) and cur not in funcs:
                    funcs.append(cur)
            found.append((n, rel, funcs))
    if not found:
        print(f"No test file mentions {name!r}.")
        return
    found.sort(key=lambda x: -x[0])
    out = [f"Test files mentioning {name!r}:"]
    for n, rel, funcs in found[: a.k]:
        out.append(f"  {rel} ({n} mentions) e.g. {', '.join(funcs[:4])}")
    out.append(f"Run one with: python3 -m pytest -x -q {found[0][1]}")
    print(clip("\n".join(out)))


if __name__ == "__main__":
    main()
