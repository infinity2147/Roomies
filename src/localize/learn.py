"""Train + evaluate the graph-locate rerankers and expansion policy (CPU, seeded).

  python -m src.localize.learn --mode cv      # grouped-by-repo CV on the train pool (public valid + proxy train half)
  python -m src.localize.learn --mode final   # train on whole train pool, evaluate ONCE on the proxy TEST half, export weights.json
Everything the models see at training time is from split=="train" (proxy eval half is never touched in cv mode).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from multiprocessing import Pool

import numpy as np

from src.localize.common import CACHE, ROOT, SKILL, load_cq, load_gl, tasks

gl = load_gl()
FI, NF, FEATURES = gl.FI, gl.NF, gl.FEATURES
NOGRAPH = {'indeg', 'outdeg', 'nbr_max', 'nbr_cnt'}  # graph-derived static features, masked in the no-graph ablation
BUDGETS = [0, 1, 2, 5, 10, 20]
KS = [1, 3, 5, 10]
_C = {}


def cq(tid):
    if tid not in _C:
        _C[tid] = load_cq(tid)
        import pickle
        d = pickle.load(open(CACHE / (tid + ".pkl"), "rb"))
        _C[tid].gold = set(d["gold_funcs"])
        _C[tid].gold_files = d["gold_files"]
    return _C[tid]


# ------------------------------------------------------------------ metrics
def ndcg(rank, gold, k=10):
    if not gold:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, n in enumerate(rank[:k]) if n in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return dcg / idcg


def file_order(c, rank):
    out = []
    for n in rank:
        f = c.ix.nodes[n].file
        if f not in out:
            out.append(f)
    return out


def metrics(c, rank, revealed=None):
    m = {}
    if c.gold:
        for k in KS:
            m["fn_hit@%d" % k] = float(any(n in c.gold for n in rank[:k]))
        m["fn_recall@10"] = len(c.gold & set(rank[:10])) / len(c.gold)
        m["ndcg@10"] = ndcg(rank, c.gold)
        if revealed is not None:
            m["reach"] = len(c.gold & set(revealed)) / len(c.gold)
    if c.gold_files:
        fo = file_order(c, rank)
        for k in KS:
            m["file_hit@%d" % k] = float(any(f in c.gold_files for f in fo[:k]))
    return m


# ------------------------------------------------------------------ methods
def rank_bm25(c):
    order = sorted(range(len(c.stat)), key=lambda i: (-c.stat[i][0], i))
    return order[:50], None


def rank_graph(c, B, pol, scorer, S=gl.POOL, nograph=False):
    if nograph:  # static features only, wide candidate set (no expansion, no dynamic features)
        cand = c.seeds(100)
        sc = sorted(((scorer(gl.State.feat_static(c, n)), n) for n in cand), key=lambda x: (-x[0], x[1]))
        return [n for _, n in sc[:50]], cand
    st = gl.run_budget(c, B, pol, S)
    r = gl.rank_state(st, scorer, 50)
    return [n for _, n in r], list(st.info)


def _feat_static(c, n):
    f = list(c.static(n))
    for nm in NOGRAPH:
        f[FI[nm]] = 0.0
    return f + [0.0] * (NF - len(f))


gl.State.feat_static = staticmethod(_feat_static)

HAND = gl.Scorer()
HANDPOL = gl.vec(gl.HAND_POLICY)


def eval_method(tids, fn, budgets=BUDGETS):
    """fn(c, B) -> (rank, revealed). returns {B: mean metrics}"""
    res = {}
    for B in budgets:
        acc = {}
        cnt = {}
        for t in tids:
            c = cq(t)
            r, rev = fn(c, B)
            for k, v in metrics(c, r, rev).items():
                acc[k] = acc.get(k, 0.0) + v
                cnt[k] = cnt.get(k, 0) + 1
        res[B] = {k: acc[k] / cnt[k] for k in acc}
        res[B]["n_fn"] = cnt.get("ndcg@10", 0)
        res[B]["n_file"] = cnt.get("file_hit@1", 0)
    return res


# ------------------------------------------------------------------ scorer training
def make_groups(tids, pol, budgets=(0, 5, 10, 20), nograph=False):
    X, y, g = [], [], []
    for t in tids:
        c = cq(t)
        if not c.gold:
            continue
        for B in (budgets if not nograph else (0,)):
            if nograph:
                cand = c.seeds(100)
                rows = [_feat_static(c, n) for n in cand]
            else:
                st = gl.run_budget(c, B, pol)
                cand = list(st.info)
                rows = [st.feat(n) for n in cand]
            lab = [1.0 if n in c.gold else 0.0 for n in cand]
            if sum(lab) == 0:
                continue
            X.append(np.array(rows))
            y.append(np.array(lab))
            g.append((t, B))
    return X, y, g


def train_linear_lambdarank(X, y, init, iters=200, lr=0.05, l2=1e-3, mask=None, seed=0):
    rng = np.random.RandomState(seed)
    w = np.array(init, dtype=float)
    m1 = np.zeros_like(w)
    m2 = np.zeros_like(w)
    mk = np.ones_like(w) if mask is None else np.array(mask, float)
    sub = []
    for Xi, yi in zip(X, y):
        pos = np.where(yi > 0)[0]
        neg = np.where(yi == 0)[0]
        sub.append((Xi, pos, neg))
    for it in range(1, iters + 1):
        grad = np.zeros_like(w)
        for Xi, pos, neg in sub:
            s = Xi @ (w * mk)
            order = np.argsort(-s, kind="stable")
            rank = np.empty(len(s), int)
            rank[order] = np.arange(len(s))
            idcg = sum(1.0 / math.log2(i + 2) for i in range(min(10, len(pos))))
            disc = np.where(rank < 10, 1.0 / np.log2(rank + 2), 0.0)
            ds = s[pos][:, None] - s[neg][None, :]
            dn = np.abs(disc[pos][:, None] - disc[neg][None, :]) / idcg
            lam = -dn / (1.0 + np.exp(np.clip(ds, -30, 30)))  # d loss / d ds
            # grad wrt w: sum lam * (x_pos - x_neg)
            gp = lam.sum(1)
            gn = lam.sum(0)
            grad += (gp[:, None] * Xi[pos]).sum(0) - (gn[:, None] * Xi[neg]).sum(0)
        grad = grad / max(1, len(sub)) + l2 * w
        grad *= mk
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad * grad
        w -= lr * (m1 / (1 - 0.9 ** it)) / (np.sqrt(m2 / (1 - 0.999 ** it)) + 1e-8)
    return (w * mk).tolist()


def train_lgbm(X, y, seed=0, n_est=80):
    import lightgbm as lgb
    Xa = np.vstack(X)
    ya = np.concatenate(y)
    grp = [len(a) for a in X]
    mdl = lgb.LGBMRanker(objective="lambdarank", n_estimators=n_est, learning_rate=0.08, num_leaves=7, min_child_samples=20,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=seed,
                         lambdarank_truncation_level=10, verbose=-1, n_jobs=4)
    mdl.fit(Xa, ya, group=grp)
    trees = [t["tree_structure"] for t in mdl.booster_.dump_model()["tree_info"]]
    return {"type": "gbdt", "trees": trees}, mdl


# ------------------------------------------------------------------ REINFORCE policy
_W = {}


def _episode_grad(args):
    t, pol, scorer_w, seed, K, Bs = args
    c = cq(t)
    rng = random.Random(seed)
    scorer = gl.Scorer({"type": "linear", "w": scorer_w})
    eps = []
    for _ in range(K):
        B = rng.choice(Bs)
        col = []
        st = gl.run_budget(c, B, pol, rng=rng, collect=col)
        r = gl.rank_state(st, scorer, 10)
        R = ndcg([n for _, n in r], c.gold)
        eps.append((R, col))
    base = sum(e[0] for e in eps) / len(eps)
    grad = np.zeros(NF)
    for R, col in eps:
        A = R - base
        if abs(A) < 1e-9:
            continue
        for fs, ps, j in col:
            F = np.array(fs)
            p = np.array(ps)
            grad += A * (F[j] - p @ F)
    return grad / K, base


def train_policy(tids, scorer_w, init, epochs=12, lr=0.1, K=6, Bs=(2, 5, 10), seed=0, procs=4, log=None):
    tids = [t for t in tids if cq(t).gold]
    w = np.array(init, float)
    m1 = np.zeros(NF)
    m2 = np.zeros(NF)
    mask = np.array([1.0 if i >= 0 else 0.0 for i in range(NF)])
    step = 0
    with Pool(procs) as pool:
        for ep in range(epochs):
            args = [(t, w.tolist(), scorer_w, seed * 100003 + ep * 1009 + i, K, Bs) for i, t in enumerate(tids)]
            out = pool.map(_episode_grad, args, chunksize=4)
            grad = sum(o[0] for o in out) / len(out)
            rew = sum(o[1] for o in out) / len(out)
            step += 1
            m1 = 0.9 * m1 + 0.1 * grad
            m2 = 0.999 * m2 + 0.001 * grad * grad
            w += lr * (m1 / (1 - 0.9 ** step)) / (np.sqrt(m2 / (1 - 0.999 ** step)) + 1e-8)  # ascent
            if log:
                log("    reinforce epoch %d mean-reward(ndcg@10, sampled) %.4f" % (ep, rew))
    return w.tolist()


# ------------------------------------------------------------------ folds
def make_folds(T):
    """grouped by repo: fastapi and rich are one fold each (leave-one-repo-out); other repos balanced into 4 folds"""
    by = {}
    for t in T:
        by.setdefault(t["repo"], []).append(t["id"])
    big = [r for r in by if len(by[r]) >= 40]
    folds = [list(by[r]) for r in sorted(big)]
    rest = sorted((r for r in by if r not in big), key=lambda r: -len(by[r]))
    small = [[] for _ in range(4)]
    for r in rest:
        min(small, key=len).extend(by[r])
    return folds + small


def summarize(res):
    return {str(B): {k: round(v, 4) for k, v in d.items()} for B, d in res.items()}


def pooled(parts):
    """merge per-fold {B:{metric: mean, n_*}} weighted by n"""
    out = {}
    for B in parts[0]:
        d = {}
        for k in parts[0][B]:
            if k.startswith("n_"):
                d[k] = sum(p[B][k] for p in parts)
        for k in parts[0][B]:
            if k.startswith("n_"):
                continue
            n = "n_file" if k.startswith("file") else "n_fn"
            tot = sum(p[B][n] for p in parts)
            d[k] = sum(p[B][k] * p[B][n] for p in parts) / max(1, tot)
        out[B] = d
    return out


def fit_all(train_ids, args, log):
    """fit all learned components on train_ids; returns dict of components"""
    comp = {}
    X, y, g = make_groups(train_ids, HANDPOL)
    log("  scorer data: %d groups, %d rows" % (len(X), sum(len(a) for a in X)))
    hw = gl.vec(gl.HAND_SCORER)
    comp["lin"] = {"type": "linear", "w": train_linear_lambdarank(X, y, hw)}
    comp["gbdt"], _ = train_lgbm(X, y, seed=args.seed)
    Xn, yn, _ = make_groups(train_ids, HANDPOL, nograph=True)
    mask = [1.0 if (i < gl.STATIC_N and FEATURES[i] not in NOGRAPH) else 0.0 for i in range(NF)]
    comp["lin_nograph"] = {"type": "linear", "w": train_linear_lambdarank(Xn, yn, hw, mask=mask)}
    comp["gbdt_nograph"], _ = train_lgbm(Xn, yn, seed=args.seed)
    log("  training REINFORCE policy")
    comp["policy"] = {"w": train_policy(train_ids, comp["lin"]["w"], gl.vec(gl.HAND_POLICY), epochs=args.epochs,
                                        seed=args.seed, procs=args.procs, log=log)}
    return comp


def eval_components(ids, comp):
    S = gl.Scorer
    sc = {k: S(comp[k]) for k in ("lin", "gbdt", "lin_nograph", "gbdt_nograph")}
    pol = comp["policy"]["w"]
    R = {}
    R["bm25"] = eval_method(ids, lambda c, B: rank_bm25(c), [0])
    R["graph_hand"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, HAND))
    R["hand_nograph"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, HAND, nograph=True), [0])
    R["lambdarank_lin"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, sc["lin"]))
    R["lambdarank_gbdt"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, sc["gbdt"]))
    R["reinforce_lin"] = eval_method(ids, lambda c, B: rank_graph(c, B, pol, sc["lin"]))
    R["reinforce_gbdt"] = eval_method(ids, lambda c, B: rank_graph(c, B, pol, sc["gbdt"]))
    R["nograph_lin"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, sc["lin_nograph"], nograph=True), [0])
    R["nograph_gbdt"] = eval_method(ids, lambda c, B: rank_graph(c, B, HANDPOL, sc["gbdt_nograph"], nograph=True), [0])
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["cv", "final"], required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "results" / "graph_locate"))
    a = ap.parse_args()
    random.seed(a.seed)
    np.random.seed(a.seed)
    T = [t for t in tasks() if (CACHE / (t["id"] + ".pkl")).exists()]
    train = [t for t in T if t["split"] == "train"]
    test = [t for t in T if t["split"] == "test"]
    (ROOT / "results" / "graph_locate").mkdir(parents=True, exist_ok=True)

    def log(s):
        print(s, flush=True)

    if a.mode == "cv":
        folds = make_folds(train)
        per = {}
        parts = {}
        for fi, fold in enumerate(folds):
            fs = set(fold)
            tr = [t["id"] for t in train if t["id"] not in fs]
            log("fold %d: test=%d train=%d" % (fi, len(fold), len(tr)))
            comp = fit_all(tr, a, log)
            R = eval_components(fold, comp)
            for m, res in R.items():
                parts.setdefault(m, []).append(res)
            per[fi] = {"repos": sorted({t["repo"] for t in train if t["id"] in fs}), "policy": comp["policy"],
                       "lin": comp["lin"]}
        out = {"mode": "cv_grouped_by_repo", "folds": per,
               "pooled": {m: summarize(pooled(p)) for m, p in parts.items()}}
        # subsets: public vs proxy-train
        for srcname in ("public", "proxy"):
            ids = {t["id"] for t in train if t["src"] == srcname}
            sub = {}
            # recompute by re-running is costly; store only pooled
        json.dump(out, open(a.out + "/cv.json", "w"), indent=1)
        log("saved cv.json")
    else:
        tr = [t["id"] for t in train]
        log("final: train=%d test=%d" % (len(tr), len(test)))
        comp = fit_all(tr, a, log)
        R = eval_components([t["id"] for t in test], comp)
        out = {"mode": "final_test_half", "n_test": len(test), "results": {m: summarize(r) for m, r in R.items()},
               "policy": comp["policy"], "lin": comp["lin"], "features": FEATURES}
        json.dump(out, open(a.out + "/test.json", "w"), indent=1)
        json.dump(comp, open(a.out + "/components.json", "w"))
        log("saved test.json")


if __name__ == "__main__":
    main()
