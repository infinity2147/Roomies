"""B2: localization baselines R1 (BM25), R2 (embedding), R3 (LightGBM lambdarank, LORO), R3+G
(graph-smoothed R3). Writes experiments/<date>_b2_baselines/ and reports/localization_baselines.md.

Usage: .venv/bin/python -m src.retrieval.run_baselines [--seeds 3]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import lightgbm as lgb
import numpy as np

from src.dataio.loaders import ROOT
from src.eval.loc_metrics import file_metrics, node_metrics, rank_from_scores
from src.retrieval.context import TaskCtx, build_contexts
from src.retrieval.features import FEATURE_NAMES, build_features

FOLDS = ["fastapi", "rich", "requests", "httpx"]
ALPHAS = [0.0, 0.1, 0.2, 0.35, 0.5, 0.75]
LGB_PARAMS = dict(
    objective="lambdarank", metric="ndcg", ndcg_eval_at=[5, 10], learning_rate=0.05,
    num_leaves=15, min_data_in_leaf=20, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
    lambdarank_truncation_level=20, verbose=-1,
)
N_ROUNDS = 300


def train_rows(ctx: TaskCtx, X: np.ndarray, mask: np.ndarray, rng: np.random.Generator):
    """All positives + hard negatives (top BM25/emb/anchor) + random negatives."""
    y = np.zeros(len(mask), dtype=np.int32)
    y[ctx.targets] = 1
    cand = set(np.flatnonzero(mask & (y == 1)))
    fi = {f: i for i, f in enumerate(FEATURE_NAMES)}
    for col in ("bm25", "emb_cos", "anc_short_idf"):
        s = np.where(mask, X[:, fi[col]], -np.inf)
        cand.update(np.argsort(-s)[:100])
    pool = np.flatnonzero(mask)
    cand.update(rng.choice(pool, size=min(200, len(pool)), replace=False))
    rows = np.array(sorted(i for i in cand if mask[i]))
    return X[rows], y[rows]


def smooth(gi, s: np.ndarray, mask: np.ndarray, alpha: float) -> np.ndarray:
    """R3+G: s'(v) = z(v) + alpha * max_{u in N(v)} z(u) over the undirected call graph."""
    if alpha == 0:
        return s
    z = (s - s[mask].mean()) / (s[mask].std() + 1e-8)
    z = np.where(mask, z, z[mask].min())
    nb = np.array([z[gi.undirected(i)].max() if len(gi.undirected(i)) else z[mask].min() for i in range(gi.n)])
    return z + alpha * nb


def evaluate(ctx: TaskCtx, scores: np.ndarray, mask: np.ndarray) -> dict:
    ranked = rank_from_scores(scores, mask)
    m = node_metrics(ranked, ctx.targets)
    m.update(file_metrics(ranked, ctx.gi.module_of, ctx.target_modules))
    return m


def mean_metrics(rows: list[dict]) -> dict:
    keys = rows[0].keys()
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()

    ctxs = [c for c in build_contexts() if len(c.targets) > 0]
    print(f"tasks with >=1 target node: {len(ctxs)}")
    feats = {}
    for c in ctxs:
        feats[c.task.instance_id] = build_features(c)
    fi = {f: i for i, f in enumerate(FEATURE_NAMES)}

    per_task: dict[str, dict[str, dict]] = defaultdict(dict)  # system -> iid -> metrics
    r3_scores: dict[int, dict[str, np.ndarray]] = defaultdict(dict)  # seed -> iid -> scores
    for c in ctxs:
        X, mask = feats[c.task.instance_id]
        per_task["R1_bm25"][c.task.instance_id] = evaluate(c, X[:, fi["bm25"]], mask)
        per_task["R2_embed"][c.task.instance_id] = evaluate(c, X[:, fi["emb_cos"]], mask)

    importances = np.zeros(len(FEATURE_NAMES))
    for seed in range(args.seeds):
        rng = np.random.default_rng(seed)
        for fold in FOLDS:
            train = [c for c in ctxs if c.task.short != fold]
            test = [c for c in ctxs if c.task.short == fold]
            if not test:
                continue
            Xs, ys, groups = [], [], []
            for c in train:
                X, mask = feats[c.task.instance_id]
                xr, yr = train_rows(c, X, mask, rng)
                Xs.append(xr), ys.append(yr), groups.append(len(yr))
            ds = lgb.Dataset(np.concatenate(Xs), np.concatenate(ys), group=groups, feature_name=FEATURE_NAMES)
            model = lgb.train({**LGB_PARAMS, "seed": seed}, ds, num_boost_round=N_ROUNDS)
            importances += model.feature_importance("gain")
            for c in test:
                X, _ = feats[c.task.instance_id]
                r3_scores[seed][c.task.instance_id] = model.predict(X)
        print(f"seed {seed} done")

    # R3 and R3+G (alpha per fold chosen on out-of-fold predictions of the other folds)
    seed_metrics: dict[str, list[dict]] = defaultdict(list)
    for seed in range(args.seeds):
        alpha_mrr = defaultdict(dict)  # fold -> alpha -> mean mrr
        for fold in FOLDS:
            for a in ALPHAS:
                ms = []
                for c in ctxs:
                    if c.task.short == fold:
                        _, mask = feats[c.task.instance_id]
                        s = smooth(c.gi, r3_scores[seed][c.task.instance_id], mask, a)
                        ms.append(evaluate(c, s, mask)["mrr"])
                if ms:
                    alpha_mrr[fold][a] = (float(np.mean(ms)), len(ms))
        for sysname in ("R3_ranker", "R3+G"):
            rows = {}
            for c in ctxs:
                iid, fold = c.task.instance_id, c.task.short
                _, mask = feats[iid]
                a = 0.0
                if sysname == "R3+G":
                    tot = {al: sum(alpha_mrr[f][al][0] * alpha_mrr[f][al][1] for f in alpha_mrr if f != fold) for al in ALPHAS}
                    a = max(tot, key=tot.get)
                rows[iid] = evaluate(c, smooth(c.gi, r3_scores[seed][iid], mask, a), mask)
                rows[iid]["alpha"] = a
            seed_metrics[sysname].append(rows)

    # aggregate
    def by_repo(rows: dict[str, dict]) -> dict[str, dict]:
        out = {"ALL": mean_metrics(list(rows.values()))}
        for fold in FOLDS:
            sub = [m for iid, m in rows.items() if iid.startswith(fold + "_")]
            if sub:
                out[fold] = mean_metrics(sub)
        return out

    results: dict[str, dict] = {}
    for sysname in ("R1_bm25", "R2_embed"):
        results[sysname] = {"mean": by_repo(per_task[sysname]), "std": None}
    for sysname, runs in seed_metrics.items():
        agg = [by_repo(r) for r in runs]
        mean = {g: {k: float(np.mean([a[g][k] for a in agg])) for k in agg[0][g]} for g in agg[0]}
        std = {g: {k: float(np.std([a[g][k] for a in agg])) for k in agg[0][g]} for g in agg[0]}
        results[sysname] = {"mean": mean, "std": std}

    date = dt.date.today().isoformat()
    exp = ROOT / "experiments" / f"{date}_b2_baselines"
    exp.mkdir(parents=True, exist_ok=True)
    imp = dict(sorted(zip(FEATURE_NAMES, (importances / importances.sum()).round(4).tolist()), key=lambda kv: -kv[1]))
    (exp / "metrics.json").write_text(json.dumps({"results": results, "feature_importance": imp, "n_tasks": len(ctxs)}, indent=1))
    (exp / "config.yaml").write_text(
        f"folds: {FOLDS}\nseeds: {args.seeds}\nlgb_params: {json.dumps(LGB_PARAMS)}\nn_rounds: {N_ROUNDS}\n"
        f"alphas: {ALPHAS}\ncandidates: all non-test graph nodes\nfeatures: {FEATURE_NAMES}\n"
    )

    cols = ["recall@1", "recall@5", "recall@10", "recall@20", "hit@5", "mrr", "ndcg10", "file_hit@1", "file_hit@3"]
    lines = [f"# Localization baselines (LORO, {len(ctxs)} tasks with >=1 gold node, {args.seeds} seeds for R3)\n",
             "Candidates = all non-test graph nodes. Node-level metrics vs B1 gold nodes; file = module-level.\n"]
    for group in ["ALL", *FOLDS]:
        n_g = len(ctxs) if group == "ALL" else sum(c.task.short == group for c in ctxs)
        lines.append(f"\n## {group} (n={n_g})\n")
        lines.append("| system | " + " | ".join(cols) + " |")
        lines.append("|---|" + "---|" * len(cols))
        for sysname, r in results.items():
            if group not in r["mean"]:
                continue
            cells = []
            for k in cols:
                mu = r["mean"][group][k]
                sd = r["std"][group][k] if r["std"] else None
                cells.append(f"{mu:.3f}" + (f"±{sd:.3f}" if sd else ""))
            lines.append(f"| {sysname} | " + " | ".join(cells) + " |")
    lines.append("\n## Feature importance (gain, R3, summed over folds × seeds)\n")
    lines += [f"- {k}: {v:.3f}" for k, v in list(imp.items())[:15]]
    report = "\n".join(lines) + "\n"
    (ROOT / "reports" / "localization_baselines.md").write_text(report)
    (exp / "notes.md").write_text("Hypothesis: supervised ranker > BM25/embedding; graph smoothing adds on top.\n\n" + report)
    print(report)


if __name__ == "__main__":
    main()
