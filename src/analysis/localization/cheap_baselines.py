"""Step 3: cheap learned/tuned baselines vs BM25, LORO over {fastapi, rich, requests}; httpx = train-on-all.

Systems
  RRF(-emb)  : reciprocal-rank fusion of BM25-full, BM25-name, anchor-idf (+ emb cosine), plus bonuses for nodes in an
               issue-mentioned module / exact dotted match. Weights grid-searched on the training repos (MRR).
  RR-LGB     : 2-stage LambdaMART re-rank of a pool = BM25 top-50 U 1-hop(BM25 top-10) U anchor seeds;
               29 base features (or 26 without embeddings) + 9 pool/graph features. 3 seeds.
Everything outside the pool keeps BM25 order.
Usage: .venv/bin/python -m src.analysis.localization.cheap_baselines [--seeds 3]
"""

from __future__ import annotations

import argparse
import itertools
import json

import lightgbm as lgb
import numpy as np

from src.analysis.localization.common import CACHE, EXTRA_FEATS, compute
from src.eval.loc_metrics import file_metrics, node_metrics
from src.retrieval.features import FEATURE_NAMES

FOLDS = ["fastapi", "rich", "requests"]
ALLF = FEATURE_NAMES + EXTRA_FEATS
NOEMB = [i for i, f in enumerate(ALLF) if not f.startswith("emb_")]
PARAMS = dict(objective="lambdarank", metric="ndcg", ndcg_eval_at=[5], learning_rate=0.05, num_leaves=7,
              min_data_in_leaf=20, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
              lambdarank_truncation_level=20, verbose=-1, num_threads=4)
ROUNDS = 200


def evaluate(r: dict, ranked: np.ndarray) -> dict:
    m = node_metrics(ranked, r["targets"])
    m.update(file_metrics(ranked, _ModView(r), r["target_modules"]))
    return m


class _ModView:
    def __init__(self, r):
        self.d = r["module_of"]

    def __getitem__(self, i):
        return self.d.get(int(i), f"?{i}")


def bm25_ranked(r):
    return r["bm25_rank_top"]


def with_pool_order(r: dict, pool_order: np.ndarray) -> np.ndarray:
    rest = r["bm25_rank_top"][~np.isin(r["bm25_rank_top"], pool_order)]
    return np.concatenate([pool_order, rest])


# ---------------- RRF ----------------
def rrf_prep(r: dict):
    src = r["rrf_inputs"]
    U = np.unique(np.concatenate([src[k] for k in ("bm25", "name", "anchor", "emb", "in_module", "dotted")]).astype(np.int64))
    pos = {int(v): i for i, v in enumerate(U)}
    ranks = {}
    for k in ("bm25", "name", "anchor", "emb"):
        a = np.full(len(U), np.inf)
        for j, v in enumerate(src[k]):
            a[pos[int(v)]] = j + 1
        ranks[k] = a
    mod = np.isin(U, src["in_module"]).astype(float)
    dot = np.isin(U, src["dotted"]).astype(float)
    gold = np.isin(U, r["targets"])
    return U, ranks, mod, dot, gold


def rrf_scores(prep, k, wn, wa, we, bm, bd):
    U, ranks, mod, dot, _ = prep
    s = 1 / (k + ranks["bm25"]) + wn / (k + ranks["name"]) + wa / (k + ranks["anchor"]) + we / (k + ranks["emb"])
    return s + (bm * mod + bd * dot) / (k + 1)


def rrf_mrr(prep, params):
    s = rrf_scores(prep, *params)
    gold = prep[4]
    if not gold.any():
        return 0.0
    order = np.argsort(-s, kind="stable")
    first = np.flatnonzero(gold[order])[0]
    return 1 / (first + 1)


GRID_NOEMB = list(itertools.product([10, 30, 60], [0, .25, .5, 1], [0, .25, .5, 1], [0], [0, .5, 1], [0, .5, 1]))
GRID_EMB = list(itertools.product([10, 30, 60], [0, .25, .5, 1], [0, .25, .5, 1], [.25, .5], [0, .5, 1], [0, .5, 1]))


def run_rrf(R, preps, grid, fold_of):
    rows, chosen = {}, {}
    for fold in FOLDS + ["httpx"]:
        test = [r for r in R if fold_of(r) == fold]
        train = [r for r in R if r["repo"] in FOLDS and r["repo"] != fold]
        if not test:
            continue
        best = max(grid, key=lambda p: np.mean([rrf_mrr(preps[r["iid"]], p) for r in train]))
        chosen[fold] = best
        for r in test:
            U = preps[r["iid"]][0]
            order = U[np.argsort(-rrf_scores(preps[r["iid"]], *best), kind="stable")]
            rest = r["bm25_rank_top"][~np.isin(r["bm25_rank_top"], order)]
            rows[r["iid"]] = evaluate(r, np.concatenate([order, rest]))
    return rows, chosen


# ---------------- 2-stage LGB ----------------
def run_lgb(R, cols, seed, fold_of):
    rows = {}
    for fold in FOLDS + ["httpx"]:
        test = [r for r in R if fold_of(r) == fold]
        train = [r for r in R if r["repo"] in FOLDS and r["repo"] != fold and r["pool_y"].sum() > 0]
        if not test:
            continue
        X = np.concatenate([r["pool_X"][:, cols] for r in train])
        y = np.concatenate([r["pool_y"] for r in train])
        ds = lgb.Dataset(X, y, group=[len(r["pool_y"]) for r in train])
        model = lgb.train({**PARAMS, "seed": seed}, ds, num_boost_round=ROUNDS)
        for r in test:
            s = model.predict(r["pool_X"][:, cols])
            order = r["pool"][np.argsort(-s, kind="stable")]
            rows[r["iid"]] = evaluate(r, with_pool_order(r, order))
    return rows


def agg(rows: dict, R, repo=None):
    ids = [r["iid"] for r in R if repo is None or r["repo"] == repo]
    ks = ["recall@1", "recall@5", "hit@5", "mrr", "file_hit@1", "file_hit@3"]
    return {k: float(np.mean([rows[i][k] for i in ids])) for k in ks}


def paired_boot(a: dict, b: dict, key="mrr", n=5000, seed=0):
    ids = sorted(a)
    d = np.array([a[i][key] - b[i][key] for i in ids])
    rng = np.random.default_rng(seed)
    bs = rng.choice(d, size=(n, len(d))).mean(1)
    return float(d.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    R = compute()
    fold_of = lambda r: r["repo"]
    systems: dict[str, list[dict]] = {}
    systems["BM25"] = [{r["iid"]: evaluate(r, bm25_ranked(r)) for r in R}]
    preps = {r["iid"]: rrf_prep(r) for r in R}
    rr, ch1 = run_rrf(R, preps, GRID_NOEMB, fold_of)
    systems["RRF-noemb (tuned LORO)"] = [rr]
    rr2, ch2 = run_rrf(R, preps, GRID_EMB, fold_of)
    systems["RRF+emb (tuned LORO)"] = [rr2]
    systems["RR-LGB pool, no-emb"] = [run_lgb(R, NOEMB, s, fold_of) for s in range(a.seeds)]
    systems["RR-LGB pool, all feats"] = [run_lgb(R, list(range(len(ALLF))), s, fold_of) for s in range(a.seeds)]
    # pool oracle for reference
    systems["(oracle re-rank of pool)"] = [{r["iid"]: evaluate(r, with_pool_order(
        r, np.concatenate([r["pool"][r["pool_y"] == 1], r["pool"][r["pool_y"] == 0]]))) for r in R}]

    out = [f"## Cheap baselines (LORO over fastapi/rich/requests, httpx trained on all three; {a.seeds} seeds for LGB)\n"]
    ks = ["recall@1", "recall@5", "hit@5", "mrr", "file_hit@1", "file_hit@3"]
    for repo in (None, "fastapi", "rich", "requests", "httpx"):
        n = sum(1 for r in R if repo is None or r["repo"] == repo)
        out.append(f"\n### {repo or 'ALL'} (n={n})\n")
        out.append("| system | " + " | ".join(ks) + " |\n|---|" + "---|" * len(ks))
        for name, runs in systems.items():
            ag = [agg(x, R, repo) for x in runs]
            cells = []
            for k in ks:
                v = [g[k] for g in ag]
                cells.append(f"{np.mean(v):.3f}" + (f"±{np.std(v):.3f}" if len(v) > 1 else ""))
            out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append("\n### Paired bootstrap vs BM25 (ALL, seed 0 for LGB): ΔMRR and ΔRecall@5 [95% CI]\n")
    for name, runs in systems.items():
        if name == "BM25":
            continue
        dm = paired_boot(runs[0], systems["BM25"][0], "mrr")
        dr = paired_boot(runs[0], systems["BM25"][0], "recall@5")
        out.append(f"- {name}: ΔMRR {dm[0]:+.3f} [{dm[1]:+.3f},{dm[2]:+.3f}], ΔR@5 {dr[0]:+.3f} [{dr[1]:+.3f},{dr[2]:+.3f}]")
    out.append(f"\nRRF chosen params (k, w_name, w_anchor, w_emb, bonus_module, bonus_dotted) per held-out fold: "
               f"no-emb {ch1}; emb {ch2}")
    text = "\n".join(out) + "\n"
    (CACHE.parent / "cheap_baselines.md").write_text(text)
    (CACHE.parent / "cheap_baselines.json").write_text(json.dumps(
        {k: [agg(x, R) for x in v] for k, v in systems.items()}, indent=1))
    print(text)


if __name__ == "__main__":
    main()
