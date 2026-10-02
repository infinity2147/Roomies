"""Does the provided graph reflect base_commit (pre-fix) or the fixed code? Count gold '+' / '-' lines found in node texts."""
import json, re, sys
from src.dataio.loaders import load_tasks, graph_path
tasks = load_tasks()
plus_hits = minus_hits = n = 0
for t in tasks:
    p = graph_path(t)
    if not p.exists(): continue
    g = json.load(open(p))
    nodes = g["nodes"] if isinstance(g, dict) else g
    text = "\n".join((x.get("text") or "") for x in nodes)
    add = [l[1:].strip() for l in t.patch.splitlines() if l.startswith("+") and not l.startswith("+++") and len(l.strip()) > 25]
    rem = [l[1:].strip() for l in t.patch.splitlines() if l.startswith("-") and not l.startswith("---") and len(l.strip()) > 25]
    # only lines unique to one side
    add_u = [l for l in add if l not in rem]; rem_u = [l for l in rem if l not in add]
    if not add_u or not rem_u: continue
    n += 1
    a = sum(l in text for l in add_u) / len(add_u); r = sum(l in text for l in rem_u) / len(rem_u)
    plus_hits += a; minus_hits += r
print(f"tasks {n}: mean frac of added(+) lines found in graph text {plus_hits/n:.3f}; removed(-) lines {minus_hits/n:.3f}")
