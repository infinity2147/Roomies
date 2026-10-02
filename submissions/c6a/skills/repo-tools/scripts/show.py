"""Print a function/class/method definition with line numbers.

Usage: --name <name | Class.method | module.path.Class.method> [--file <relative path>] [--max_lines 120]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import clip, definitions, iter_py_files, read, repo_root  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--file", default=None)
    ap.add_argument("--max_lines", type=int, default=120)
    a = ap.parse_args()
    root = repo_root()
    want = a.name.strip().strip("`").removesuffix("()")
    files = [a.file.lstrip("./").removeprefix("workspace/")] if a.file else list(iter_py_files(root, include_tests=True))
    hits = []
    for rel in files:
        try:
            src = read(os.path.join(root, rel))
            defs = list(definitions(src))
        except (SyntaxError, ValueError, OSError):
            continue
        mod = rel[:-3].replace("/", ".")
        for q, kind, s, e, _ in defs:
            full = f"{mod}.{q}"
            if q == want or full.endswith("." + want) or full == want:
                hits.append((rel, q, s, e, src))
    if not hits:
        print(f"No definition named {want!r} found. Try a shorter name or grep.")
        return
    # Prefer non-test files
    hits.sort(key=lambda h: ("test" in h[0], h[0]))
    out = []
    if len(hits) > 1:
        out.append(f"{len(hits)} matches: " + ", ".join(f"{h[0]}:{h[2]} {h[1]}" for h in hits[:10]))
    rel, q, s, e, src = hits[0]
    lines = src.splitlines()
    end = min(e, s + a.max_lines - 1)
    out.append(f"== {rel} lines {s}-{e} ({q})")
    out.extend(f"{i:5d}  {lines[i - 1]}" for i in range(s, end + 1))
    if end < e:
        out.append(f"... ({e - end} more lines; read_file {rel} {end + 1}-{e})")
    print(clip("\n".join(out)))


if __name__ == "__main__":
    main()
