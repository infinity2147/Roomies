"""§8 measurement protocol: aggregate k runs of a system into one scoreboard row.

pass@1 = mean ± std over runs (on the common task set); pass@k = solved in any run;
stable = solved in all runs; stochastic = solved in some but not all.
Also time/task, tool-error rate (tool calls returning status=error), tokens/task — from traces.

Usage:
  .venv/bin/python -m src.eval.scoreboard --system C6a --runs results/kaggle/c6a_full_r1/results/c6a_full_r1 ... \
      [--tasks data/derived/valid_tasks.txt] [--append reports/scoreboard.md]
  .venv/bin/python -m src.eval.scoreboard --compare A_run1,A_run2 B_run1,B_run2   # paired McNemar on union
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_run(run_dir: Path) -> dict[str, dict]:
    rows = {}
    for line in open(run_dir / "task_results.jsonl"):
        r = json.loads(line)
        tr = run_dir / "traces" / f"trace_{r['instance_id']}.json"
        r["_tool_err"], r["_tool_calls"], r["_tokens"] = 0, 0, None
        if tr.exists():
            try:
                t = json.loads(tr.read_text())
                for s in t.get("steps", []):
                    for c in s.get("tool_calls", []) or []:
                        r["_tool_calls"] += 1
                    obs = json.dumps(s.get("observation") or "")
                    r["_tool_err"] += obs.count('\\"status\\": \\"error\\"') + obs.count('"error_code"')
                r["_tokens"] = (t.get("final_metrics") or {}).get("total_tokens")
            except Exception:  # noqa: BLE001
                pass
        rows[r["instance_id"]] = r
    return rows


def row_for(system: str, runs: list[Path], task_filter: set[str] | None) -> dict:
    data = [load_run(r) for r in runs]
    common = set.intersection(*(set(d) for d in data))
    if task_filter:
        common &= task_filter
    per_run = [sum(d[i]["resolved"] for i in common) / len(common) for d in data]
    solved_counts = defaultdict(int)
    for d in data:
        for i in common:
            solved_counts[i] += bool(d[i]["resolved"])
    k = len(data)
    times = [d[i]["duration_seconds"] for d in data for i in common]
    calls = sum(d[i]["_tool_calls"] for d in data for i in common)
    errs = sum(d[i]["_tool_err"] for d in data for i in common)
    toks = [d[i]["_tokens"] for d in data for i in common if d[i]["_tokens"]]
    return {
        "system": system, "date": dt.date.today().isoformat(), "n_tasks": len(common), "k": k,
        "pass1_mean": st.mean(per_run), "pass1_std": st.pstdev(per_run) if k > 1 else 0.0,
        "passk": sum(c > 0 for c in solved_counts.values()) / len(common),
        "stable": sum(c == k for c in solved_counts.values()),
        "stochastic": sum(0 < c < k for c in solved_counts.values()),
        "time_per_task": st.mean(times), "tool_err_rate": errs / max(calls, 1),
        "tokens_per_task": st.mean(toks) if toks else None,
        "runs": [str(r) for r in runs], "solved_counts": dict(solved_counts),
    }


def mcnemar(a_runs: list[Path], b_runs: list[Path]) -> str:
    """Paired comparison on per-task majority outcome (exact binomial McNemar)."""
    A = [load_run(r) for r in a_runs]
    B = [load_run(r) for r in b_runs]
    common = set.intersection(*(set(d) for d in A + B))
    maj = lambda D, i: sum(d[i]["resolved"] for d in D) / len(D) > 0.5  # noqa: E731
    b = sum(maj(A, i) and not maj(B, i) for i in common)
    c = sum(maj(B, i) and not maj(A, i) for i in common)
    n = b + c
    p = min(1.0, 2 * sum(math.comb(n, j) for j in range(0, min(b, c) + 1)) / 2**n) if n else 1.0
    return f"tasks={len(common)}  A-only={b}  B-only={c}  exact McNemar p={p:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system")
    ap.add_argument("--runs", nargs="*")
    ap.add_argument("--tasks", default=str(ROOT / "data" / "derived" / "valid_tasks.txt"))
    ap.add_argument("--append", default=str(ROOT / "reports" / "scoreboard.md"))
    ap.add_argument("--compare", nargs=2)
    a = ap.parse_args()
    if a.compare:
        print(mcnemar([Path(x) for x in a.compare[0].split(",")], [Path(x) for x in a.compare[1].split(",")]))
        return
    tf = {l.strip() for l in open(a.tasks) if l.strip()} if a.tasks else None
    r = row_for(a.system, [Path(x) for x in a.runs], tf)
    line = (f"| {r['system']} | {r['date']} | {r['n_tasks']} | {r['k']} | {r['pass1_mean']:.3f} ± {r['pass1_std']:.3f} | "
            f"{r['passk']:.3f} | {r['stable']} | {r['stochastic']} | {r['time_per_task']:.0f}s | "
            f"{r['tool_err_rate']:.3f} | {r['tokens_per_task'] or 0:.0f} |")
    print(line)
    sb = Path(a.append)
    if not sb.exists():
        sb.write_text("# Scoreboard (§8 protocol)\n\n| system | date | tasks | k | pass@1 mean ± std | pass@k | stable | stochastic | time/task | tool_err_rate | tokens/task |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
    with open(sb, "a") as f:
        f.write(line + "\n")
    (ROOT / "experiments").mkdir(exist_ok=True)
    out = ROOT / "experiments" / f"{r['date']}_scoreboard_{r['system']}.json"
    out.write_text(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
