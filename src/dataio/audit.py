"""A1 data audit: coverage of snapshots/graphs/embeddings per task, sizes, patch stats.

Usage: .venv/bin/python -m src.dataio.audit [--out reports/data_audit.json]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from unidiff import PatchSet

from .loaders import ROOT, embedding_path, graph_path, load_tasks, snapshot_candidates


def patch_stats(patch: str) -> dict:
    ps = PatchSet(patch)
    return {
        "files": len(ps),
        "added_files": sum(f.is_added_file for f in ps),
        "hunks": sum(len(f) for f in ps),
        "lines_added": ps.added,
        "lines_removed": ps.removed,
        "paths": [f.path for f in ps],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "data_audit.json"))
    args = ap.parse_args()

    tasks = load_tasks()
    rows = []
    for t in tasks:
        g, e = graph_path(t), embedding_path(t)
        snaps = snapshot_candidates(t)
        row = {
            "instance_id": t.instance_id,
            "repo": t.short,
            "has_graph": g.exists(),
            "has_emb": e.exists(),
            "snapshots": [p.name for p in snaps],
            "has_hints": bool(t.hints_text.strip()),
            "ps_chars": len(t.problem_statement),
            "patch": patch_stats(t.patch),
            "test_patch": patch_stats(t.test_patch),
        }
        if g.exists():
            gj = json.loads(g.read_text())
            row["nodes"] = len(gj["nodes"])
            row["edges"] = len(gj["edges"])
            row["edge_types"] = dict(Counter(x["type"] for x in gj["edges"]))
        rows.append(row)

    by_repo = defaultdict(list)
    for r in rows:
        by_repo[r["repo"]].append(r)

    print(f"tasks: {len(rows)}  unique graph keys: {len({t.key for t in tasks})}")
    hdr = f"{'repo':10} {'n':>4} {'graph':>6} {'emb':>5} {'snap':>5} {'hints':>6} {'nodes~':>8} {'files~':>7} {'hunks~':>7} {'newfile%':>8} {'touches_tests%':>14}"
    print(hdr)
    for repo, rs in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        med = lambda xs: st.median(xs) if xs else 0  # noqa: E731
        print(
            f"{repo:10} {len(rs):4d} {sum(r['has_graph'] for r in rs):6d} {sum(r['has_emb'] for r in rs):5d} "
            f"{sum(bool(r['snapshots']) for r in rs):5d} {sum(r['has_hints'] for r in rs):6d} "
            f"{med([r.get('nodes', 0) for r in rs]):8.0f} {med([r['patch']['files'] for r in rs]):7.1f} "
            f"{med([r['patch']['hunks'] for r in rs]):7.1f} "
            f"{100 * sum(r['patch']['added_files'] > 0 for r in rs) / len(rs):8.0f} "
            f"{100 * sum(any('test' in p for p in r['patch']['paths']) for r in rs) / len(rs):14.0f}"
        )

    missing = [r["instance_id"] for r in rows if not (r["has_graph"] and r["has_emb"])]
    nosnap = [r["instance_id"] for r in rows if not r["snapshots"]]
    print("missing graph/emb:", missing)
    print("missing snapshot:", nosnap)
    ext = Counter(Path(p).suffix for r in rows for p in r["patch"]["paths"])
    print("gold patch file types:", dict(ext.most_common(8)))
    print("edge types (all graphs):", sum((Counter(r.get("edge_types", {})) for r in rows), Counter()))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, indent=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
