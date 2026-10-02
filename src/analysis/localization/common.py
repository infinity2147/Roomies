"""Per-task localization data for the headroom study (council, localization scientist).

One worker call per task (process pool, graph cached per process). Computes:
  * oracle / reachability statistics over the undirected code graph (BM25 seeds, anchor seeds)
  * a candidate pool (BM25 top-50 U 1-hop(BM25 top-10) U anchor seeds) with features for 2-stage re-rankers
Results are cached to a pickle so the analysis scripts are cheap to re-run.
"""

from __future__ import annotations

import os
import pickle
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from src.dataio.loaders import ROOT, load_tasks
from src.eval.loc_metrics import file_metrics, node_metrics, rank_from_scores
from src.retrieval.context import build_contexts, bfs_dist
from src.retrieval.features import FEATURE_NAMES, anchor_matches, build_features

CACHE = ROOT / "experiments" / "council_localization" / "per_task.pkl"
NS = (1, 5, 10, 20, 50, 100)
KS_EXP = (5, 10, 20)
POOL_TOPN, POOL_HOP_SEEDS = 50, 10
EXTRA_FEATS = ["nbr_bm25_max", "nbr_bm25_mean", "n_top10_nbrs", "in_bm25_top50", "pool_bm25_rank",
               "parent_bm25", "same_module_as_top1", "rrf_name", "rrf_anchor"]


def multi_dist(gi, seeds, max_hops: int) -> np.ndarray:
    if len(seeds) == 0:
        return np.full(gi.n, max_hops + 1, dtype=np.int16)
    return bfs_dist(gi, [int(s) for s in seeds], max_hops=max_hops).astype(np.int16)


def gold_dist(gi, src: int, golds: set[int], max_hops: int = 8) -> int:
    """Undirected shortest-path distance from src to nearest gold (max_hops+1 if none)."""
    if src in golds:
        return 0
    seen = {src}
    q = deque([(src, 0)])
    while q:
        u, d = q.popleft()
        if d >= max_hops:
            continue
        for v in gi.undirected(u):
            v = int(v)
            if v in seen:
                continue
            if v in golds:
                return d + 1
            seen.add(v)
            q.append((v, d + 1))
    return max_hops + 1


def _rank_of(scores: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """1-based rank of every masked node (inf for unmasked)."""
    r = np.full(len(scores), np.inf)
    order = rank_from_scores(scores, mask)
    r[order] = np.arange(1, len(order) + 1)
    return r


def work(iid: str) -> dict:
    ctx = _CTX[iid]
    gi = ctx.gi
    X, mask = build_features(ctx)
    fi = {f: i for i, f in enumerate(FEATURE_NAMES)}
    bm = X[:, fi["bm25"]]
    rk = rank_from_scores(bm, mask)
    golds = set(int(t) for t in ctx.targets if mask[t])
    G = len(set(int(t) for t in ctx.targets))
    out: dict = {"iid": iid, "repo": ctx.task.short, "n_nodes": gi.n, "n_nontest": int(mask.sum()),
                 "n_gold": G, "n_gold_nontest": len(golds)}
    gold_rank = sorted(int(np.flatnonzero(rk == g)[0]) + 1 for g in golds) if golds else []
    out["gold_bm25_ranks"] = gold_rank
    for N in NS:
        hits = sum(r <= N for r in gold_rank)
        out[f"bm25_recall@{N}"] = hits / G
        out[f"bm25_hit@{N}"] = float(hits > 0)
    m = node_metrics(rk, ctx.targets)
    out["bm25_mrr"] = m["mrr"]
    fm = file_metrics(rk, gi.module_of, ctx.target_modules)
    out.update({f"bm25_{k}": v for k, v in fm.items()})
    out["has_target_module"] = bool(ctx.target_modules)

    # (b) expansion from BM25 top-k, (c) anchors, union
    am = anchor_matches(ctx)
    anc = np.array([s for s in am["seeds"] if mask[s]], dtype=np.int32)
    out["n_anchor_seeds"] = int(len(anc))
    seedsets = {f"bm25top{k}": rk[:k] for k in KS_EXP}
    seedsets["anchor"] = anc
    seedsets["anchor+bm25top5"] = np.union1d(anc, rk[:5]).astype(np.int32)
    gl = np.array(sorted(golds), dtype=np.int32)
    for name, seeds in seedsets.items():
        d = multi_dist(gi, seeds, 2)
        for h in (0, 1, 2):
            C = mask & (d <= h)
            sz = int(C.sum())
            hits = int(C[gl].sum()) if len(gl) else 0
            out[f"{name}_h{h}_size"] = sz
            out[f"{name}_h{h}_recall"] = hits / G
            out[f"{name}_h{h}_hit"] = float(hits > 0)
            # oracle reorder of C: recall@5 / MRR ceiling
            out[f"{name}_h{h}_orR5"] = min(hits, 5) / G
            # equal-budget BM25: recall of BM25 top-|C|
            eb = sum(r <= sz for r in gold_rank)
            out[f"{name}_h{h}_eqbudget_recall"] = eb / G
            out[f"{name}_h{h}_eqbudget_hit"] = float(eb > 0)
            # gold reachable in C but NOT within BM25 top-50/100 (unique graph value)
            in_c = set(gl[C[gl]].tolist()) if len(gl) else set()
            out[f"{name}_h{h}_graph_only50"] = float(any(gold_rank_of(rk, g) > 50 for g in in_c))
            out[f"{name}_h{h}_graph_only100"] = float(any(gold_rank_of(rk, g) > 100 for g in in_c))
    # (d) distance from BM25 top-1 / top-5 to nearest gold
    out["dist_top1"] = gold_dist(gi, int(rk[0]), golds) if golds else 9
    out["dist_top5"] = min(gold_dist(gi, int(s), golds) for s in rk[:5]) if golds else 9
    out["dist_anchor"] = (min(gold_dist(gi, int(s), golds, 4) for s in anc[:200]) if len(anc) and golds else 9)
    out["deg_top5_median"] = float(np.median([len(gi.undirected(int(s))) for s in rk[:5]]))
    out["deg_gold_median"] = float(np.median([len(gi.undirected(g)) for g in golds])) if golds else 0.0

    # candidate pool for 2-stage re-rankers
    top_hop = multi_dist(gi, rk[:POOL_HOP_SEEDS], 1)
    pool_mask = mask & (top_hop <= 1)
    pool_mask[rk[:POOL_TOPN]] = True
    pool_mask[anc] = True
    pool = np.flatnonzero(pool_mask & mask)
    bmn = bm / max(float(bm[mask].max()), 1e-6)
    top10 = np.zeros(gi.n, dtype=bool)
    top10[rk[:10]] = True
    rname = _rank_of(X[:, fi["bm25_name_norm"]], mask)
    ranc = _rank_of(X[:, fi["anc_short_idf"]], mask & (X[:, fi["anc_short_idf"]] > 0))
    top1_mod = gi.module_of[int(rk[0])]
    bm_rank = _rank_of(bm, mask)
    extra = np.zeros((len(pool), len(EXTRA_FEATS)), dtype=np.float32)
    for j, v in enumerate(pool):
        nb = gi.undirected(int(v))
        nbm = bmn[nb][mask[nb]] if len(nb) else np.zeros(0)
        p = gi.parent[v]
        extra[j] = [nbm.max() if len(nbm) else 0, nbm.mean() if len(nbm) else 0, top10[nb].sum() if len(nb) else 0,
                    float(bm_rank[v] <= 50), np.log1p(bm_rank[v]), bmn[p] if p >= 0 else 0,
                    float(gi.module_of[v] == top1_mod), 1 / (60 + rname[v]), 1 / (60 + ranc[v])]
    y = np.zeros(len(pool), dtype=np.int32)
    y[np.isin(pool, gl)] = 1
    out["pool"] = pool
    out["pool_X"] = np.concatenate([X[pool], extra], axis=1)
    out["pool_y"] = y
    out["pool_size"] = int(len(pool))
    out["pool_recall"] = int(y.sum()) / G
    out["pool_hit"] = float(y.sum() > 0)
    # full-ranking support for evaluation after re-rank
    out["bm25_rank_top"] = rk[:2000]
    out["targets"] = np.array(ctx.targets, dtype=np.int32)
    out["target_modules"] = set(ctx.target_modules)
    keep = set(rk[:2000].tolist()) | set(pool.tolist())
    out["module_of"] = {int(i): gi.module_of[int(i)] for i in keep}
    # full-graph score vectors needed by RRF (only for masked nodes in top lists to limit size)
    out["rrf_inputs"] = {
        "bm25": rank_from_scores(bm, mask)[:3000],
        "name": rank_from_scores(X[:, fi["bm25_name_norm"]], mask)[:3000],
        "anchor": rank_from_scores(X[:, fi["anc_short_idf"]], mask & (X[:, fi["anc_short_idf"]] > 0))[:3000],
        "emb": rank_from_scores(X[:, fi["emb_cos"]], mask)[:3000] if gi.emb is not None else np.zeros(0, np.int32),
        "in_module": np.flatnonzero(mask & (X[:, fi["anc_in_module"]] > 0)),
        "dotted": np.flatnonzero(mask & (X[:, fi["anc_dotted"]] > 0)),
    }
    for i in out["rrf_inputs"]["in_module"][:5000]:
        out["module_of"].setdefault(int(i), gi.module_of[int(i)])
    for key in ("name", "anchor", "emb"):
        for i in out["rrf_inputs"][key][:3000]:
            out["module_of"].setdefault(int(i), gi.module_of[int(i)])
    return out


def gold_rank_of(rk: np.ndarray, g: int) -> int:
    w = np.flatnonzero(rk == g)
    return int(w[0]) + 1 if len(w) else 10**9


_CTX: dict = {}


def _init(ids):
    global _CTX
    tasks = [t for t in load_tasks() if t.instance_id in ids]
    _CTX = {c.task.instance_id: c for c in build_contexts(tasks)}


def _work_chunk(ids: list[str]) -> list[dict]:
    _init(set(ids))
    return [work(i) for i in ids]


def compute(procs: int = 12, force: bool = False) -> list[dict]:
    if CACHE.exists() and not force:
        return pickle.loads(CACHE.read_bytes())
    import json
    from src.dataio.loaders import DATA
    tg = {r["instance_id"]: r for r in map(json.loads, open(DATA / "derived" / "targets.jsonl"))}
    ids = [t.instance_id for t in load_tasks() if tg.get(t.instance_id, {}).get("target_nodes")]
    chunks = [ids[i::procs] for i in range(procs)]
    with ProcessPoolExecutor(procs) as ex:
        res = [r for ch in ex.map(_work_chunk, chunks) for r in ch]
    res = [r for r in res if r["n_gold"] > 0]
    order = {i: k for k, i in enumerate(ids)}
    res.sort(key=lambda r: order[r["iid"]])
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(res))
    return res


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    rs = compute(force=True)
    print(len(rs), "tasks cached ->", CACHE)
