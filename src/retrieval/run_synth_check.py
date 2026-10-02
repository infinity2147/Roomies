"""B5 distribution check (Gate B): does synthetic localization data help the ranker on held-out
REAL repos? LORO over {fastapi, rich, requests}; embedding features removed everywhere (synthetic
packages have no organizer embeddings). Systems: R1 BM25, R3-real, R3-real+synth, R3-synth.

Usage: .venv/bin/python -m src.retrieval.run_synth_check [--seeds 3] [--max-mention-rate auto]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

import lightgbm as lgb
import numpy as np

from src.dataio.loaders import DATA, ROOT, Task
from src.eval.loc_metrics import file_metrics, node_metrics, rank_from_scores
from src.retrieval.context import TaskCtx, build_contexts, graph_index
from src.retrieval.features import FEATURE_NAMES, build_features
from src.retrieval.run_baselines import LGB_PARAMS, N_ROUNDS, train_rows
from src.retrieval.text import extract_anchors

FOLDS = ["fastapi", "rich", "requests"]
NOEMB = [i for i, f in enumerate(FEATURE_NAMES) if not f.startswith("emb_")]


def synth_contexts(rows: list[dict]) -> list[TaskCtx]:
    out = []
    for r in rows:
        gi = graph_index("path:" + str(DATA / "derived" / r["graph"]))
        t = Task(instance_id=r["instance_id"], repo=r["package"], base_commit="", patch="", test_patch="",
                 problem_statement=r["issue"], hints_text="", created_at="")
        tg = np.array([gi.idx[n] for n in r["target_nodes"] if n in gi.idx], dtype=np.int32)
        if len(tg):
            out.append(TaskCtx(t, gi, r["issue"], extract_anchors(r["issue"]), tg, set()))
    return out


def mention_rate(ctxs: list[TaskCtx]) -> float:
    hit = 0
    for c in ctxs:
        shorts = {c.gi.short[i] for i in c.targets}
        hit += any(s in c.query for s in shorts)
    return hit / max(len(ctxs), 1)


def evaluate(c: TaskCtx, scores, mask) -> dict:
    ranked = rank_from_scores(scores, mask)
    m = node_metrics(ranked, c.targets)
    m.update(file_metrics(ranked, c.gi.module_of, c.target_modules))
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    real = [c for c in build_contexts() if len(c.targets) and c.task.short in FOLDS]
    rows = [json.loads(l) for l in open(DATA / "derived" / "synth_issues.jsonl")]
    synth_all = synth_contexts([r for r in rows if r.get("issue")])
    real_rate = mention_rate(real)
    # calibrate: keep synthetic issues so that the name-mention rate matches the real tasks
    rng = np.random.default_rng(0)
    named = [c for c in synth_all if mention_rate([c]) == 1.0]
    unnamed = [c for c in synth_all if mention_rate([c]) == 0.0]
    k = int(round(real_rate / max(1 - real_rate, 1e-6) * len(unnamed)))
    synth = unnamed + list(rng.permutation(np.array(named, dtype=object))[: min(k, len(named))])
    print(f"real tasks={len(real)} name-mention={real_rate:.2f} | synth issues={len(synth_all)} raw mention={mention_rate(synth_all):.2f} "
          f"-> calibrated {len(synth)} (mention={mention_rate(synth):.2f})")

    feats = {id(c): build_features(c) for c in real + synth}
    results = defaultdict(lambda: defaultdict(list))  # system -> fold -> list of per-task metric dicts (all seeds)
    for c in real:
        X, mask = feats[id(c)]
        results["R1_bm25"][c.task.short].append(evaluate(c, X[:, FEATURE_NAMES.index("bm25")], mask))
    for seed in range(a.seeds):
        rs = np.random.default_rng(seed)
        for fold in FOLDS:
            test = [c for c in real if c.task.short == fold]
            train_real = [c for c in real if c.task.short != fold]
            for sysname, train in (("R3_real", train_real), ("R3_real+synth", train_real + synth), ("R3_synth", synth)):
                Xs, ys, gs = [], [], []
                for c in train:
                    X, mask = feats[id(c)]
                    xr, yr = train_rows(c, X, mask, rs)
                    Xs.append(xr[:, NOEMB]), ys.append(yr), gs.append(len(yr))
                ds = lgb.Dataset(np.concatenate(Xs), np.concatenate(ys), group=gs,
                                 feature_name=[FEATURE_NAMES[i] for i in NOEMB])
                model = lgb.train({**LGB_PARAMS, "seed": seed}, ds, num_boost_round=N_ROUNDS)
                for c in test:
                    X, mask = feats[id(c)]
                    results[sysname][fold].append(evaluate(c, model.predict(X[:, NOEMB]), mask))
    cols = ["recall@1", "recall@5", "mrr", "file_hit@1", "file_hit@3"]
    lines = [f"# B5 distribution check (LORO on real repos, no embedding features, {a.seeds} seeds)\n",
             f"real tasks {len(real)} (target-name mention rate {real_rate:.2f}); synthetic issues used {len(synth)} "
             f"(calibrated mention rate {mention_rate(synth):.2f}) from {len({c.task.repo for c in synth})} packages\n",
             "| system | fold | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    summary = {}
    for sysname, by_fold in results.items():
        for fold in FOLDS + ["ALL"]:
            ms = [m for f_, lst in by_fold.items() for m in lst] if fold == "ALL" else by_fold[fold]
            vals = {k: float(np.mean([m[k] for m in ms])) for k in cols}
            summary[(sysname, fold)] = vals
            lines.append(f"| {sysname} | {fold} | " + " | ".join(f"{vals[k]:.3f}" for k in cols) + " |")
    wins = sum(summary[("R3_real+synth", f)]["mrr"] > summary[("R1_bm25", f)]["mrr"] for f in FOLDS)
    gain = sum(summary[("R3_real+synth", f)]["mrr"] > summary[("R3_real", f)]["mrr"] for f in FOLDS)
    lines.append(f"\nGate B criterion: R3_real+synth beats BM25 (MRR) on {wins}/3 folds; beats R3_real on {gain}/3 folds.")
    report = "\n".join(lines) + "\n"
    (ROOT / "reports" / "b5_synth_check.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
