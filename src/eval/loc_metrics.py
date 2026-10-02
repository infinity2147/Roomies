"""Localization metrics over a ranked list of node indices (fixed schema for all experiments)."""

from __future__ import annotations

import numpy as np

KS = (1, 5, 10, 20)


def node_metrics(ranked: np.ndarray, targets: np.ndarray) -> dict[str, float]:
    tset = set(int(t) for t in targets)
    pos = [i for i, n in enumerate(ranked[:1000]) if int(n) in tset]
    m: dict[str, float] = {}
    for k in KS:
        hits = sum(p < k for p in pos)
        m[f"recall@{k}"] = hits / len(tset)
        m[f"hit@{k}"] = float(hits > 0)
    m["mrr"] = 1.0 / (pos[0] + 1) if pos else 0.0
    dcg = sum(1 / np.log2(p + 2) for p in pos if p < 10)
    idcg = sum(1 / np.log2(i + 2) for i in range(min(len(tset), 10)))
    m["ndcg10"] = dcg / idcg
    return m


def file_metrics(ranked: np.ndarray, module_of: list[str], target_modules: set[str]) -> dict[str, float]:
    """Hit@k over the de-duplicated module (file) ranking induced by the node ranking."""
    seen: list[str] = []
    for n in ranked[:2000]:
        m = module_of[int(n)]
        if m not in seen:
            seen.append(m)
        if len(seen) >= 20:
            break
    pos = [i for i, m in enumerate(seen) if m in target_modules]
    out = {f"file_hit@{k}": float(bool(pos) and pos[0] < k) for k in (1, 3, 5, 10)}
    out["file_mrr"] = 1.0 / (pos[0] + 1) if pos else 0.0
    return out


def rank_from_scores(scores: np.ndarray, mask: np.ndarray) -> np.ndarray:
    ids = np.flatnonzero(mask)
    return ids[np.argsort(-scores[ids], kind="stable")]
