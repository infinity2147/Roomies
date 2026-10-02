"""Own AST code graph builder, schema-compatible with the competition graphs.

Schema: {"directed": true, "multigraph": true, "graph": {"repo_name": ...},
         "nodes": [{"id", "name", "text"}], "edges": [{"type": "calls", "source", "target", "key"}]}
Conventions reproduced from the provided graphs:
- node name = dotted module path (repo-relative; leading `src/`, `docs_src/` dropped; `__init__`
  collapsed) + qualname; nodes = classes, functions, methods (+ nested classes' methods).
- class text = header + docstring + method stubs (`def ...:\n    ...`); function text = source.
- edges `calls`: class -> its methods; function -> callee for calls whose name resolves via the
  module's imports or same-module definitions (Name / module.attr / Class() constructors).
  `self.x()` calls are not resolved (the provided graphs don't resolve them either).

Usage: .venv/bin/python -m src.graphbuild.build <repo_dir> <out.json> [--name repo_name]
       .venv/bin/python -m src.graphbuild.build --parity   # compare vs provided graphs (4 repos)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "build", "dist", ".tox", ".venv", "venv", "node_modules", "site", ".eggs"}
STRIP_PREFIXES = ("src/", "docs_src/")


def module_name(rel: str) -> str:
    for p in STRIP_PREFIXES:
        if rel.startswith(p):
            rel = rel[len(p):]
            break
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def class_text(node: ast.ClassDef, src: str) -> str:
    seg = ast.get_source_segment(src, node) or ""
    header = seg.split("\n", 1)[0]
    # keep header lines up to the colon that opens the body
    first_body = node.body[0] if node.body else None
    lines = src.splitlines()
    head_end = (first_body.lineno - 1) if first_body else node.lineno
    header = "\n".join(lines[node.lineno - 1: head_end]).strip("\n")
    header = header.lstrip()
    out = [header]
    doc = ast.get_docstring(node, clean=True)
    if doc:
        out.append(f'    """{doc}"""')
        out.append("")
    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig_lines = lines[b.lineno - 1: b.body[0].lineno - 1] if b.body else [lines[b.lineno - 1]]
            sig = "\n".join(sig_lines).rstrip()
            # drop the docstring line(s) accidentally included when body[0] is the docstring itself
            if b.body and isinstance(b.body[0], ast.Expr) and isinstance(getattr(b.body[0], "value", None), ast.Constant):
                pass
            out.append(sig if sig.lstrip().startswith(("def", "async")) else "    " + sig.lstrip())
            out.append("        ...")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def func_text(node, src: str) -> str:
    seg = ast.get_source_segment(src, node) or ""
    return seg


class ModuleIndex:
    def __init__(self, mod: str, tree: ast.Module):
        self.mod = mod
        self.imports: dict[str, str] = {}  # local alias -> dotted target
        self.defs: set[str] = set()
        for n in tree.body:
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    pkg = mod.split(".")
                    pkg = pkg[: len(pkg) - n.level] if len(pkg) >= n.level else []
                    base = ".".join(pkg + ([base] if base else []))
                for a in n.names:
                    self.imports[a.asname or a.name] = f"{base}.{a.name}" if base else a.name
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs.add(n.name)

    def resolve(self, func: ast.expr) -> str | None:
        if isinstance(func, ast.Name):
            if func.id in self.defs:
                return f"{self.mod}.{func.id}"
            return self.imports.get(func.id)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            if base in ("self", "cls"):
                return None
            if base in self.imports:
                return f"{self.imports[base]}.{func.attr}"
            if base in self.defs:
                return f"{self.mod}.{base}.{func.attr}"
        return None


def build_graph(repo: Path, repo_name: str) -> dict:
    nodes: dict[str, str] = {}
    raw_calls: list[tuple[str, str]] = []
    contains: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = Path(dirpath) / fn
            rel = path.relative_to(repo).as_posix()
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(src)
            except (SyntaxError, ValueError):
                continue
            mod = module_name(rel)
            idx = ModuleIndex(mod, tree)

            def visit(body, prefix: str, owner: str | None):
                for n in body:
                    if isinstance(n, (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.While)):
                        # definitions under `if TYPE_CHECKING:`, try/except imports, etc.
                        inner = list(getattr(n, "body", [])) + list(getattr(n, "orelse", []))
                        for h in getattr(n, "handlers", []) or []:
                            inner += h.body
                        inner += list(getattr(n, "finalbody", []) or [])
                        visit(inner, prefix, owner)
                        continue
                    if isinstance(n, ast.ClassDef):
                        name = f"{prefix}.{n.name}"
                        nodes[name] = class_text(n, src)
                        if owner:
                            contains.append((owner, name))
                        visit(n.body, name, name)
                    elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        name = f"{prefix}.{n.name}"
                        nodes[name] = func_text(n, src)
                        if owner:
                            contains.append((owner, name))
                        for sub in ast.walk(n):
                            if isinstance(sub, ast.Call):
                                tgt = idx.resolve(sub.func)
                                if tgt:
                                    raw_calls.append((name, tgt))
                        visit(n.body, prefix, name)  # nested defs are named under the enclosing class/module

            visit(tree.body, mod, None)
    edges = []
    seen = set()
    for s, t in contains + raw_calls:
        if t not in nodes and t.rsplit(".", 1)[0] in nodes and t.rsplit(".", 1)[-1] == "__init__":
            t = t.rsplit(".", 1)[0]
        if t in nodes and s != t:
            # provided graphs store each relation in both directions
            for a, b in ((s, t), (t, s)):
                if (a, b) not in seen:
                    seen.add((a, b))
                    edges.append({"type": "calls", "source": a, "target": b, "key": 0})
    return {"directed": True, "multigraph": True, "graph": {"repo_name": repo_name},
            "nodes": [{"id": n, "name": n, "text": t} for n, t in nodes.items()], "edges": edges}


def parity() -> None:
    import subprocess
    import tempfile

    from src.dataio.loaders import DATA, load_tasks

    seen = set()
    for t in load_tasks():
        if t.short in seen:
            continue
        seen.add(t.short)
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            subprocess.run(["tar", "xzf", str(DATA / "snapshots" / f"{t.instance_id}.tgz"), "-C", td,
                            "--wildcards", "*.py"], capture_output=True)
            mine = build_graph(Path(td), t.key)
        ref = json.load(open(DATA / "graphs" / f"{t.key}.json"))
        rn = {n["name"] for n in ref["nodes"]}
        mn = {n["name"] for n in mine["nodes"]}
        re_ = {(e["source"], e["target"]) for e in ref["edges"]}
        me = {(e["source"], e["target"]) for e in mine["edges"]}
        print(f"{t.short:9} nodes ref={len(rn)} mine={len(mn)} recall={len(rn & mn) / len(rn):.3f} precision={len(rn & mn) / max(len(mn), 1):.3f} "
              f"| edges ref={len(re_)} mine={len(me)} recall={len(re_ & me) / max(len(re_), 1):.3f} precision={len(re_ & me) / max(len(me), 1):.3f}")
        missing = sorted(rn - mn)[:5]
        extra = sorted(mn - rn)[:5]
        print("   missing e.g.", missing, "\n   extra e.g.", extra)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--name", default=None)
    ap.add_argument("--parity", action="store_true")
    a = ap.parse_args()
    if a.parity:
        parity()
        return
    g = build_graph(Path(a.repo), a.name or Path(a.repo).name)
    Path(a.out).write_text(json.dumps(g))
    print(f"nodes={len(g['nodes'])} edges={len(g['edges'])} -> {a.out}")


if __name__ == "__main__":
    main()
