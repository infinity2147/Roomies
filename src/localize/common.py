"""Shared helpers for the graph-locate offline experiments (labels, task lists, skill-module loader)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "graph-locate"
SNAP = Path(os.environ.get("GL_SNAP", "/tmp/gl_snap"))  # extracted *.py snapshots: SNAP/<instance_id>/
CACHE = Path(os.environ.get("GL_CACHE", "/tmp/gl_cache"))


def load_gl():
    spec = importlib.util.spec_from_file_location("graph_locate", SKILL / "scripts" / "graph_locate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tasks():
    """returns list of dict(id, repo, text, patch, split) ; split in {train, test}. Proxy eval-half is TEST ONLY."""
    half = set((ROOT / "ops/queue/shards/proxy_eval_half.txt").read_text().split())
    valid = set((ROOT / "data/derived/valid_tasks.txt").read_text().split())
    out = []
    for l in open(ROOT / "data/tasks.jsonl"):
        r = json.loads(l)
        if r["instance_id"] in valid:
            out.append(dict(id=r["instance_id"], repo=r["repo"], text=r["problem_statement"], patch=r["patch"], split="train", src="public"))
    for l in open(ROOT / "data/derived/proxy/valid_tasks.jsonl"):
        r = json.loads(l)
        out.append(dict(id=r["instance_id"], repo=r["repo"], text=r["problem_statement"], patch=r["patch"],
                        split="test" if r["instance_id"] in half else "train", src="proxy"))
    return out


def gold_of(patch: str, ix):
    """gold files (existing, non-added) and gold function node ids: functions whose line range (old side) contains a changed
    line; pure insertions count the line just before the insertion point and the first line after."""
    from unidiff import PatchSet
    files, funcs = [], set()
    for pf in PatchSet(patch):
        if pf.is_added_file:
            continue
        path = pf.path
        if not path.endswith(".py"):
            continue
        files.append(path)
        ns = ix.byfile.get(path, [])
        for h in pf:
            old = h.source_start
            ln = old
            for line in h:
                if line.is_context:
                    ln += 1
                elif line.is_removed:
                    for n in ns:
                        if n.start <= ln <= n.end:
                            funcs.add(n.id)
                    ln += 1
                elif line.is_added:
                    for n in ns:  # insertion between ln-1 and ln: inside function if both neighbours are inside
                        if n.start < ln <= n.end:
                            funcs.add(n.id)
    return files, funcs


class LN:
    __slots__ = ("id", "file", "qual", "name", "start", "end", "callees", "callers", "sib", "mod")


class _IX:
    pass


class CQ:
    """compact, picklable per-task snapshot of (index, query) with the same interface State/run_budget need."""

    def __init__(self, d):
        self.__dict__.update(d)
        self.ix = _IX()
        self.ix.nodes = []
        for i, t in enumerate(d["nodes"]):
            n = LN()
            n.id = i
            (n.file, n.qual, n.name, n.start, n.end, n.callees, n.callers, n.sib, n.mod) = t
            self.ix.nodes.append(n)
        self.seed_score = dict(enumerate(d["seed_score"]))
        self._order = sorted(self.seed_score, key=lambda k: (-self.seed_score[k], k))
        self.byfile = {}
        for n in self.ix.nodes:
            self.byfile.setdefault(n.file, []).append(n.id)

    def static(self, nid):
        return self.stat[nid]

    def seeds(self, S=20):
        return self._order[:S]


def compact(gl, task, snap=None):
    snap = snap or (SNAP / task["id"])
    ix = gl.build_index(str(snap), time_budget=120)
    q = gl.Query(ix, task["text"])
    N = len(ix.nodes)
    stat = [q.static(i) for i in range(N)]
    seed = [q.seed_score[i] for i in range(N)]
    files, funcs = gold_of(task["patch"], ix)
    return dict(id=task["id"], repo=task["repo"], split=task["split"], src=task["src"], gold_files=files,
                gold_funcs=sorted(funcs), build_time=ix.build_time, N=N, stat=stat, seed_score=seed,
                nodes=[(n.file, n.qual, n.name, n.start, n.end, n.callees, n.callers, n.sib, n.mod) for n in ix.nodes])


def load_cq(tid):
    import pickle
    return CQ(pickle.load(open(CACHE / (tid + ".pkl"), "rb")))
