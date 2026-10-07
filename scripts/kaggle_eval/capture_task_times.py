"""Per-task agent time from a Kaggle eval kernel capture.jsonl (serial run, concurrency 1).

Usage: .venv/bin/python scripts/kaggle_eval/capture_task_times.py <run> [<base_run>]
Segments LLM calls by the root task prompt ("You are evaluating a software engineering task ...") and reports
per-task spans (start of task i -> start of task i+1; last task -> its last call end). Excludes sandbox setup
before the first call and verification after the last call of the final task, so it slightly underestimates.
"""
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def spans(run: str) -> list:
    f = next((ROOT / "results/kaggle" / run).rglob("capture.jsonl"))
    starts, last_end = {}, 0.0
    for line in open(f):
        r = json.loads(line)
        last_end = max(last_end, r["t"] + r["dt"])
        for m in r["request"].get("messages", []):
            c = m.get("content")
            c = c if isinstance(c, str) else json.dumps(c)
            if m.get("role") == "user" and c.startswith("You are evaluating a software engineering task"):
                key = c.split("## Task Budget")[0]
                starts.setdefault(key, r["t"])
                break
    order = sorted(starts.values())
    return [(b - a) / 60 for a, b in zip(order, order[1:] + [last_end])]


def report(run: str) -> list:
    sp = spans(run)
    print(f"{run}: tasks={len(sp)} min/task mean={st.mean(sp):.2f} median={st.median(sp):.2f} "
          f"p90={sorted(sp)[int(0.9 * len(sp))]:.1f} max={max(sp):.1f}")
    for n in (100, 120, 150):
        print(f"  projection {n} tasks: {n * st.mean(sp) / 60 + 0.5:.2f} h")
    print("  spans:", " ".join(f"{s:.1f}" for s in sp))
    return sp


if __name__ == "__main__":
    a = report(sys.argv[1])
    if len(sys.argv) > 2:
        b = report(sys.argv[2])
        print(f"total-time ratio {sys.argv[1]}/{sys.argv[2]} = {sum(a) / sum(b):.2f} (same task list required; n={len(a)} vs {len(b)})")
