"""B4 step 2: build harness-compatible snapshot tarballs for mined candidates.

Each snapshot = repository tree at the parent commit in a fresh single-commit git repo (no future
history), packed as <instance_id>.tgz like the competition snapshots. Also writes a tasks file in
the harness schema for verify_gold.

Usage: .venv/bin/python -m src.mining.build_snapshots [--per-repo 200] [--workers 16]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src.dataio.loaders import DATA

MINING = DATA / "derived" / "mining"
OUT = DATA / "derived" / "mined_snapshots"
FIELDS = ["instance_id", "repo", "base_commit", "patch", "test_patch", "problem_statement", "hints_text", "created_at"]


def build(row: dict) -> tuple[str, bool, str]:
    short = row["repo"].split("/")[-1].lower()
    src_repo = MINING / short
    tgz = OUT / f"{row['instance_id']}.tgz"
    if tgz.exists():
        return row["instance_id"], True, "cached"
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        arch = subprocess.run(["git", "-C", str(src_repo), "archive", row["base_commit"]], capture_output=True)
        if arch.returncode != 0:
            return row["instance_id"], False, "archive failed"
        subprocess.run(["tar", "xf", "-", "-C", str(ws)], input=arch.stdout, check=True)
        env = ["-c", "user.email=miner@local", "-c", "user.name=miner", "-c", "init.defaultBranch=main"]
        subprocess.run(["git", *env, "init", "-q", str(ws)], check=True)
        subprocess.run(["git", *env, "-C", str(ws), "add", "-A"], check=True)
        subprocess.run(["git", *env, "-C", str(ws), "commit", "-qm", "base"], check=True)
        subprocess.run(["tar", "czf", str(tgz), "-C", str(ws), "."], check=True)
    return row["instance_id"], True, "built"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-repo", type=int, default=200)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in open(DATA / "derived" / "mined_candidates.jsonl")]
    by_repo: dict[str, list] = {}
    for r in sorted(rows, key=lambda r: -int(r["created_at"])):  # most recent first (closest deps)
        by_repo.setdefault(r["repo"], []).append(r)
    chosen = [r for rs in by_repo.values() for r in rs[: a.per_repo]]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(build, chosen))
    ok = {i for i, good, _ in res if good}
    with open(DATA / "derived" / "mined_tasks_unverified.jsonl", "w") as f:
        for r in chosen:
            if r["instance_id"] in ok:
                t = {k: r[k] for k in FIELDS}
                t["created_at"] = str(t["created_at"])
                f.write(json.dumps(t) + "\n")
    print(f"snapshots ok: {len(ok)}/{len(chosen)} -> {OUT}")


if __name__ == "__main__":
    main()
