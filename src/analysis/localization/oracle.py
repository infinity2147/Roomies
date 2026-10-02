"""Step 1: oracle / upper-bound analyses (no learning). Prints markdown tables.

Usage: .venv/bin/python -m src.analysis.localization.oracle
"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np

from src.analysis.localization.common import CACHE, KS_EXP, NS, compute


def boot_ci(x, n=2000, seed=0):
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    bs = rng.choice(x, size=(n, len(x))).mean(1)
    return float(x.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def fmt(x):
    m, lo, hi = boot_ci(x)
    return f"{m:.3f} [{lo:.2f},{hi:.2f}]"


def main() -> None:
    R = compute()
    n = len(R)
    out = [f"## Oracle analyses (n={n} tasks with >=1 gold node; 95% bootstrap CI)\n"]
    out.append("### (a) BM25 top-N recall / hit\n")
    out.append("| N | recall@N | hit@N |\n|---|---|---|")
    for N in NS:
        out.append(f"| {N} | {fmt([r[f'bm25_recall@{N}'] for r in R])} | {fmt([r[f'bm25_hit@{N}'] for r in R])} |")
    out.append(f"\nBM25 MRR = {fmt([r['bm25_mrr'] for r in R])}\n")

    out.append("### (b,c) Graph expansion of seed sets (undirected, non-test nodes)\n")
    out.append("| seeds | hops | cand. size median (p90) | recall | hit | BM25 equal-budget recall | BM25 eq-budget hit | gold reachable only via graph (not in BM25 top-100) |")
    out.append("|---|---|---|---|---|---|---|---|")
    seedsets = [f"bm25top{k}" for k in KS_EXP] + ["anchor", "anchor+bm25top5"]
    for s in seedsets:
        for h in (0, 1, 2):
            sz = [r[f"{s}_h{h}_size"] for r in R]
            out.append(
                f"| {s} | {h} | {np.median(sz):.0f} ({np.percentile(sz, 90):.0f}) | "
                f"{np.mean([r[f'{s}_h{h}_recall'] for r in R]):.3f} | {np.mean([r[f'{s}_h{h}_hit'] for r in R]):.3f} | "
                f"{np.mean([r[f'{s}_h{h}_eqbudget_recall'] for r in R]):.3f} | {np.mean([r[f'{s}_h{h}_eqbudget_hit'] for r in R]):.3f} | "
                f"{int(sum(r[f'{s}_h{h}_graph_only100'] for r in R))} |")
    na = sum(r["n_anchor_seeds"] > 0 for r in R)
    out.append(f"\nTasks with >=1 anchor seed: {na}/{n}; median #anchor seeds (when >0): "
               f"{np.median([r['n_anchor_seeds'] for r in R if r['n_anchor_seeds'] > 0]):.0f}\n")

    out.append("### (d) Shortest undirected path from BM25 seeds to nearest gold node\n")
    out.append("| distance | from top-1 | from top-5 (min) | from anchor seeds (min) |\n|---|---|---|---|")
    c1, c5, ca = (Counter(min(r[k], 9) for r in R) for k in ("dist_top1", "dist_top5", "dist_anchor"))
    for d in range(0, 10):
        lab = str(d) if d < 9 else "unreached(>8 / no seeds)"
        if d >= 5 and d < 9 and not (c1[d] or c5[d] or ca[d]):
            continue
        out.append(f"| {lab} | {c1[d]} | {c5[d]} | {ca[d]} |")
    out.append(f"\nMedian undirected degree: BM25 top-5 nodes {np.median([r['deg_top5_median'] for r in R]):.1f}, "
               f"gold nodes {np.median([r['deg_gold_median'] for r in R]):.1f}.\n")

    # RL-addressable set
    miss5 = [r for r in R if r["bm25_hit@5"] == 0]
    out.append("### RL-addressable set\n")
    out.append(f"- BM25 misses all gold in top-5 on {len(miss5)}/{n} tasks ({len(miss5) / n:.1%}).")
    rows = []
    for name, cond in [
        ("gold in BM25 top-6..20 (pure re-rank, no graph needed)", lambda r: r["bm25_hit@20"] == 1),
        ("gold in BM25 top-21..50 (re-rank of top-50)", lambda r: r["bm25_hit@50"] == 1 and r["bm25_hit@20"] == 0),
        ("gold in BM25 top-51..100", lambda r: r["bm25_hit@100"] == 1 and r["bm25_hit@50"] == 0),
        ("gold <=1 hop of BM25 top-5", lambda r: r["dist_top5"] <= 1),
        ("gold <=2 hops of BM25 top-5", lambda r: r["dist_top5"] <= 2),
        ("gold <=1 hop of anchor/top-5 seeds", lambda r: min(r["dist_top5"], r["dist_anchor"]) <= 1),
        ("gold <=2 hops of anchor/top-5 seeds", lambda r: min(r["dist_top5"], r["dist_anchor"]) <= 2),
        ("gold <=2 hops of top-5/anchors AND not in BM25 top-50 (graph-unique)",
         lambda r: min(r["dist_top5"], r["dist_anchor"]) <= 2 and r["bm25_hit@50"] == 0),
        ("gold <=2 hops of top-5/anchors AND not in BM25 top-100 (graph-unique)",
         lambda r: min(r["dist_top5"], r["dist_anchor"]) <= 2 and r["bm25_hit@100"] == 0),
        ("gold <=1 hop of top-5/anchors AND not in BM25 top-50 (graph-unique, cheap)",
         lambda r: min(r["dist_top5"], r["dist_anchor"]) <= 1 and r["bm25_hit@50"] == 0),
        ("unreachable: >2 hops and not in top-100", lambda r: min(r["dist_top5"], r["dist_anchor"]) > 2 and r["bm25_hit@100"] == 0),
    ]:
        k = sum(cond(r) for r in miss5)
        rows.append((name, k))
        out.append(f"- among those {len(miss5)}: {name}: **{k}** ({k / n:.1%} of all tasks)")

    # ceilings: oracle re-ranking within candidate sets
    out.append("\n### Ceilings (oracle ordering inside a candidate set)\n")
    out.append("| candidate set | median size | oracle hit@5 = oracle MRR ceiling* | oracle Recall@5 | gain over BM25 hit@5 / R@5 |")
    out.append("|---|---|---|---|---|")
    b_hit5 = np.mean([r["bm25_hit@5"] for r in R])
    b_r5 = np.mean([r["bm25_recall@5"] for r in R])

    def ceil_row(lbl, sizes, hits, r5):
        out.append(f"| {lbl} | {np.median(sizes):.0f} | {np.mean(hits):.3f} | {np.mean(r5):.3f} | "
                   f"+{np.mean(hits) - b_hit5:.3f} / +{np.mean(r5) - b_r5:.3f} |")

    ceil_row("BM25 top-5 (= BM25 itself)", [5] * n, [r["bm25_hit@5"] for r in R], [r["bm25_recall@5"] for r in R])
    for N in (20, 50, 100):
        ceil_row(f"BM25 top-{N}", [N] * n, [r[f"bm25_hit@{N}"] for r in R],
                 [min(sum(x <= N for x in r["gold_bm25_ranks"]), 5) / r["n_gold"] for r in R])
    for s in ("bm25top5", "anchor+bm25top5", "bm25top10"):
        for h in (1, 2):
            ceil_row(f"{s} +{h} hop", [r[f"{s}_h{h}_size"] for r in R], [r[f"{s}_h{h}_hit"] for r in R],
                     [r[f"{s}_h{h}_orR5"] for r in R])
    ceil_row("re-rank pool (BM25 top-50 U 1hop(top-10) U anchors)", [r["pool_size"] for r in R],
             [r["pool_hit"] for r in R], [min(int(r["pool_y"].sum()), 5) / r["n_gold"] for r in R])
    out.append(f"\n*oracle MRR = 1 whenever any gold is in the set. BM25 hit@5={b_hit5:.3f}, R@5={b_r5:.3f}, MRR="
               f"{np.mean([r['bm25_mrr'] for r in R]):.3f}.\n")

    # per-repo summary
    out.append("### Per-repo\n")
    out.append("| repo | n | BM25 hit@5 | hit@50 | top5+2hop hit (size med) | dist_top5<=2 & miss@50 |\n|---|---|---|---|---|---|")
    for repo in ("fastapi", "rich", "requests", "httpx"):
        S = [r for r in R if r["repo"] == repo]
        if not S:
            continue
        out.append(f"| {repo} | {len(S)} | {np.mean([r['bm25_hit@5'] for r in S]):.3f} | {np.mean([r['bm25_hit@50'] for r in S]):.3f} | "
                   f"{np.mean([r['bm25top5_h2_hit'] for r in S]):.3f} ({np.median([r['bm25top5_h2_size'] for r in S]):.0f}) | "
                   f"{sum(min(r['dist_top5'], r['dist_anchor']) <= 2 and r['bm25_hit@50'] == 0 for r in S)} |")
    text = "\n".join(out) + "\n"
    (CACHE.parent / "oracle.md").write_text(text)
    (CACHE.parent / "oracle_rl_addressable.json").write_text(json.dumps(dict(rows), indent=1))
    print(text)


if __name__ == "__main__":
    main()
