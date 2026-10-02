"""Offline accuracy of the repo-tools locate.py skill script against gold patch files/nodes.

Extracts each snapshot's .py files to a temp dir, runs locate.py with the issue text as the query
(as the agent would), parses `path:start-end kind qualname` lines.
Usage: .venv/bin/python -m src.eval.eval_locate_skill [--skill submissions/c1/skills/repo-tools] [--chars 1500]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from unidiff import PatchSet

from src.dataio.loaders import DATA, ROOT, load_tasks

LINE = re.compile(r"^\s+(\S+\.py):(\d+)-(\d+)\s+(?:class|def)\s+(\S+)")


def run_one(args) -> dict:
    t, skill, chars, k = args
    gold_files = [f.path for f in PatchSet(t.patch) if not f.is_added_file]
    tg = {}
    p = DATA / "derived" / "targets.jsonl"
    for line in open(p):
        r = json.loads(line)
        if r["instance_id"] == t.instance_id:
            tg = r
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        subprocess.run(["tar", "xzf", str(DATA / "snapshots" / f"{t.instance_id}.tgz"), "-C", td,
                        "--wildcards", "*.py", "./.git/HEAD"], capture_output=True)
        os.makedirs(os.path.join(td, ".git"), exist_ok=True)
        query = t.problem_statement[:chars]
        r = subprocess.run(["python3", str(Path(skill) / "scripts" / "locate.py"), "--query", query, "--k", str(k)],
                           capture_output=True, text=True, env={**os.environ, "SWE_WORKSPACE": td, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=300)
    hits = [LINE.match(l) for l in r.stdout.splitlines()]
    hits = [m for m in hits if m]
    files = []
    for m in hits:
        if m.group(1) not in files:
            files.append(m.group(1))
    m_files = re.search(r"Most relevant files: (.*)", r.stdout)
    ranked_files = [f.strip() for f in m_files.group(1).split(",")] if m_files else files
    tquals = {n.rsplit(".", 1)[-1] for n in tg.get("target_nodes", [])}
    node_pos = [i for i, m in enumerate(hits) if m.group(4).rsplit(".", 1)[-1] in tquals and m.group(1) in gold_files]
    file_pos = [i for i, f in enumerate(ranked_files) if f in gold_files]
    return {
        "instance_id": t.instance_id,
        "has_gold_file": bool(gold_files),
        "file_hit1": bool(file_pos and file_pos[0] < 1),
        "file_hit3": bool(file_pos and file_pos[0] < 3),
        "file_hit6": bool(file_pos),
        "node_hit1": bool(node_pos and node_pos[0] < 1),
        "node_hit5": bool(node_pos and node_pos[0] < 5),
        "node_hitk": bool(node_pos),
        "stderr": r.stderr[-300:],
        "chars_out": len(r.stdout),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default=str(ROOT / "submissions" / "c1" / "skills" / "repo-tools"))
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--k", type=int, default=12)
    a = ap.parse_args()
    tasks = load_tasks()
    with ProcessPoolExecutor(16) as ex:
        rows = list(ex.map(run_one, [(t, a.skill, a.chars, a.k) for t in tasks]))
    rows = [r for r in rows if r["has_gold_file"]]
    n = len(rows)
    for key in ("file_hit1", "file_hit3", "file_hit6", "node_hit1", "node_hit5", "node_hitk"):
        print(f"{key:10} {sum(r[key] for r in rows) / n:.3f}")
    errs = [r for r in rows if r["stderr"].strip()]
    print(f"n={n}  errors={len(errs)}  max_out_chars={max(r['chars_out'] for r in rows)}")
    for r in errs[:3]:
        print(r["instance_id"], r["stderr"])
    out = ROOT / "results" / "locate_skill_eval.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


if __name__ == "__main__":
    main()
