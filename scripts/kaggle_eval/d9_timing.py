"""D9 runtime check for a Kaggle L4 timing run (concurrency 1 = serial like the scorer).

Usage: .venv/bin/python scripts/kaggle_eval/d9_timing.py <run> [<base_run>]
  <run> = results/kaggle/<run>/results/<run-ish>/task_results.jsonl is searched under results/kaggle/<run>.
Prints n, resolved, mean/median/max task minutes, the projection 150 × mean + 0.5 h (must be ≤ 11 h), and, with a
base run, the paired per-task time ratio on shared instance_ids.
"""
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(run: str) -> dict:
    files = list((ROOT / "results/kaggle" / run).rglob("task_results.jsonl"))
    if not files:
        sys.exit(f"no task_results.jsonl under results/kaggle/{run}")
    return {r["instance_id"]: r for f in files for r in map(json.loads, f.read_text().splitlines()) if r}


def report(run: str) -> dict:
    rs = load(run)
    mins = [r["duration_seconds"] / 60 for r in rs.values()]
    mean = st.mean(mins)
    proj = 150 * mean / 60 + 0.5
    print(f"{run}: n={len(rs)} resolved={sum(r['resolved'] for r in rs.values())} "
          f"min/task mean={mean:.2f} median={st.median(mins):.2f} max={max(mins):.1f} "
          f"errors={sum(bool(r.get('error')) for r in rs.values())}")
    print(f"  D9 projection 150×mean+0.5h = {proj:.2f} h -> {'PASS' if proj <= 11 else 'FAIL'} (limit 11 h)")
    return rs


if __name__ == "__main__":
    a = report(sys.argv[1])
    if len(sys.argv) > 2:
        b = report(sys.argv[2])
        ids = sorted(set(a) & set(b))
        if ids:
            ta = sum(a[i]["duration_seconds"] for i in ids)
            tb = sum(b[i]["duration_seconds"] for i in ids)
            print(f"paired on {len(ids)} tasks: total time ratio {sys.argv[1]}/{sys.argv[2]} = {ta / tb:.2f}; "
                  f"resolved {sum(a[i]['resolved'] for i in ids)} vs {sum(b[i]['resolved'] for i in ids)}")
