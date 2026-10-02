"""Rank the functions/classes most likely to need changes for an issue.

BM25 over every def/class in non-test Python files (name tokens weighted 3x + body tokens), plus boosts
for identifiers quoted in the issue (`backticks`), dotted paths and mentioned file paths.
Usage: --query "<issue title + key identifiers / error text>" [--k 12]
"""

import argparse
import math
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import STOP, clip, definitions, iter_py_files, read, repo_root, split_ident, tokenize  # noqa: E402

_BACKTICK = re.compile(r"`([^`\n]{1,200})`")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DOTTED = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_PYPATH = re.compile(r"[\w./-]+\.py\b")
PATH_W = float(os.environ.get("LOCATE_PATH_W", "0.5"))


def anchors(q: str):
    back = {w for span in _BACKTICK.findall(q) for w in _WORD.findall(span) if len(w) > 2 and w.lower() not in STOP}
    idents = {w for w in _WORD.findall(q) if len(w) > 3 and ("_" in w or re.search(r"[a-z][A-Z]", w))}
    dotted = {d for d in _DOTTED.findall(q) if not re.fullmatch(r"[\d.]+", d)}
    paths = {p.strip("./") for p in _PYPATH.findall(q)}
    return back, idents, dotted, paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--k", type=int, default=12)
    a = ap.parse_args()

    root = repo_root()
    docs, meta = [], []
    for rel in iter_py_files(root):
        try:
            src = read(os.path.join(root, rel))
            defs = list(definitions(src))
        except (SyntaxError, ValueError, OSError):
            continue
        lines = src.splitlines()
        for q, kind, s, e, _ in defs:
            body = "\n".join(lines[s - 1 : min(e, s + 120)])
            name_toks = [t for comp in q.split(".") for t in split_ident(comp) + [comp.lower()]]
            docs.append(name_toks * 3 + tokenize(body) + tokenize(rel.replace("/", " ")))
            meta.append((rel, q, kind, s, e))
    if not docs:
        print("no python definitions found under", root)
        return

    # BM25
    n = len(docs)
    avgdl = sum(map(len, docs)) / n
    df = Counter(t for d in docs for t in set(d))
    qtoks = Counter(tokenize(a.query))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t, qtf in qtoks.items():
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                f = tf[t]
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / avgdl)) * min(qtf, 3)
        scores.append(s)

    back, idents, dotted, paths = anchors(a.query)
    short_count = Counter(m[1].rsplit(".", 1)[-1] for m in meta)
    top = max(scores) or 1.0

    # file-path evidence: query terms that appear in the file's path components (idf over files)
    generic = {"py", "init", "main", "utils", "util", "src", "lib", "core", "base", "common", "helpers"}
    files = sorted({m[0] for m in meta})
    ftoks = {f: set(tokenize(f[:-3].replace("/", " "))) - generic for f in files}
    fdf = Counter(t for ts in ftoks.values() for t in ts)
    qset = set(qtoks)
    path_bonus = {}
    for f, ts in ftoks.items():
        if ts:
            w = {t: math.log(1 + len(files) / fdf[t]) for t in ts}
            path_bonus[f] = sum(w[t] for t in ts & qset) / sum(w.values())
    for i, (rel, q, kind, s, e) in enumerate(meta):
        short = q.rsplit(".", 1)[-1]
        bonus = 0.0
        if short in back:
            bonus += 0.6 / math.sqrt(short_count[short])
        elif short in idents:
            bonus += 0.3 / math.sqrt(short_count[short])
        if any(q.endswith(d.split(".", 1)[-1]) or d.endswith("." + q) for d in dotted):
            bonus += 0.4
        mod = rel[:-3].replace("/", ".")
        if any(p and (rel.endswith(p) or p.endswith(rel)) for p in paths) or any(mod.endswith(d.rsplit(".", 1)[0]) for d in dotted if "." in d):
            bonus += 0.25
        bonus += PATH_W * path_bonus.get(rel, 0.0)
        scores[i] = scores[i] / top + bonus

    order = sorted(range(n), key=lambda i: -scores[i])
    out = [f"Top {a.k} code locations for the query (repo: {root}):"]
    for i in order[: a.k]:
        rel, q, kind, s, e = meta[i]
        out.append(f"  {rel}:{s}-{e}  {kind} {q}   score={scores[i]:.2f}")
    files = []
    for i in order[:60]:
        if meta[i][0] not in files:
            files.append(meta[i][0])
    out.append("Most relevant files: " + ", ".join(files[:6]))
    out.append("Next: read_file the top hits (use the line ranges), or run show.py --name <qualname>.")
    print(clip("\n".join(out)))


if __name__ == "__main__":
    main()
