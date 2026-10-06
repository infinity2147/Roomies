"""Proxy-queue report: per-run pass rate + paired comparison vs a baseline on common tasks.

Reads results/px/<run>/<shard>/task_results.jsonl (partial shards included: rows are written as tasks finish).
Usage: .venv/bin/python ops/queue/px_report.py [--base c8] [--done-only]
Run names look like px_<cand>_s<seed>; candidates are pooled over seeds for the paired test
(pairs = (task, seed) present in both candidate and base).
"""
import argparse, json, math, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument("--base", default="c8")
ap.add_argument("--done-only", action="store_true", help="only shards whose queue item is in ops/queue/done")
a = ap.parse_args()

done = {p.name for p in (ROOT / "ops/queue/done").iterdir()}
res = defaultdict(dict)  # (cand, seed) -> {task: row}
for f in sorted((ROOT / "results/px").glob("px_*/s*/task_results.jsonl")):
    run, shard = f.parent.parent.name, f.parent.name
    m = re.match(r"px_(.+)_s(\d+)$", run)
    if not m:
        continue
    if a.done_only and not any(d.endswith(f"_{shard}_{run}") for d in done):
        continue
    for line in open(f):
        r = json.loads(line)
        res[(m[1], m[2])][r["instance_id"]] = r

print(f"{'run':<22}{'n':>5}{'pass':>6}{'rate':>7}{'min/task':>9}{'ctxErr':>7}{'err':>5}{'empty':>6}")
for (c, s), rows in sorted(res.items()):
    v = list(rows.values()); n = len(v)
    p = sum(r["resolved"] for r in v)
    ctx = sum("ContextWindowExceeded" in (r.get("error") or "") for r in v)
    err = sum(bool(r.get("error")) for r in v)
    emp = sum(not r.get("agent_patch_size") for r in v)
    t = sum(r.get("duration_seconds") or 0 for r in v) / max(n, 1) / 60
    print(f"{c+'_s'+s:<22}{n:>5}{p:>6}{p/max(n,1):>7.3f}{t:>9.1f}{ctx:>7}{err:>5}{emp:>6}")

print(f"\nPaired vs {a.base} (pairs = same task & seed; wins = cand pass & base fail):")
cands = sorted({c for c, _ in res} - {a.base})
for c in cands:
    w = l = n = pc = pb = 0
    for (cc, s), rows in res.items():
        if cc != c or (a.base, s) not in res:
            continue
        b = res[(a.base, s)]
        for t, r in rows.items():
            if t in b:
                n += 1; x, y = r["resolved"], b[t]["resolved"]
                pc += x; pb += y; w += x and not y; l += y and not x
    if n:
        z = (w - l) / math.sqrt(w + l) if w + l else 0.0
        print(f"  {c:<18} n={n:<4} cand={pc/n:.3f} base={pb/n:.3f} diff={(pc-pb)/n:+.3f} wins={w} losses={l} sign-z={z:+.2f}")
