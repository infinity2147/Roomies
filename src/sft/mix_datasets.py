"""Mix SFT sequence files (external converted trajectories + own rollouts) into one training file.

Contamination guard: own rollouts come from the proxy benchmark, so they may only be trained on for proxy repos in the
TRAIN half of a fixed repo split; the EVAL half (written to --eval-ids) is the only proxy subset on which a model trained
with own data may be evaluated. External sources already exclude every proxy repo and the public competition repos.

Usage:
  .venv/bin/python -m src.sft.mix_datasets --external data/derived/sft/e2_nebius data/derived/sft/e2_swe_hero \
      --own data/derived/sft/e1_own_c11t.jsonl --own-share 0.3 --out data/derived/sft/mix_v1.jsonl \
      --eval-ids ops/queue/shards/proxy_eval_half.txt
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_seqs(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        files = sorted(glob.glob(str(Path(p) / "*.jsonl"))) if Path(p).is_dir() else [p]
        for f in files:
            out.extend(l for l in open(f) if l.strip())
    return out


def repo_split(seed: int) -> tuple[set[str], set[str], list[str]]:
    tasks = [json.loads(l) for l in open(ROOT / "data/derived/proxy/valid_tasks.jsonl")]
    repos = sorted({t["repo"] for t in tasks})
    random.Random(seed).shuffle(repos)
    train = set(repos[: len(repos) // 2])
    evalr = set(repos[len(repos) // 2:])
    eval_ids = [t["instance_id"] for t in tasks if t["repo"] in evalr]
    return train, evalr, eval_ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", nargs="+", required=True, help="files or dirs of *.jsonl")
    ap.add_argument("--own", nargs="*", default=[])
    ap.add_argument("--own-share", type=float, default=0.3, help="target fraction of sequences from own rollouts")
    ap.add_argument("--max-seqs", type=int, default=0, help="cap total sequences (0 = all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eval-ids", default=str(ROOT / "ops/queue/shards/proxy_eval_half.txt"))
    a = ap.parse_args()

    train_repos, eval_repos, eval_ids = repo_split(a.seed)
    task_repo = {json.loads(l)["instance_id"]: json.loads(l)["repo"] for l in open(ROOT / "data/derived/proxy/valid_tasks.jsonl")}
    rng = random.Random(a.seed)
    ext = read_seqs(a.external)
    own_all = read_seqs(a.own)
    own, dropped = [], 0
    for l in own_all:
        iid = json.loads(l)["instance_id"]
        if task_repo.get(iid) in train_repos:
            own.append(l)
        else:
            dropped += 1
    rng.shuffle(ext); rng.shuffle(own)
    if a.max_seqs and len(ext) + len(own) > a.max_seqs:  # budgeted run: own gets up to its share, external fills the rest
        n_own = min(len(own), int(a.max_seqs * a.own_share))
        own, ext = own[:n_own], ext[: a.max_seqs - n_own]
    elif own and 0 < a.own_share < 1:  # unbudgeted: own-share is a ceiling on own data, never a reason to drop external
        own = own[: int(len(ext) * a.own_share / (1 - a.own_share))]
    mix = ext + own
    rng.shuffle(mix)
    if a.max_seqs:
        mix = mix[: a.max_seqs]
    src = Counter()
    with open(a.out, "w") as f:
        for l in mix:
            ex = json.loads(l)
            src[ex.get("source", "own")] += 1
            f.write(l if l.endswith("\n") else l + "\n")
    Path(a.eval_ids).parent.mkdir(parents=True, exist_ok=True)
    Path(a.eval_ids).write_text("\n".join(eval_ids) + "\n")
    print(json.dumps({"sequences": len(mix), "by_source": src, "own_dropped_eval_half": dropped,
                      "train_repos": sorted(train_repos), "eval_repos": sorted(eval_repos),
                      "eval_tasks": len(eval_ids)}, indent=1))


if __name__ == "__main__":
    main()
