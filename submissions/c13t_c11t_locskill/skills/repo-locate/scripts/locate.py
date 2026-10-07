"""Rank the source files / functions most likely to need a change for an issue.

Pure stdlib; runs inside the evaluation sandbox (repo at /workspace).
Usage: locate.py --issue "<issue text or keywords>" [--hints "file.py, Class.method"] [--root DIR] [--k 6]

Method (deterministic):
  1. Extract terms from the issue: `backticked` code, snake_case / CamelCase / dotted identifiers,
     traceback frames, *.py paths, error-message fragments, and plain words (low weight).
  2. Index every non-test *.py file: identifier counts + identifier sub-token counts.
  3. Score files by sum(weight * idf * (1 + log tf)) over matched terms, plus bonuses when the file
     defines a matching function/class or its path matches a term.
  4. Map hits to enclosing def/class via `ast`; print a compact ranked list (<= ~60 lines).
"""

import argparse
import ast
import math
import os
import re
import sys
import warnings
from collections import Counter, defaultdict

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", ".tox", ".nox",
             ".venv", "venv", "env", "node_modules", "site-packages", ".eggs"}
TEST_DIRS = {"tests", "test", "testing", "testdata", "test_data"}
HARNESS_FILES = {"conftest.py", "setup.py", "noxfile.py"}
MAX_FILES = 20000
MAX_BYTES = 1_500_000
BM25_W = float(os.environ.get("LOCATE_BM25_W", "0.7"))

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_BACKTICK = re.compile(r"`{1,3}([^`]{1,400})`{1,3}")
_DOTTED = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_PYPATH = re.compile(r"[\w./\\-]*\w\.py\b")
_FRAME = re.compile(r'File "([^"]+\.py)", line (\d+), in (\w+)')
_ERRLINE = re.compile(r"\b(\w*(?:Error|Exception|Warning|Exit))\b:?\s*(.*)")
_QUOTED = re.compile(r"""(?<![\w\\])(["'])([^"'\n]{12,160})\1""")

STOP = set("""
a an the and or but if then else of to in on for with without by from as at is are was were be been being this that
these those it its we you i he she they them our your their not no yes do does did done can could should would will
may might must have has had there here when where which who what why how all any some such than too very just also
only into out up down over under again further once more most other same so pr fix fixes fixed issue issues add
added adds adding update updated use used uses using support new now see https http github com www self cls none
true false return def class import from print example expected actual behavior behaviour error errors exception
traceback file line lines code python version versions following work works working like want would get gets got
make makes made way case cases thing something value values problem bug bugs think seems seem currently instead
because however still even though since already well possible able need needs needed when while after before
default note string strings type types function functions method methods object objects call calls called result
results test tests run running item items name names data list dict none set sets args kwargs param params option
options description reproduce steps output input current proposal feature request user users env environment
""".split())
GENERIC_PATH = {"py", "init", "main", "utils", "util", "src", "lib", "core", "base", "common", "helpers", "__init__"}


def split_ident(tok):
    out = []
    for p in tok.split("_"):
        if p:
            out.extend(x.lower() for x in _CAMEL.sub(" ", p).split() if x)
    return out


def repo_root(arg):
    cands = [arg, os.environ.get("SWE_WORKSPACE"), "/workspace", os.environ.get("PWD"), os.getcwd()]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, ".git")):
            return c
    for c in cands:
        if c and os.path.isdir(c) and c != "/":
            return c
    return "."


def is_test_path(rel):
    parts = rel.split("/")
    fn = parts[-1]
    return (any(p in TEST_DIRS for p in parts[:-1]) or fn.startswith("test_") or fn.endswith("_test.py")
            or fn == "conftest.py" or fn.endswith("_tests.py"))


def iter_py(root):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(".py") and not fn.startswith(".adk_exec_"):
                full = os.path.join(dirpath, fn)
                yield os.path.relpath(full, root).replace(os.sep, "/"), full
                n += 1
                if n >= MAX_FILES:
                    return


# ----------------------------------------------------------------------------------------------- terms
def extract_terms(text):
    """Return {term: (kind, weight)}. kind: 'ident' (full identifier), 'word' (sub-token), 'phrase', 'path'."""
    terms = {}

    def add(t, kind, w):
        key = (t if kind in ("phrase", "path") else t.lower())
        if not key or (kind != "phrase" and len(key) < 3):
            return
        if kind in ("ident", "word") and key in STOP:
            return
        old = terms.get((key, kind))
        if old is None or old < w:
            terms[(key, kind)] = w

    # traceback frames: strongest evidence
    for path, _line, func in _FRAME.findall(text):
        add(path.replace("\\", "/"), "path", 3.0)
        if func != "<module>":
            add(func, "ident", 2.5)
    # explicit .py paths
    for p in _PYPATH.findall(text):
        add(p.replace("\\", "/").lstrip("./"), "path", 2.5)
    # backtick code spans
    for span in _BACKTICK.findall(text):
        for d in _DOTTED.findall(span):
            for comp in d.split("."):
                add(comp, "ident", 2.0)
        for w in _IDENT.findall(span):
            add(w, "ident", 2.0 if (len(w) > 3 and not w.islower() or "_" in w) else 1.6)
    # dotted names anywhere (module.Class.method)
    for d in _DOTTED.findall(text):
        if re.fullmatch(r"[\d.]+", d) or d.lower().startswith(("www.", "github.")) or d.endswith((".com", ".org", ".io", ".html")):
            continue
        comps = d.split(".")
        for c in comps:
            add(c, "ident", 1.6)
            if 2 <= len(c) and c.islower():
                terms[(c, "part")] = max(terms.get((c, "part"), 0), 1.0)
        if len(comps) >= 2:
            add("/".join(comps[:-1]), "path", 1.0)
            add("/".join(comps), "path", 1.0)
    # identifiers that look like code
    for w in _IDENT.findall(text):
        if "_" in w.strip("_") or re.search(r"[a-z][A-Z]", w) or re.fullmatch(r"[A-Z][a-z]+[A-Z]\w*", w):
            add(w, "ident", 1.5)
        elif re.fullmatch(r"[A-Z][a-z0-9]{3,}", w):
            add(w, "ident", 0.6)          # CapWord: maybe a class, maybe sentence start
        elif len(w) >= 4 and w.islower():
            add(w, "word", 0.35)
    # error messages / quoted literals -> phrase search
    for m in _ERRLINE.finditer(text):
        add(m.group(1), "ident", 1.8)
        for frag in re.split(r"[\"'{}()\[\]<>]|\d+|0x[0-9a-f]+", m.group(2)):
            frag = frag.strip(" .,:;")
            if len(frag) >= 12 and " " in frag:
                add(frag[:80], "phrase", 2.0)
    for _q, s in _QUOTED.findall(text):
        s = s.strip()
        if " " in s and not s.startswith(("http", "pip ")):
            for frag in re.split(r"[{}()\[\]<>%]|\d+", s):
                frag = frag.strip(" .,:;")
                if len(frag) >= 12 and " " in frag:
                    add(frag[:80], "phrase", 1.5)
    # sub-tokens of identifiers as words (low weight) so 'timeout' finds 'read_timeout'
    for (t, kind), w in list(terms.items()):
        if kind == "ident":
            for s in split_ident(t):
                if len(s) >= 4 and s not in STOP:
                    add(s, "word", 0.3)
    return terms


# ----------------------------------------------------------------------------------------------- index
def index_repo(root):
    files = {}
    for rel, full in iter_py(root):
        if rel.split("/")[-1] in ("setup.py", "noxfile.py") or rel.startswith(("docs/", "doc/", "examples/", "benchmarks/")):
            continue
        try:
            if os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue
        idents = _IDENT.findall(src)
        full_c = Counter(w.lower() for w in idents)
        sub_c = Counter()
        for w, c in full_c.items():
            for s in set(split_ident(w)) | {w}:
                sub_c[s] += c
        defs = set(m.lower() for m in re.findall(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", src, re.M))
        files[rel] = {"src": src, "full": full_c, "sub": sub_c, "defs": defs, "test": is_test_path(rel)}
    return files


def score_files(files, terms, hints_paths):
    src_files = [r for r, d in files.items() if not d["test"]] or list(files)
    n = len(src_files)
    df = {}
    for (t, kind) in terms:
        if kind == "ident":
            df[(t, kind)] = sum(1 for r in src_files if t in files[r]["full"])
        elif kind == "word":
            df[(t, kind)] = sum(1 for r in src_files if t in files[r]["sub"])
        elif kind == "phrase":
            tl = t.lower()
            df[(t, kind)] = sum(1 for r in src_files if tl in files[r]["src"].lower())
    # drop terms that match nothing; cap very common ones
    live = {k: w for k, w in terms.items() if k[1] in ("path", "part") or df.get(k, 0) > 0}
    scores, why = {}, {}
    for rel in files:
        d = files[rel]
        s = 0.0
        hits = []
        stem_parts = [p for p in re.split(r"[/_.]", rel[:-3].lower()) if p and p not in GENERIC_PATH]
        for (t, kind), w in live.items():
            if kind == "part":
                if t in rel.lower()[:-3].split("/"):
                    s += 2.0 * w
                    hits.append(t)
                continue
            if kind == "path":
                tl = t.lower().strip("/")
                if tl and (rel.lower().endswith(tl) or rel.lower().endswith(tl + ".py") or
                           rel.lower().endswith(tl + "/__init__.py")):
                    s += 4.0 * w
                    hits.append(t)
                continue
            k = df[(t, kind)]
            idf = math.log(1.0 + n / k)
            if kind == "ident":
                tf = d["full"].get(t, 0)
            elif kind == "word":
                tf = d["sub"].get(t, 0)
            else:
                tf = d["src"].lower().count(t.lower())
            if tf:
                s += w * idf * (1.0 + math.log(tf))
                hits.append(t)
                if kind in ("ident", "word") and t in d["defs"]:
                    s += w * idf * (1.5 if kind == "ident" else 0.5)
            if kind in ("ident", "word") and t in stem_parts:
                s += w * idf * 0.8
        for h in hints_paths:
            if h and rel.endswith(h):
                s += 10.0
        if s > 0:
            # mild length normalisation: huge files match everything
            lines = d["src"].count("\n") + 1
            s /= 1.0 + 0.15 * max(0.0, math.log(lines / 400.0))
            scores[rel] = s
            why[rel] = hits
    return scores, why, live


# ----------------------------------------------------------------------------------------------- defs
def enclosing_defs(src):
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError):
        return []
    out = []
    stack = [(tree, "")]
    while stack:
        node, prefix = stack.pop()
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{ch.name}" if prefix else ch.name
                start = min([ch.lineno] + [x.lineno for x in ch.decorator_list])
                out.append((q, ch, start, ch.end_lineno or ch.lineno))
                stack.append((ch, q))
            elif not isinstance(ch, ast.Lambda):
                stack.append((ch, prefix))
    return out


def signature(lines, node):
    i = node.lineno - 1
    sig = lines[i].strip()
    j = i
    while not sig.rstrip().endswith(":") and j < min(len(lines) - 1, i + 6):
        j += 1
        sig += " " + lines[j].strip()
    sig = re.sub(r"\s+", " ", sig).rstrip(":")
    return sig if len(sig) <= 110 else sig[:107] + "..."


def rank_defs(src, live):
    lines = src.splitlines()
    defs = enclosing_defs(src)
    pats = []
    for (t, kind), w in live.items():
        if kind == "ident":
            pats.append((re.compile(r"\b" + re.escape(t) + r"\b", re.I), w, t))
        elif kind == "word":
            pats.append((re.compile(re.escape(t), re.I), w * 0.6, t))
        elif kind == "phrase":
            pats.append((re.compile(re.escape(t), re.I), w * 1.5, t))
    line_score = {}
    for i, ln in enumerate(lines, 1):
        sc = 0.0
        for p, w, _t in pats:
            if p.search(ln):
                sc += w
        if sc:
            line_score[i] = sc
    # innermost def for each line
    owner = {}
    for q, node, s, e in sorted(defs, key=lambda x: x[3] - x[2], reverse=True):
        for i in range(s, e + 1):
            owner[i] = (q, node, s, e)
    agg = defaultdict(lambda: [0.0, []])
    for i, sc in line_score.items():
        key = owner.get(i)
        if key is None:
            continue
        agg[(key[0], key[2])][0] += sc
        agg[(key[0], key[2])][1].append(i)
    info = {(q, s): (node, s, e) for q, node, s, e in defs}  # keyed by start: @overload defs share a qualname
    ranked = []
    for (q, _s0), (sc, ls) in agg.items():
        node, s, e = info[(q, _s0)]
        name_l = q.rsplit(".", 1)[-1].lower()
        bonus = sum(w * 2 for (t, kind), w in live.items() if kind == "ident" and t == name_l)
        if any(getattr(d, "id", getattr(d, "attr", "")) == "overload" for d in getattr(node, "decorator_list", [])):
            sc, bonus = sc * 0.3, bonus * 0.3   # typing stub; prefer the real implementation
        ranked.append((sc + bonus, q, s, e, signature(lines, node), sorted(ls)))
    ranked.sort(key=lambda x: (-x[0], x[2]))
    return ranked


# ----------------------------------------------------------------------------------------------- bm25
BM25_STOP = set("""a an the and or but if then else of to in on for with without by from as at is are was were be been
being this that these those it its we you he she they them our your their not no yes do does did done can could should
would will may might must have has had there here when where which who what why how all any some such than too very
just also only into out up down over under again further once more most other same so pr fix fixes fixed issue issues
add added adds adding update updated use used uses using support new now see https http github com www self cls none
true false return def class import merge""".split())


def bm25_tokens(text):
    out = []
    for w in _IDENT.findall(text):
        subs = split_ident(w)
        if len(subs) > 1:
            out.append(w.lower())
        out.extend(subs)
    return [t for t in out if len(t) > 1 and t not in BM25_STOP and not t.isdigit()]


def bm25_files(files, query, rels):
    """Max over definitions of BM25(def name x3 + body + path tokens); returns {rel: score}."""
    docs, owner = [], []
    for rel in rels:
        src = files[rel]["src"]
        ptoks = bm25_tokens(rel[:-3].replace("/", " "))
        try:
            defs = enclosing_defs(src)
        except RecursionError:
            defs = []
        lines = src.splitlines()
        if not defs:
            docs.append(bm25_tokens(src[:20000]) + ptoks)
            owner.append(rel)
            continue
        for q, _node, s, e in defs:
            name = [t for comp in q.split(".") for t in split_ident(comp) + [comp.lower()]]
            body = "\n".join(lines[s - 1:min(e, s + 120)])
            docs.append(name * 3 + bm25_tokens(body) + ptoks)
            owner.append(rel)
    if not docs:
        return {}
    n = len(docs)
    avgdl = sum(map(len, docs)) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    qt = Counter(bm25_tokens(query))
    best = {}
    for d, rel in zip(docs, owner):
        tf = Counter(d)
        sc = 0.0
        for t, qtf in qt.items():
            f = tf.get(t)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                sc += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / avgdl)) * min(qtf, 3)
        if sc > best.get(rel, 0.0):
            best[rel] = sc
    return best


# ----------------------------------------------------------------------------------------------- main
def main():
    warnings.simplefilter("ignore")
    ap = argparse.ArgumentParser(add_help=False)
    for name in ("--issue", "--query", "--text", "--keywords", "--hints", "--root", "--k", "--files"):
        ap.add_argument(name, default=None)
    a, rest = ap.parse_known_args()
    text = " ".join(x for x in (a.issue, a.query, a.text, a.keywords, a.hints) if x)
    text = (text + " " + " ".join(r for r in rest if r != "--")).strip()
    if not text:
        print("usage: run_skill_script(skill_name='repo-locate', file_path='scripts/locate.py', "
              "args={'issue': '<issue text, identifiers, error message>'})")
        return
    k = 6
    try:
        k = max(1, min(10, int(a.k or a.files or 6)))
    except ValueError:
        pass
    root = repo_root(a.root)
    terms = extract_terms(text)
    hints_paths = [p.replace("\\", "/").lstrip("./") for p in _PYPATH.findall(a.hints or "")]
    files = index_repo(root)
    if not files:
        print(f"No Python files found under {root}.")
        return
    scores, why, live = score_files(files, terms, hints_paths)
    # fuse with BM25 over definitions (robust when the issue names no identifiers)
    srcs = [r for r in files if not files[r]["test"]]
    bm = bm25_files(files, text, srcs)
    m1 = max([scores[r] for r in srcs if r in scores] or [0.0]) or 1.0
    m2 = max(bm.values() or [0.0]) or 1.0
    for r in srcs:
        if r in scores or r in bm:
            scores[r] = scores.get(r, 0.0) / m1 + BM25_W * bm.get(r, 0.0) / m2
            why.setdefault(r, [])
    src_rank = sorted((r for r in scores if not files[r]["test"]), key=lambda r: (-scores[r], r))
    test_rank = sorted((r for r in scores if files[r]["test"]), key=lambda r: (-scores[r], r))
    best_w = {}
    for (t, kind), w in live.items():
        if kind in ("ident", "phrase", "path") and "/" not in t:
            best_w[t.lower()] = max(best_w.get(t.lower(), 0.0), w)
    shown_terms = sorted(best_w, key=lambda t: (-best_w[t], t))[:12]
    out = [f"Candidate locations (repo {root}; terms: {', '.join(shown_terms) or 'plain words only'})"]
    if not src_rank:
        out.append("No source file matches the issue terms. Search manually with grep -rn on key words.")
    for n, rel in enumerate(src_rank[:k], 1):
        h = why[rel]
        hs = ", ".join(sorted(sorted(set(h)), key=lambda t: -live.get((t, "ident"), live.get((t, "phrase"), 0)))[:5])
        out.append(f"{n}. {rel}  (score {scores[rel]:.1f}; matches: {hs})")
        ndefs = 3 if n <= 2 else (2 if n <= 4 else 1)
        for sc, q, s, e, sig, ls in rank_defs(files[rel]["src"], live)[:ndefs]:
            hl = ",".join(str(x) for x in ls[:4]) + ("..." if len(ls) > 4 else "")
            out.append(f"   L{s}-{e} {q}: {sig}   [hit lines {hl}]")
    if len(src_rank) > k:
        out.append("Also: " + ", ".join(src_rank[k:k + 4]))
    if test_rank:
        out.append("Tests: " + ", ".join(test_rank[:3]))
    out.append("Next: read only the top 1-2 ranges above (sed -n 'START,ENDp' FILE), then confirm.")
    print("\n".join(out[:62]))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never crash the agent's turn
        print(f"locate.py failed ({type(e).__name__}: {e}); fall back to grep -rn.")
        sys.exit(0)
