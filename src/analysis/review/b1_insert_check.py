"""B1 audit: how many target nodes come only from pure-insertion lines that sit at the END of a span
(i.e. a new def/statement appended after the function -> previous function labelled)."""
import json
from unidiff import PatchSet
from src.dataio.loaders import load_tasks, load_graph
from src.groundtruth.map_patch import read_files_from_snapshot, qualname_spans, resolve_module
tasks = {t.instance_id: t for t in load_tasks()}
tg = {json.loads(l)["instance_id"]: json.loads(l) for l in open("data/derived/targets.jsonl")}
sus_tasks = 0; sus_nodes = 0; tot_nodes = 0; examples = []
for iid, r in tg.items():
    t = tasks[iid]; names = {n["name"] for n in load_graph(t.key)["nodes"]}
    ps = PatchSet(t.patch); mod_files = [f for f in ps if not f.is_added_file]
    files = read_files_from_snapshot(t, [f.path for f in mod_files])
    removed_nodes, insert_nodes = set(), {}
    for pf in mod_files:
        src = files.get(pf.path)
        if src is None: continue
        spans = qualname_spans(src); mod = resolve_module(pf.path, [q for q, _, _ in spans], names)
        def node_of(line):
            for q, a, b in sorted([s for s in spans if s[1] <= line <= s[2]], key=lambda s: s[2]-s[1]):
                if mod and f"{mod}.{q}" in names: return f"{mod}.{q}", (a, b)
            return None, None
        for h in pf:
            prev = h.source_start; added_block = []
            for ln in h:
                if ln.is_removed:
                    n, _ = node_of(ln.source_line_no); removed_nodes.add(n)
                elif ln.is_added:
                    n, sp = node_of(max(prev, 1))
                    if n: insert_nodes.setdefault(n, []).append((prev == sp[1] - 0 or prev < sp[1], prev == sp[1-1+1], ln.value.strip()))
                if ln.source_line_no is not None: prev = ln.source_line_no
    # nodes only reached by insertions where insertion line == span end AND the added text is a new def/class/decorator
    for n, ins in insert_nodes.items():
        if n in removed_nodes: continue
        tot_nodes += 1
    nodes_end = set()
    for pf in mod_files:
        src = files.get(pf.path)
        if src is None: continue
        spans = qualname_spans(src); mod = resolve_module(pf.path, [q for q, _, _ in spans], names)
        for h in pf:
            prev = h.source_start
            for ln in h:
                if ln.is_added and ln.value.lstrip().startswith(("def ", "async def ", "class ", "@")):
                    for q, a, b in sorted([s for s in spans if s[1] <= prev <= s[2]], key=lambda s: s[2]-s[1]):
                        if mod and f"{mod}.{q}" in names:
                            if prev == b and f"{mod}.{q}" not in removed_nodes: nodes_end.add(f"{mod}.{q}")
                            break
                if ln.source_line_no is not None: prev = ln.source_line_no
    nodes_end &= set(r["target_nodes"])
    if nodes_end:
        sus_tasks += 1; sus_nodes += len(nodes_end); examples.append((iid, sorted(nodes_end)[:2]))
allnodes = sum(len(r["target_nodes"]) for r in tg.values())
print(f"target nodes total {allnodes}; suspicious (new def/class inserted right after a span's last line, node not otherwise edited): {sus_nodes} in {sus_tasks} tasks")
print(examples[:8])
