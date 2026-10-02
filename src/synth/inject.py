"""B5 step 1: unpack non-eval pure-Python packages from /wheels, build graphs, inject bugs.

Each sample: one function (graph node) mutated by one operator at one site. Only the function's
source span is replaced (ast.unparse of the mutated function, re-indented), so the diff is local.
Output: data/derived/synth/<pkg>/{src/, graph.json} and data/derived/synth_mutations.jsonl
Usage: .venv/bin/python -m src.synth.inject [--per-pkg 80] [--seed 0]
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import random
import re
import textwrap
import zipfile
from pathlib import Path

from src.dataio.loaders import DATA
from src.graphbuild.build import build_graph, module_name

SYNTH = DATA / "derived" / "synth"
PACKAGES = ["starlette", "pydantic", "urllib3", "httpcore", "anyio", "click", "flask", "werkzeug", "jinja2",
            "sqlalchemy", "sqlmodel", "typer", "pygments", "markdown_it_py", "packaging", "pluggy", "tqdm", "idna",
            "itsdangerous", "hatchling", "poetry_core", "pytest"]
CMP_FLIP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
            ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
EXC_SWAP = {"ValueError": "TypeError", "TypeError": "ValueError", "KeyError": "IndexError", "IndexError": "KeyError",
            "RuntimeError": "ValueError", "AttributeError": "KeyError", "NotImplementedError": "RuntimeError"}


def latest_wheel(pkg: str) -> Path | None:
    from packaging.version import Version

    cands = []
    for w in (DATA / "wheels").glob("*.whl"):
        name, ver = w.name.split("-")[:2]
        if name.lower().replace("-", "_") == pkg.lower() and ("none-any" in w.name or "cp313" in w.name):
            try:
                cands.append((Version(ver), w))
            except Exception:  # noqa: BLE001
                pass
    return max(cands)[1] if cands else None


# ---------------- mutation operators: each returns list of (site_description, apply_fn) -----------------
def sites(fn: ast.AST):
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP_FLIP:
            out.append(("compare_flip", node))
        elif isinstance(node, ast.BoolOp):
            out.append(("boolop_flip", node))
        elif isinstance(node, ast.If) and not isinstance(node.test, ast.UnaryOp):
            out.append(("negate_if", node))
            t = node.test
            if isinstance(t, ast.Compare) and any(isinstance(o, (ast.Is, ast.IsNot)) for o in t.ops) and \
                    any(isinstance(c, ast.Constant) and c.value is None for c in t.comparators) and not node.orelse:
                out.append(("remove_none_check", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool) \
                and 0 <= node.value <= 64:
            out.append(("off_by_one", node))
        elif isinstance(node, ast.Call):
            if [k for k in node.keywords if k.arg and isinstance(k.value, ast.Name) and k.value.id == k.arg]:
                out.append(("drop_kwarg_passthrough", node))
            if len(node.args) >= 2 and not any(isinstance(a, ast.Starred) for a in node.args[:2]):
                out.append(("swap_args", node))
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name) \
                and node.exc.func.id in EXC_SWAP:
            out.append(("wrong_exception", node))
    args = fn.args
    for d in list(args.defaults) + [x for x in args.kw_defaults if x is not None]:
        if isinstance(d, ast.Constant) and (isinstance(d.value, bool) or isinstance(d.value, int) or d.value is None):
            out.append(("wrong_default", d))
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
    if len(body) >= 3:
        for s in body[:-1]:
            if isinstance(s, (ast.Assign, ast.AugAssign, ast.Expr)):
                out.append(("drop_statement", s))
    return out


def apply(kind: str, node, fn: ast.AST, rng: random.Random) -> bool:
    if kind == "compare_flip":
        node.ops[0] = CMP_FLIP[type(node.ops[0])]()
    elif kind == "boolop_flip":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif kind == "negate_if":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif kind == "remove_none_check":
        node.body = [ast.Pass()]
    elif kind == "off_by_one":
        node.value = node.value + (1 if node.value == 0 or rng.random() < 0.5 else -1)
    elif kind == "drop_kwarg_passthrough":
        ks = [k for k in node.keywords if k.arg and isinstance(k.value, ast.Name) and k.value.id == k.arg]
        node.keywords.remove(rng.choice(ks))
    elif kind == "swap_args":
        node.args[0], node.args[1] = node.args[1], node.args[0]
    elif kind == "wrong_exception":
        node.exc.func.id = EXC_SWAP[node.exc.func.id]
    elif kind == "wrong_default":
        v = node.value
        node.value = (not v) if isinstance(v, bool) else (v + 1 if isinstance(v, int) else False)
    elif kind == "drop_statement":
        for parent in ast.walk(fn):
            for field in ("body", "orelse", "finalbody"):
                lst = getattr(parent, field, None)
                if isinstance(lst, list) and node in lst:
                    lst.remove(node)
                    if not lst:
                        lst.append(ast.Pass())
                    return True
        return False
    return True


def mutate_function(src: str, fn: ast.AST, rng: random.Random) -> tuple[str, str, str] | None:
    """Return (kind, original_text, mutated_text) for one random applicable mutation."""
    fn2 = copy.deepcopy(fn)
    cands = sites(fn2)
    if not cands:
        return None
    kind, node = rng.choice(cands)
    if not apply(kind, node, fn2, rng):
        return None
    ast.fix_missing_locations(fn2)
    try:
        orig = ast.unparse(fn)
        new = ast.unparse(fn2)
    except Exception:  # noqa: BLE001
        return None
    if orig == new:
        return None
    return kind, orig, new


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-pkg", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    rows = []
    for pkg in PACKAGES:
        whl = latest_wheel(pkg)
        if not whl:
            print("no wheel for", pkg)
            continue
        root = SYNTH / pkg / "src"
        if not root.exists():
            root.mkdir(parents=True)
            with zipfile.ZipFile(whl) as z:
                for m in z.namelist():
                    if m.endswith(".py") and ".dist-info/" not in m and ".data/" not in m:
                        z.extract(m, root)
        graph = build_graph(root, f"{pkg}_{whl.name.split('-')[1]}")
        (SYNTH / pkg / "graph.json").write_text(json.dumps(graph))
        names = {n["name"] for n in graph["nodes"]}
        # candidate functions: non-test, >= 3 lines, defined at module/class level
        funcs = []
        for py in sorted(root.rglob("*.py")):
            rel = py.relative_to(root).as_posix()
            if "/tests/" in "/" + rel or "/testing/" in "/" + rel or "vendor" in rel:
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(src)
            except (SyntaxError, ValueError):
                continue
            mod = module_name(rel)
            stack = [(tree, mod)]
            while stack:
                node, prefix = stack.pop()
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, ast.ClassDef):
                        stack.append((ch, f"{prefix}.{ch.name}"))
                    elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        q = f"{prefix}.{ch.name}"
                        if q in names and ch.end_lineno - ch.lineno >= 3:
                            funcs.append((rel, src, ch, q))
        rng.shuffle(funcs)
        kept = 0
        for rel, src, fn, q in funcs:
            if kept >= a.per_pkg:
                break
            m = mutate_function(src, fn, rng)
            if not m:
                continue
            kind, orig, new = m
            lines = src.splitlines()
            start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
            indent = re.match(r"\s*", lines[fn.lineno - 1]).group(0)
            new_src = "\n".join(lines[: start - 1] + textwrap.indent(new, indent).splitlines() + lines[fn.end_lineno:]) + "\n"
            try:
                ast.parse(new_src)
            except SyntaxError:
                continue
            rows.append({"instance_id": f"synth_{pkg}_{kept:03d}", "package": pkg, "wheel": whl.name, "file": rel,
                         "target_nodes": [q], "mutation": kind, "original": orig, "mutated": new,
                         "graph": f"synth/{pkg}/graph.json"})
            kept += 1
        print(f"{pkg:14} nodes={len(graph['nodes']):5d} edges={len(graph['edges']):5d} candidates={len(funcs):5d} mutations={kept}")
    out = DATA / "derived" / "synth_mutations.jsonl"
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from collections import Counter

    print(f"total {len(rows)} -> {out}; by kind {dict(Counter(r['mutation'] for r in rows))}")


if __name__ == "__main__":
    main()
