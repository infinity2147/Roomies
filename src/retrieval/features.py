"""Per-(task, node) features shared by the supervised ranker (R3) and, later, the RL policy.

Everything is pure numpy over all graph nodes; callers mask out test nodes.
"""

from __future__ import annotations

import math

import numpy as np

from src.retrieval.context import REPO_PKG, TaskCtx, bfs_dist
from src.retrieval.text import STOP, name_tokens, tokenize

FEATURE_NAMES = [
    "bm25", "bm25_norm", "bm25_rank", "bm25_name_norm",
    "emb_cos", "emb_rank", "emb_max_anchor",
    "anc_short_idf", "anc_backtick", "anc_dotted", "anc_trace", "anc_in_module",
    "anc_parent", "anc_child", "n_anchor_children",
    "dist_anchor", "n_anchor_nbrs", "dist_bm25top",
    "log_in_deg", "log_out_deg", "kind", "is_private", "is_dunder", "depth",
    "in_repo_pkg", "log_text_len", "name_q_frac", "name_q_jacc", "module_bm25_max",
]


def _rank_pct(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rank of x among masked nodes, as fraction in [0,1] (0 = best)."""
    out = np.ones_like(x, dtype=np.float32)
    ids = np.flatnonzero(mask)
    order = ids[np.argsort(-x[ids], kind="stable")]
    out[order] = np.arange(len(order), dtype=np.float32) / max(len(order) - 1, 1)
    return out


def anchor_matches(ctx: TaskCtx) -> dict[str, np.ndarray]:
    gi, a = ctx.gi, ctx.anchors
    n = gi.n
    short_idf = np.zeros(n, dtype=np.float32)
    backtick = np.zeros(n, dtype=np.float32)
    dotted = np.zeros(n, dtype=np.float32)
    trace = np.zeros(n, dtype=np.float32)
    seeds: list[int] = []
    for anc in a.all_last():
        hits = gi.short_to_idx.get(anc) or []
        if not hits:
            continue
        w = math.log(1 + n / len(hits))
        short_idf[hits] += w
        if anc in a.backtick:
            backtick[hits] = np.maximum(backtick[hits], w)
        if anc in a.trace_funcs:
            trace[hits] = 1
        if len(hits) <= 25:
            seeds.extend(hits)
    for d in a.dotted:
        if d in gi.idx:
            dotted[gi.idx[d]] = 2
        suf = "." + d
        if len(d.split(".")) >= 2:
            for cand in gi.short_to_idx.get(d.rsplit(".", 1)[-1], []):
                if gi.names[cand].endswith(suf):
                    dotted[cand] = max(dotted[cand], 1)
                    seeds.append(cand)
    in_mod = np.zeros(n, dtype=np.float32)
    if a.modules:
        for i, m in enumerate(gi.module_of):
            if any(m == mm or m.endswith("." + mm) or mm.endswith("." + m) for mm in a.modules):
                in_mod[i] = 1
    return {"short_idf": short_idf, "backtick": backtick, "dotted": dotted, "trace": trace,
            "in_module": in_mod, "seeds": np.unique(np.array(seeds, dtype=np.int32))}


def r1_bm25(ctx: TaskCtx) -> np.ndarray:
    return ctx.gi.bm25_full.scores(tokenize(ctx.query))


def r2_embed(ctx: TaskCtx, am: dict | None = None, bm25: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Cosine to centroid of anchor-matched nodes (pseudo-query; no text encoder available).
    Falls back to BM25 top-5 as pseudo-relevant seeds. Returns (cos_centroid, max_cos_to_any_seed)."""
    gi = ctx.gi
    if gi.emb is None:
        z = np.zeros(gi.n, dtype=np.float32)
        return z, z
    am = am if am is not None else anchor_matches(ctx)
    seeds = am["seeds"]
    seeds = seeds[~gi.is_test[seeds]] if len(seeds) else seeds
    if len(seeds) == 0:
        bm25 = bm25 if bm25 is not None else r1_bm25(ctx)
        cand = np.where(gi.is_test, -np.inf, bm25)
        seeds = np.argsort(-cand)[:5]
    seeds = seeds[:50]
    cen = gi.emb[seeds].mean(0)
    cen /= max(np.linalg.norm(cen), 1e-8)
    cos = gi.emb @ cen
    mx = (gi.emb @ gi.emb[seeds].T).max(1)
    return cos.astype(np.float32), mx.astype(np.float32)


def build_features(ctx: TaskCtx) -> tuple[np.ndarray, np.ndarray]:
    """Returns (X [N, F], candidate mask [N])."""
    gi = ctx.gi
    n = gi.n
    mask = ~gi.is_test
    qtok = tokenize(ctx.query)
    qset = {t for t in qtok if t not in STOP}

    bm = gi.bm25_full.scores(qtok)
    bmn = gi.bm25_name.scores(qtok)
    am = anchor_matches(ctx)
    cos, mx = r2_embed(ctx, am, bm)

    seeds = am["seeds"]
    dist_a = bfs_dist(gi, list(seeds)) if len(seeds) else np.full(n, 4, dtype=np.int8)
    top_bm = np.argsort(-np.where(mask, bm, -np.inf))[:5]
    dist_b = bfs_dist(gi, list(top_bm))

    seed_set = np.zeros(n, dtype=bool)
    seed_set[seeds] = True
    n_anc_nbrs = np.array([seed_set[gi.undirected(i)].sum() for i in range(n)], dtype=np.float32)
    anc_parent = np.where(gi.parent >= 0, am["short_idf"][np.maximum(gi.parent, 0)], 0) * (gi.parent >= 0)
    child_max = np.zeros(n, dtype=np.float32)
    child_cnt = np.zeros(n, dtype=np.float32)
    for i in np.flatnonzero((gi.parent >= 0) & (am["short_idf"] > 0)):
        p = gi.parent[i]
        child_max[p] = max(child_max[p], am["short_idf"][i])
        child_cnt[p] += 1

    pkg = REPO_PKG.get(ctx.task.short, ctx.task.short)
    in_pkg = np.array([nm.split(".")[0] == pkg for nm in gi.names], dtype=np.float32)
    name_frac = np.zeros(n, dtype=np.float32)
    name_jac = np.zeros(n, dtype=np.float32)
    for i, s in enumerate(gi.short):
        toks = set(name_tokens(s))
        if toks:
            inter = len(toks & qset)
            name_frac[i] = inter / len(toks)
            name_jac[i] = inter / len(toks | qset) * 100
    # module-level BM25 evidence: best BM25 score among nodes of the same module
    mod_max: dict[str, float] = {}
    for i, m in enumerate(gi.module_of):
        if mask[i]:
            mod_max[m] = max(mod_max.get(m, 0.0), float(bm[i]))
    mod_bm = np.array([mod_max.get(m, 0.0) for m in gi.module_of], dtype=np.float32)
    bm_max = max(float(bm[mask].max()) if mask.any() else 0.0, 1e-6)

    feats = {
        "bm25": bm,
        "bm25_norm": bm / bm_max,
        "bm25_rank": _rank_pct(bm, mask),
        "bm25_name_norm": bmn / max(float(bmn[mask].max()) if mask.any() else 0.0, 1e-6),
        "emb_cos": cos,
        "emb_rank": _rank_pct(cos, mask),
        "emb_max_anchor": mx,
        "anc_short_idf": am["short_idf"],
        "anc_backtick": am["backtick"],
        "anc_dotted": am["dotted"],
        "anc_trace": am["trace"],
        "anc_in_module": am["in_module"],
        "anc_parent": anc_parent.astype(np.float32),
        "anc_child": child_max,
        "n_anchor_children": child_cnt,
        "dist_anchor": dist_a.astype(np.float32),
        "n_anchor_nbrs": n_anc_nbrs,
        "dist_bm25top": dist_b.astype(np.float32),
        "log_in_deg": np.log1p([len(x) for x in gi.in_adj]).astype(np.float32),
        "log_out_deg": np.log1p([len(x) for x in gi.out_adj]).astype(np.float32),
        "kind": gi.kind.astype(np.float32),
        "is_private": np.array([s.startswith("_") and not s.startswith("__") for s in gi.short], dtype=np.float32),
        "is_dunder": np.array([s.startswith("__") and s.endswith("__") for s in gi.short], dtype=np.float32),
        "depth": np.array([nm.count(".") for nm in gi.names], dtype=np.float32),
        "in_repo_pkg": in_pkg,
        "log_text_len": np.log1p([len(t) for t in gi.texts]).astype(np.float32),
        "name_q_frac": name_frac,
        "name_q_jacc": name_jac,
        "module_bm25_max": mod_bm / bm_max,
    }
    X = np.stack([np.asarray(feats[k], dtype=np.float32) for k in FEATURE_NAMES], axis=1)
    return X, mask
