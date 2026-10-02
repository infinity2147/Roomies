"""A1 sanity: verify gold patches (should resolve) and empty patches (should fail) with the
real harness `verify_task` in the subprocess sandbox. No LLM needed.

Run with the 3.13 eval env (matches the competition sandbox python):
  .venv-eval/bin/python -m src.eval.verify_gold --per-repo 5 --mode gold
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import src.eval.harness_patches  # noqa: F401  (must precede Evaluator use)
from swegemma.config import EvalConfig
from swegemma.deduplication import resolve_task_snapshot_paths
from swegemma.evaluate import Evaluator
from swegemma.harness.verification import verify_task
from swegemma.models import load_tasks

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


async def run_one(ev: Evaluator, task, patch: str) -> dict:
    snap, base_snap, patch_path = resolve_task_snapshot_paths(ev.config.snapshots_dir, task.instance_id, task.repo)
    t0 = time.perf_counter()
    res = await verify_task(
        ev.docker,
        ev.config,
        task,
        snap,
        base_snapshot_path=base_snap,
        patch_path=patch_path,
        agent_patch=patch,
        start_time=t0,
    )
    return {
        "instance_id": task.instance_id,
        "resolved": bool(res.resolved),
        "exit_code": res.test_exit_code,
        "error": (res.error or "")[:300],
        "seconds": round(time.perf_counter() - t0, 1),
        "test_tail": (res.test_output or "")[-1500:],
        "full_output": res.test_output or "",
    }


async def main_async(args) -> None:
    tasks = load_tasks(DATA / "tasks.jsonl")
    by_repo = defaultdict(list)
    for t in tasks:
        by_repo[t.repo].append(t)
    rng = random.Random(args.seed)
    if args.task_ids:
        chosen = [t for t in tasks if t.instance_id in set(args.task_ids)]
    elif args.per_repo:
        chosen = [t for ts in by_repo.values() for t in rng.sample(ts, min(args.per_repo, len(ts)))]
    else:
        chosen = tasks

    out_dir = ROOT / "results" / f"verify_{args.mode}"
    cfg = EvalConfig(
        tasks_path=DATA / "tasks.jsonl",
        snapshots_dir=DATA / "snapshots",
        results_dir=out_dir,
        submission_dir=DATA / "sample_submission",
        models={},
        sandbox="subprocess",
        wheels_dir=DATA / "wheels",
        graph_dir=str(DATA / "graphs"),
        embeddings_dir=str(DATA / "embeddings"),
        display_mode="quiet",
    )
    ev = Evaluator(cfg)
    sem = asyncio.Semaphore(args.concurrency)
    out_path = out_dir / "verify.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def worker(t):
        async with sem:
            patch = t.patch if args.mode == "gold" else ""
            r = await run_one(ev, t, patch)
            print(f"{r['instance_id']:18} resolved={r['resolved']!s:5} exit={r['exit_code']} {r['seconds']}s {r['error'][:120]}", flush=True)
            log_dir = out_dir / "logs"
            log_dir.mkdir(exist_ok=True)
            (log_dir / f"{t.instance_id}.log").write_text(r.pop("full_output"))
            with open(out_path, "a") as f:
                f.write(json.dumps(r) + "\n")
            return r

    results = await asyncio.gather(*(worker(t) for t in chosen))
    n_ok = sum(r["resolved"] for r in results)
    print(f"\nmode={args.mode}: {n_ok}/{len(results)} resolved -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["gold", "empty"], default="gold")
    ap.add_argument("--per-repo", type=int, default=0)
    ap.add_argument("--task-ids", nargs="*")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
