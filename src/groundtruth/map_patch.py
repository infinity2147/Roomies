"""B1: map gold patches to graph nodes (free localization supervision).

For each task: parse the gold patch, read touched files at base_commit from the snapshot
tarball, compute qualified-name spans with `ast`, map changed old-file lines to the
innermost enclosing def/class, and keep names present in the provided graph.

Usage: .venv/bin/python -m src.groundtruth.map_patch [--out data/derived/targets.jsonl]
"""

from __future__ import annotations

import argparse
import ast
import json
import tarfile
from collections import Counter
from pathlib import Path

from unidiff import PatchSet

from src.dataio.loaders import DATA, Task, load_graph, load_tasks


def read_files_from_snapshot(task: Task, paths: list[str]) -> dict[str, str]:
    tgz = DATA / "snapshots" / f"{task.instance_id}.tgz"
    want = {f"./{p}" for p in paths} | set(paths)
    out = {}
    with tarfile.open(tgz) as tf:
        for m in tf:
            if m.name in want and m.isfile():
                out[m.name.removeprefix("./")] = tf.extractfile(m).read().decode("utf-8", "replace")
    return out


def qualname_spans(src: str) -> list[tuple[str, int, int]]:
    """(relative qualname, start_line, end_line) for every def/class, decorators included."""
    spans: list[tuple[str, int, int]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{child.name}" if prefix else child.name
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                spans.append((q, start, child.end_lineno))
                visit(child, q)
            elif not isinstance(child, (ast.Lambda,)):
                visit(child, prefix)

    visit(ast.parse(src), "")
    return spans


def module_candidates(path: str) -> list[str]:
    parts = path[:-3].split("/") if path.endswith(".py") else path.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts))]


def resolve_module(path: str, rel_quals: list[str], names: set[str]) -> str | None:
    best, best_hits = None, 0
    for mod in module_candidates(path):
        hits = sum(f"{mod}.{q}" in names for q in rel_quals)
        if hits > best_hits:
            best, best_hits = mod, hits
    return best


def changed_old_lines(pf) -> set[int]:
    """Old-file line numbers touched by a patched file; pure insertions map to the line above."""
    lines: set[int] = set()
    for h in pf:
        prev_old = h.source_start
        for ln in h:
            if ln.is_removed:
                lines.add(ln.source_line_no)
            elif ln.is_added:
                lines.add(max(prev_old, 1))
            if ln.source_line_no is not None:
                prev_old = ln.source_line_no
    return lines


def map_task(task: Task) -> dict:
    names = {n["name"] for n in load_graph(task.key)["nodes"]}
    ps = PatchSet(task.patch)
    modified = [f for f in ps if not f.is_added_file]
    files = read_files_from_snapshot(task, [f.path for f in modified])
    target_nodes: list[str] = []
    target_modules: dict[str, str | None] = {}
    unmapped: list[dict] = []
    for pf in modified:
        src = files.get(pf.path)
        if src is None:
            unmapped.append({"path": pf.path, "reason": "file_not_in_snapshot"})
            continue
        try:
            spans = qualname_spans(src)
        except SyntaxError:
            unmapped.append({"path": pf.path, "reason": "syntax_error"})
            continue
        mod = resolve_module(pf.path, [q for q, _, _ in spans], names)
        target_modules[pf.path] = mod
        for line in sorted(changed_old_lines(pf)):
            inner = [s for s in spans if s[1] <= line <= s[2]]
            hit = None
            # innermost enclosing span that exists in the graph
            for q, a, b in sorted(inner, key=lambda s: s[2] - s[1]):
                if mod and f"{mod}.{q}" in names:
                    hit = f"{mod}.{q}"
                    break
            if hit:
                if hit not in target_nodes:
                    target_nodes.append(hit)
            else:
                unmapped.append({"path": pf.path, "line": line, "reason": "module_level" if not inner else "not_in_graph"})
    return {
        "instance_id": task.instance_id,
        "repo": task.short,
        "target_nodes": target_nodes,
        "target_files": [f.path for f in ps],
        "target_modules": target_modules,
        "added_files": [f.path for f in ps if f.is_added_file],
        "unmapped": unmapped,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "derived" / "targets.jsonl"))
    args = ap.parse_args()
    rows = []
    for t in load_tasks():
        if not (DATA / "snapshots" / f"{t.instance_id}.tgz").exists():
            print("skip (no snapshot)", t.instance_id)
            continue
        try:
            rows.append(map_task(t))
        except (EOFError, tarfile.ReadError) as e:
            print("skip (bad snapshot)", t.instance_id, e)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n = len(rows)
    full = sum(bool(r["target_nodes"]) and not r["unmapped"] for r in rows)
    some = sum(bool(r["target_nodes"]) for r in rows)
    only_new = sum(not r["target_nodes"] and bool(r["added_files"]) for r in rows)
    print(f"tasks mapped: {n}  fully mapped: {full} ({full / n:.0%})  >=1 node: {some} ({some / n:.0%})  only new files: {only_new}")
    print("unmapped reasons:", Counter(u["reason"] for r in rows for u in r["unmapped"]))
    print("#targets/task:", Counter(min(len(r["target_nodes"]), 6) for r in rows))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
