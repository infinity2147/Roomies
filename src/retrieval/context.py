"""Per-task retrieval context: graph structure, BM25 index, embeddings, anchors, gold targets."""

from __future__ import annotations

import json
from pathlib import Path
import math
from collections import Counter, deque
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.dataio.loaders import DATA, Task, load_embeddings, load_graph, load_tasks
from src.retrieval.text import Anchors, extract_anchors, name_tokens, tokenize

REPO_PKG = {"fastapi": "fastapi", "rich": "rich", "requests": "requests", "httpx": "httpx"}
TEST_COMPONENTS = {"tests", "test", "testing", "conftest"}


def is_test_node(name: str) -> bool:
    comps = name.split(".")
    return any(c in TEST_COMPONENTS or c.startswith("test_") for c in comps[:-1]) or comps[0] in TEST_COMPONENTS


class BM25:
    """Plain Okapi BM25 over pre-tokenized docs (vectorized per query term)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.dl = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.dl.mean()) if self.n else 1.0
        self.postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        tmp: dict[str, list[tuple[int, int]]] = {}
        for i, d in enumerate(docs):
            for t, c in Counter(d).items():
                tmp.setdefault(t, []).append((i, c))
        for t, lst in tmp.items():
            idx = np.array([x[0] for x in lst], dtype=np.int32)
            tf = np.array([x[1] for x in lst], dtype=np.float32)
            self.postings[t] = (idx, tf)

    def idf(self, t: str) -> float:
        df = len(self.postings[t][0]) if t in self.postings else 0
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(self.n, dtype=np.float32)
        for t, qtf in Counter(query).items():
            if t not in self.postings:
                continue
            idx, tf = self.postings[t]
            denom = tf + self.k1 * (1 - self.b + self.b * self.dl[idx] / self.avgdl)
            s[idx] += self.idf(t) * (tf * (self.k1 + 1) / denom) * min(qtf, 3)
        return s


@dataclass
class GraphIndex:
    key: str
    names: list[str]
    idx: dict[str, int]
    texts: list[str]
    out_adj: list[np.ndarray]
    in_adj: list[np.ndarray]
    module_of: list[str]
    parent: np.ndarray  # index of enclosing class/function node, -1 if module level
    short: list[str]  # last name component
    is_test: np.ndarray
    kind: np.ndarray  # 0 function, 1 class, 2 method/nested
    emb: np.ndarray | None  # (N, 256) L2-normalized, aligned with names
    bm25_full: BM25
    bm25_name: BM25
    short_to_idx: dict[str, list[int]]

    @property
    def n(self) -> int:
        return len(self.names)

    def undirected(self, i: int) -> np.ndarray:
        return np.union1d(self.out_adj[i], self.in_adj[i])


@lru_cache(maxsize=16)
def graph_index(key: str) -> GraphIndex:
    """key = competition graph key, or "path:<json file>" for our own graphs (no embeddings)."""
    if key.startswith("path:"):
        g = json.loads(Path(key[5:]).read_text())
    else:
        g = load_graph(key)
    names = [n["name"] for n in g["nodes"]]
    texts = [n.get("text") or "" for n in g["nodes"]]
    idx = {n: i for i, n in enumerate(names)}
    out_l: list[list[int]] = [[] for _ in names]
    in_l: list[list[int]] = [[] for _ in names]
    for e in g["edges"]:
        s, t = idx.get(e["source"]), idx.get(e["target"])
        if s is None or t is None or s == t:
            continue
        out_l[s].append(t)
        in_l[t].append(s)
    out_adj = [np.unique(np.array(x, dtype=np.int32)) for x in out_l]
    in_adj = [np.unique(np.array(x, dtype=np.int32)) for x in in_l]

    parent = np.full(len(names), -1, dtype=np.int32)
    for i, n in enumerate(names):
        if "." in n:
            p = n.rsplit(".", 1)[0]
            if p in idx:
                parent[i] = idx[p]

    module_of: list[str] = []
    for i, n in enumerate(names):
        j = i
        while parent[j] >= 0:
            j = parent[j]
        module_of.append(names[j].rsplit(".", 1)[0] if "." in names[j] else "")

    kind = np.zeros(len(names), dtype=np.int8)
    for i, t in enumerate(texts):
        head = t.lstrip()
        while head.startswith("@"):
            head = head.split("\n", 1)[1].lstrip() if "\n" in head else ""
        if head.startswith("class "):
            kind[i] = 1
        elif parent[i] >= 0:
            kind[i] = 2

    short = [n.rsplit(".", 1)[-1] for n in names]
    short_to_idx: dict[str, list[int]] = {}
    for i, s in enumerate(short):
        short_to_idx.setdefault(s, []).append(i)

    emb = None
    try:
        if key.startswith("path:"):
            raise FileNotFoundError
        enames, mat = load_embeddings(key)
        pos = {n: i for i, n in enumerate(enames)}
        emb = np.zeros((len(names), mat.shape[1]), dtype=np.float32)
        for i, n in enumerate(names):
            if n in pos:
                emb[i] = mat[pos[n]]
        nrm = np.linalg.norm(emb, axis=1, keepdims=True)
        emb = emb / np.maximum(nrm, 1e-8)
    except FileNotFoundError:
        pass

    name_docs = [name_tokens(n) for n in names]
    full_docs = [name_docs[i] * 3 + tokenize(texts[i][:4000]) for i in range(len(names))]
    return GraphIndex(
        key=key,
        names=names,
        idx=idx,
        texts=texts,
        out_adj=out_adj,
        in_adj=in_adj,
        module_of=module_of,
        parent=parent,
        short=short,
        is_test=np.array([is_test_node(n) for n in names]),
        kind=kind,
        emb=emb,
        bm25_full=BM25(full_docs),
        bm25_name=BM25(name_docs),
        short_to_idx=short_to_idx,
    )


def bfs_dist(gi: GraphIndex, seeds: list[int], max_hops: int = 3) -> np.ndarray:
    """Undirected hop distance from the seed set (max_hops+1 if unreached)."""
    dist = np.full(gi.n, max_hops + 1, dtype=np.int8)
    q: deque[int] = deque()
    for s in seeds:
        if dist[s] > 0:
            dist[s] = 0
            q.append(s)
    while q:
        u = q.popleft()
        if dist[u] >= max_hops:
            continue
        for v in gi.undirected(u):
            if dist[v] > dist[u] + 1:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


@dataclass
class TaskCtx:
    task: Task
    gi: GraphIndex
    query: str
    anchors: Anchors
    targets: np.ndarray  # node indices of gold targets
    target_modules: set[str]


def load_targets() -> dict[str, dict]:
    with open(DATA / "derived" / "targets.jsonl") as f:
        return {r["instance_id"]: r for r in map(json.loads, f)}


def build_contexts(tasks: list[Task] | None = None) -> list[TaskCtx]:
    tasks = tasks or load_tasks()
    tg = load_targets()
    out = []
    for t in tasks:
        gi = graph_index(t.key)
        r = tg.get(t.instance_id, {})
        tnodes = np.array([gi.idx[n] for n in r.get("target_nodes", []) if n in gi.idx], dtype=np.int32)
        tmods = {m for m in (r.get("target_modules") or {}).values() if m}
        query = t.problem_statement + ("\n" + t.hints_text if t.hints_text else "")
        out.append(TaskCtx(t, gi, query, extract_anchors(query), tnodes, tmods))
    return out
