"""graph-locate: graph-expanded, learned-reranked function localizer. Pure stdlib (runs in the eval sandbox).

Usage: graph_locate.py <issue_text_file | -> [--root /workspace] [--k 10] [--budget 8]

Pipeline
  (a) function-level BM25 (name, class, path, docstring, body identifiers) + exact identifier / traceback / file-name
      hits from the issue -> a seed pool of S functions;
  (b) AST def/call/sibling graph of the repo (tests/venvs/.git skipped);
  (c) sequential frontier expansion: B times pick one frontier node (policy = linear score, weights learned by
      REINFORCE) and reveal its callees / callers / same-class / same-module neighbours;
  (d) rerank all revealed nodes with a learned scorer (linear LambdaRank or small GBDT trees; weights.json).
"""
import ast
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", ".tox", ".nox", ".venv", "venv",
             "env", "node_modules", "site-packages", ".eggs"}
TEST_DIRS = {"tests", "test", "testing", "testdata", "test_data"}
PERIPH = {"docs", "doc", "docs_src", "examples", "example", "scripts", "benchmarks", "tools", "bench"}
MAX_BYTES = 1_200_000
POOL = 20
KW = set("""False None True and as assert async await break class continue def del elif else except finally for from
global if import in is lambda nonlocal not or pass raise return try while with yield self cls""".split())
STOP = set("""a an the and or but if then else of to in on for with without by from as at is are was were be been being this
that these those it its we you i he she they them our your their not no yes do does did done can could should would will
may might must have has had there here when where which who what why how all any some such than too very just also only
into out up down over under again more most other same so pr fix fixes fixed issue issues add added adds adding update
updated use used uses using support new now see https http github com www self cls none true false return def class
import print example expected actual behavior behaviour error errors exception traceback file line lines code python
version following work works working like want get gets got make makes made way case cases thing something value values
problem bug bugs think seems seem currently instead because however still even though since already possible able need
needs needed while after before default note string strings type types function functions method methods object objects
call calls called result results test tests run running item items name names data list dict set sets args kwargs param
params option options description reproduce steps output input current proposal feature request user users""".split())

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_BACKTICK = re.compile(r"`{1,3}([^`]{1,300})`{1,3}")
_PYPATH = re.compile(r"[\w./\\-]*\w\.py\b")
_FRAME = re.compile(r'File "([^"]+\.py)", line (\d+), in (\w+)')
_FRAME2 = re.compile(r"([\w./-]+\.py):(\d+):? in (\w+)")

FEATURES = ["bm25", "bm25_rank", "name_hit", "cls_hit", "tb", "file_hit", "file_bm25", "overlap", "loglen", "indeg",
            "outdeg", "depth", "private", "dunder", "periph", "nbr_max", "nbr_cnt", "hop1", "hop2", "parent_seed", "nparents", "via_callee",
            "via_caller", "via_sibling", "via_module", "is_seed", "seed_score"]
FI = {n: i for i, n in enumerate(FEATURES)}
NF = len(FEATURES)
STATIC_N = 17  # first 17 are static (query+graph), rest dynamic (expansion state)

HAND_SCORER = {"bm25": 1.0, "bm25_rank": 0.3, "name_hit": 1.0, "cls_hit": 0.3, "tb": 1.5, "file_hit": 0.3,
               "file_bm25": 0.4, "overlap": 0.5, "loglen": 0.0, "indeg": 0.05, "outdeg": 0.0, "depth": -0.05,
               "private": -0.1, "dunder": -0.1, "periph": -0.3, "nbr_max": 0.3, "nbr_cnt": 0.1, "hop1": -0.1, "hop2": -0.25, "parent_seed": 0.35,
               "nparents": 0.1, "via_callee": 0.05, "via_caller": 0.0, "via_sibling": 0.05, "via_module": 0.0,
               "is_seed": 0.0, "seed_score": 0.0}
HAND_POLICY = dict(HAND_SCORER)


def vec(d):
    return [float(d.get(n, 0.0)) for n in FEATURES]


def split_ident(tok):
    out = []
    for p in tok.split("_"):
        if p:
            out.extend(x.lower() for x in _CAMEL.sub(" ", p).split() if x)
    return out


def toks_of(tok):
    """full lowercase identifier + its sub-tokens"""
    sub = split_ident(tok)
    full = tok.lower().strip("_")
    return ([full] if len(sub) > 1 and full else []) + sub


# ----------------------------------------------------------------------------------------------- index
class Node:
    __slots__ = ("id", "file", "qual", "name", "cls", "start", "end", "sig", "doc", "tf", "dl", "calls", "callees",
                 "callers", "sib", "mod", "depth", "periph", "bm25", "idx")


def is_test_path(rel):
    parts = rel.split("/")
    fn = parts[-1]
    return any(p in TEST_DIRS for p in parts[:-1]) or fn.startswith("test_") or fn.endswith("_test.py") or fn == "conftest.py"


def iter_py(root, deadline):
    for dp, dns, fns in os.walk(root):
        rel = os.path.relpath(dp, root)
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.endswith(".egg-info") and not d.startswith("."))
        for fn in sorted(fns):
            if fn.endswith(".py"):
                r = os.path.normpath(os.path.join(rel, fn)).replace(os.sep, "/")
                if not is_test_path(r):
                    yield r
        if time.time() > deadline:
            return


def defs_of(tree):
    """yield (qualname, cls, node) for top-level functions and methods (nested defs are folded into their parent)"""
    stack = [("", None, tree.body)]
    while stack:
        pre, cls, body = stack.pop()
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield (pre + n.name, cls, n)
            elif isinstance(n, ast.ClassDef):
                stack.append((pre + n.name + ".", n.name, n.body))
            elif isinstance(n, (ast.If, ast.Try, ast.With)):
                stack.append((pre, cls, n.body + getattr(n, "orelse", []) + getattr(n, "finalbody", [])))


class Index:
    pass


def build_index(root, time_budget=14.0):
    t0 = time.time()
    deadline = t0 + time_budget
    nodes, byfile, imports = [], defaultdict(list), {}
    for rel in iter_py(root, deadline):
        p = os.path.join(root, rel)
        try:
            if os.path.getsize(p) > MAX_BYTES:
                continue
            src = open(p, encoding="utf-8", errors="replace").read()
            tree = ast.parse(src)
        except Exception:
            continue
        lines = src.split("\n")
        parts = rel.split("/")
        imp = {}
        for n in tree.body:
            if isinstance(n, ast.ImportFrom) and n.module is not None or isinstance(n, ast.ImportFrom):
                for a in n.names:
                    imp[a.asname or a.name] = ((n.module or ""), n.level)
        imports[rel] = imp
        stem = [t for t in split_ident(os.path.splitext(parts[-1])[0]) if t not in ("init",)]
        for qual, cls, fn in defs_of(tree):
            nd = Node()
            nd.id = len(nodes)
            nd.file, nd.qual, nd.name, nd.cls = rel, qual, fn.name, cls
            st = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
            nd.start, nd.end = st, getattr(fn, "end_lineno", fn.lineno)
            nd.sig = lines[fn.lineno - 1].strip()[:110] if fn.lineno - 1 < len(lines) else ""
            nd.doc = (ast.get_docstring(fn) or "")[:400]
            body = "\n".join(lines[st - 1:min(nd.end, st + 400)])[:7000]
            tf = Counter()
            for m in _IDENT.findall(body):
                if m in KW:
                    continue
                for t in toks_of(m):
                    tf[t] += 1
            for t in toks_of(fn.name):
                tf[t] += 3
            if cls:
                for t in toks_of(cls):
                    tf[t] += 1
            for t in stem:
                tf[t] += 1
            for t in re.findall(r"[a-z]{4,}", nd.doc.lower()):
                tf[t] += 1
            nd.tf = tf
            nd.dl = sum(tf.values())
            nd.calls = set(m for m in _CALL.findall(body) if m not in KW and m != fn.name)
            nd.callees, nd.callers, nd.sib, nd.mod = [], [], [], []
            nd.depth = len(parts) - 1
            nd.periph = 1.0 if parts[0] in PERIPH else 0.0
            nd.bm25 = 0.0
            nodes.append(nd)
            byfile[rel].append(nd)
    ix = Index()
    ix.nodes, ix.byfile, ix.root = nodes, byfile, root
    N = len(nodes)
    ix.avgdl = (sum(n.dl for n in nodes) / N) if N else 1.0
    post = defaultdict(list)
    for n in nodes:
        for t, c in n.tf.items():
            post[t].append((n.id, c))
    ix.post = post
    byname = defaultdict(list)
    for n in nodes:
        byname[n.name].append(n.id)
    clsinit = defaultdict(list)
    for n in nodes:
        if n.name == "__init__" and n.cls:
            clsinit[n.cls].append(n.id)
    ix.byname = byname
    # call graph
    modfile = defaultdict(set)
    for rel in byfile:
        mod = rel[:-3].replace("/", ".")
        ps = mod.split(".")
        for i in range(len(ps)):
            modfile[".".join(ps[i:])].add(rel)
    for n in nodes:
        imp = imports.get(n.file, {})
        out = []
        for c in n.calls:
            cands = list(byname.get(c, ())) + (clsinit.get(c, []) if c not in byname else [])
            cands = [x for x in cands if x != n.id]
            if not cands:
                continue
            if len(cands) > 1:
                pref = [x for x in cands if nodes[x].file == n.file]
                if not pref and c in imp:
                    mod = imp[c][0]
                    files = modfile.get(mod, set()) if mod else set()
                    pref = [x for x in cands if nodes[x].file in files]
                cands = pref or (cands if len(cands) <= 4 else [])
            out.extend(cands[:4])
        n.callees = list(dict.fromkeys(out))
    for n in nodes:
        for c in n.callees:
            nodes[c].callers.append(n.id)
    # siblings / same-module neighbours
    for rel, ns in byfile.items():
        ns.sort(key=lambda x: x.start)
        for i, n in enumerate(ns):
            same = [m for m in ns if m is not n and m.cls == n.cls and n.cls]
            same.sort(key=lambda m: abs(m.start - n.start))
            n.sib = [m.id for m in same[:6]]
            other = sorted((m for m in ns if m is not n and (m.cls != n.cls or not n.cls)), key=lambda m: abs(m.start - n.start))
            n.mod = [m.id for m in other[:4]]
    ix.build_time = time.time() - t0
    ix.idx = None
    return ix


# ----------------------------------------------------------------------------------------------- query
def parse_issue(text):
    text = text[:30000]
    q = {"strong": set(), "plain": set(), "frames": [], "paths": set()}
    for m in _FRAME.finditer(text):
        q["frames"].append((m.group(1), m.group(3)))
    for m in _FRAME2.finditer(text):
        q["frames"].append((m.group(1), m.group(3)))
    for m in _PYPATH.finditer(text):
        q["paths"].add(m.group(0).replace("\\", "/").lstrip("./"))
    bt = " ".join(_BACKTICK.findall(text))
    for m in _IDENT.finditer(bt):
        if m.group(0) not in KW and len(m.group(0)) > 2:
            q["strong"].add(m.group(0))
    for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", text):
        w = m.group(0)
        if len(w) < 3 or w in KW:
            continue
        end = m.end()
        code_like = "_" in w.strip("_") or bool(re.search(r"[a-z][A-Z]", w)) or text[end:end + 1] == "(" or (
            w[0].isupper() and any(c.islower() for c in w) and len(w) > 3 and not text[max(0, m.start() - 2):m.start()].endswith(". "))
        if code_like and w.lower() not in STOP:
            q["strong"].add(w)
        elif w.lower() not in STOP:
            q["plain"].add(w.lower())
    return q


def bm25_scores(ix, q):
    qt = Counter()
    for w in q["strong"]:
        for t in toks_of(w):
            qt[t] += 2.0 if t == w.lower() or len(toks_of(w)) == 1 else 1.0
    for w in q["plain"]:
        qt[w] += 1.0
    N = len(ix.nodes)
    sc = defaultdict(float)
    k1, b = 1.2, 0.75
    for t, w in qt.items():
        p = ix.post.get(t)
        if not p:
            continue
        idf = math.log(1 + (N - len(p) + 0.5) / (len(p) + 0.5))
        if len(p) > 0.3 * N:
            continue
        for nid, c in p:
            dl = ix.nodes[nid].dl
            sc[nid] += w * idf * c * (k1 + 1) / (c + k1 * (1 - b + b * dl / ix.avgdl))
    return sc, qt


class Query:
    """per-issue static features for every node that has any signal (others default to zeros)"""

    def __init__(self, ix, text):
        self.ix = ix
        q = parse_issue(text)
        self.q = q
        sc, qt = bm25_scores(ix, q)
        self.qt = qt
        mx = max(sc.values()) if sc else 1.0
        self.bm = {k: v / mx for k, v in sc.items()}
        order = sorted(self.bm, key=lambda k: (-self.bm[k], k))
        self.rank = {k: i for i, k in enumerate(order)}
        fb = defaultdict(list)
        for k, v in self.bm.items():
            fb[ix.nodes[k].file].append(v)
        fbs = {f: sum(sorted(v, reverse=True)[:3]) for f, v in fb.items()}
        m2 = max(fbs.values()) if fbs else 1.0
        self.filebm = {f: v / m2 for f, v in fbs.items()}
        names = {w: 1.0 for w in q["strong"]}
        self.sf = {}
        self.base = {}
        self.seed_score = {}
        qtl = set(qt)
        for nid in list(self.bm) + [i for w in list(q["strong"]) + list(q["plain"]) for i in ix.byname.get(w, [])] + \
                [i for (_, fn) in q["frames"] for i in ix.byname.get(fn, [])]:
            self.static(nid)

    def _base(self, nid):
        b = self.base.get(nid)
        if b is None:
            b = self.base[nid] = self._base0(nid, set(self.qt))
            self.seed_score[nid] = self._seed(b)
        return b

    def _static(self, nid):
        f = list(self._base(nid))
        n = self.ix.nodes[nid]
        nb = n.callees[:20] + n.callers[:20] + n.sib + n.mod
        sc = [self._seed(self._base(m)) for m in nb]
        f.append(max(sc) if sc and max(sc) > 0 else 0.0)
        f.append(min(1.0, math.log1p(sum(1 for x in sc if x > 0.5)) / 2))
        return f

    def _base0(self, nid, qtl):
        ix, q = self.ix, self.q
        n = ix.nodes[nid]
        f = [0.0] * 15
        f[0] = self.bm.get(nid, 0.0)
        f[1] = 1.0 / (1 + self.rank.get(nid, 10 ** 6))
        amb = 1.0 / (1 + math.log2(max(1, len(ix.byname.get(n.name, [])))))
        if n.name in q["strong"] or n.qual in q["strong"]:
            f[2] = amb
        elif n.name.lower() in q["plain"] and len(n.name) > 4:
            f[2] = 0.4 * amb
        if n.cls and n.cls in q["strong"]:
            f[3] = 1.0
        fb = os.path.basename(n.file)
        for (fp, fn) in q["frames"]:
            if fn == n.name:
                f[4] = max(f[4], 1.0 if os.path.basename(fp) == fb else 0.6)
        for p in q["paths"]:
            if n.file == p or n.file.endswith("/" + p) or (os.path.basename(p) == fb and "/" not in p):
                f[5] = 1.0
        f[6] = self.filebm.get(n.file, 0.0)
        if qtl:
            f[7] = sum(1 for t in qtl if t in n.tf) / len(qtl)
        f[8] = min(1.0, math.log(1 + n.end - n.start + 1) / 6)
        f[9] = min(1.0, math.log1p(len(n.callers)) / 3)
        f[10] = min(1.0, math.log1p(len(n.callees)) / 3)
        f[11] = min(1.0, n.depth / 5)
        f[12] = 1.0 if n.name.startswith("_") and not n.name.startswith("__") else 0.0
        f[13] = 1.0 if n.name.startswith("__") else 0.0
        f[14] = n.periph
        return f

    def static(self, nid):
        f = self.sf.get(nid)
        if f is None:
            f = self.sf[nid] = self._static(nid)
        return f

    @staticmethod
    def _seed(f):
        return f[0] + 1.0 * f[2] + 0.5 * f[3] + 1.5 * f[4] + 0.3 * f[5] + 0.2 * f[6] - 0.2 * f[14]

    def seeds(self, S=POOL):
        for nid in list(self.bm):
            self._base(nid)
        cand = sorted(self.seed_score, key=lambda k: (-self.seed_score[k], k))
        return cand[:S]


# ----------------------------------------------------------------------------------------------- expansion state
class State:
    def __init__(self, qry, S=POOL):
        self.qry = qry
        self.ix = qry.ix
        self.info = {}  # nid -> dict(hop, par, np, via)
        self.expanded = set()
        for s in qry.seeds(S):
            self.info[s] = {"hop": 0, "par": 0.0, "np": 0, "via": set(), "from": None}

    def feat(self, nid):
        i = self.info[nid]
        f = list(self.qry.static(nid))
        h = i["hop"]
        f += [1.0 if h == 1 else 0.0, 1.0 if h >= 2 else 0.0, i["par"], min(1.0, math.log1p(i["np"]) / 2),
              1.0 if "callee" in i["via"] else 0.0, 1.0 if "caller" in i["via"] else 0.0,
              1.0 if "sibling" in i["via"] else 0.0, 1.0 if "module" in i["via"] else 0.0,
              1.0 if h == 0 else 0.0, self.qry.seed_score.get(nid, 0.0)]
        return f

    def frontier(self):
        return [n for n in self.info if n not in self.expanded]

    def expand(self, nid):
        self.expanded.add(nid)
        ix, qry = self.ix, self.qry
        n = ix.nodes[nid]
        h = self.info[nid]["hop"]
        ps = qry.static(nid) and qry.seed_score.get(nid, 0.0)
        groups = [("callee", sorted(n.callees, key=lambda x: -qry.static(x)[0])[:10]),
                  ("caller", sorted(n.callers, key=lambda x: -qry.static(x)[0])[:10]),
                  ("sibling", n.sib), ("module", n.mod)]
        for via, lst in groups:
            for m in lst:
                if m not in self.info:
                    self.info[m] = {"hop": h + 1, "par": ps, "np": 1, "via": {via}, "from": nid}
                else:
                    i = self.info[m]
                    if m not in self.expanded or True:
                        i["par"] = max(i["par"], ps)
                        i["np"] += 1
                        i["via"].add(via)
                        if i["hop"] > h + 1:
                            i["hop"] = h + 1


def dot(w, f):
    return sum(a * b for a, b in zip(w, f))


def run_budget(qry, B, policy_w, S=POOL, rng=None, collect=None):
    """sequential expansion; policy_w is a feature-weight vector. Greedy argmax unless rng given (softmax sampling)."""
    st = State(qry, S)
    for _ in range(B):
        fr = st.frontier()
        if not fr:
            break
        fs = [st.feat(n) for n in fr]
        sc = [dot(policy_w, f) for f in fs]
        if rng is None:
            j = max(range(len(fr)), key=lambda i: (sc[i], -fr[i]))
        else:
            m = max(sc)
            ps = [math.exp(s - m) for s in sc]
            z = sum(ps)
            ps = [p / z for p in ps]
            r, c, j = rng.random(), 0.0, len(ps) - 1
            for i, p in enumerate(ps):
                c += p
                if r <= c:
                    j = i
                    break
            if collect is not None:
                collect.append((fs, ps, j))
        st.expand(fr[j])
    return st


# ----------------------------------------------------------------------------------------------- scorer
def tree_eval(tree, f):
    while "leaf_value" not in tree:
        v = f[tree["split_feature"]]
        if v != v:
            go_left = tree.get("default_left", True)
        else:
            go_left = v <= tree["threshold"]
        tree = tree["left_child"] if go_left else tree["right_child"]
    return tree["leaf_value"]


class Scorer:
    def __init__(self, spec=None):
        spec = spec or {"type": "linear", "w": vec(HAND_SCORER)}
        self.spec = spec

    def __call__(self, f):
        s = self.spec
        if s["type"] == "linear":
            return dot(s["w"], f)
        return sum(tree_eval(t, f) for t in s["trees"])


def rank_state(st, scorer, k=None):
    out = sorted(((scorer(st.feat(n)), n) for n in st.info), key=lambda x: (-x[0], x[1]))
    return out[:k] if k else out


def load_weights(path=None):
    for p in ([path] if path else [os.path.join(HERE, "weights.json"), os.path.join(HERE, "..", "weights.json")]):
        try:
            return json.load(open(p))
        except Exception:
            continue
    return {}


def why(st, nid, score):
    f = st.feat(nid)
    r = []
    if f[FI["tb"]] > 0:
        r.append("traceback")
    if f[FI["name_hit"]] > 0.3:
        r.append("name-in-issue")
    if f[FI["cls_hit"]] > 0:
        r.append("class-in-issue")
    if f[FI["file_hit"]] > 0:
        r.append("file-in-issue")
    r.append("bm25=%.2f" % f[0])
    i = st.info[nid]
    if i["hop"] > 0 and i["from"] is not None:
        p = st.ix.nodes[i["from"]]
        r.append("%s of %s" % (sorted(i["via"])[0], p.qual))
    return ", ".join(r)


def _find_root():
    # Kaggle scorer (docker): /workspace. Local subprocess sandbox: the skill runner chdirs to a temp dir, but bash's
    # $PWD and $PYTHONPATH still point at the repo. Prefer a candidate that is a git checkout.
    cands = [os.environ.get("SWE_WORKSPACE"), "/workspace", os.environ.get("PWD")]
    cands += os.environ.get("PYTHONPATH", "").split(os.pathsep) + [os.getcwd()]
    cands = [c for c in cands if c and os.path.isdir(c)]
    for c in cands:
        if os.path.isdir(os.path.join(c, ".git")):
            return os.path.abspath(c)
    return os.path.abspath(cands[0]) if cands else "."


def _tmp(path):
    # "/tmp/x" as the agent's shell sees it: real /tmp in the scorer container, $TMPDIR in the local sandbox.
    if os.path.isdir("/workspace") or not path.startswith("/tmp"):
        return path
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", path[len("/tmp"):].lstrip("/"))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("issue_file", nargs="?", default=None, help="issue text file, or - for stdin")
    ap.add_argument("--issue", default=None, help="issue text given inline (run_skill_script passes key 'issue' as --issue)")
    ap.add_argument("--root", default=None)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--budget", type=int, default=8)
    ap.add_argument("--weights", default=None)
    a = ap.parse_args(argv)
    if a.issue is not None:
        text = a.issue
    elif a.issue_file in (None, "-"):
        text = sys.stdin.read()
    else:
        text = open(a.issue_file, encoding="utf-8", errors="replace").read()
    root = a.root or _find_root()
    ix = build_index(root)
    if not ix.nodes:
        print("graph-locate: no python functions indexed under %s" % root)
        return
    W = load_weights(a.weights)
    scorer = Scorer(W.get("scorer"))
    pol = W.get("policy", {}).get("w") or vec(HAND_POLICY)
    qry = Query(ix, text)
    st = run_budget(qry, a.budget, pol)
    ranked = rank_state(st, scorer, a.k)
    files = []
    for s, n in ranked:
        f = ix.nodes[n].file
        if f not in files:
            files.append(f)
    print("graph-locate: %d functions indexed in %.1fs, %d nodes reached with %d expansions. Candidates, best first:" % (
        len(ix.nodes), ix.build_time, len(st.info), len(st.expanded)))
    for i, (s, n) in enumerate(ranked, 1):
        nd = ix.nodes[n]
        print("%d. %s:%s (lines %d-%d) %.2f  %s" % (i, nd.file, nd.qual, nd.start, nd.end, s, why(st, n, s)))
    print("Files in order: " + ", ".join(files[:6]))
    print("Read the top 1-2 ranges with sed -n 'A,Bp' FILE; verify the code before editing. Do not re-run with the same text.")


if __name__ == "__main__":
    main()
