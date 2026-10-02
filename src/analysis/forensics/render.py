"""Render a compact, readable trajectory for one (run, task).

Usage: .venv/bin/python -m src.analysis.forensics.render c6a_n30 rich_4077 [--msg 200] [--obs 160]
"""

from __future__ import annotations

import argparse
import json

from src.analysis.forensics.extract import run_dir


def render(run: str, iid: str, msg_w: int = 200, obs_w: int = 160) -> str:
    tr = json.loads((run_dir(run) / "traces" / f"trace_{iid}.json").read_text())
    out = []
    k = 0
    for s in tr["steps"]:
        if s.get("source") != "agent":
            continue
        m = (s.get("message") or "").replace("\n", " ")
        if m and msg_w:
            out.append(f"      # {m[:msg_w]}")
        obs = (s.get("observation") or {}).get("content", "").replace("\\n", " ")
        for tc in s.get("tool_calls") or []:
            k += 1
            t = (tc.get("extra") or {}).get("elapsed_s") or 0
            a = json.dumps(tc.get("arguments"), ensure_ascii=False).replace("\\n", "⏎")
            out.append(f"{k:3d} {t:6.0f}s {tc.get('function_name')}: {a[:240]}")
            if obs_w:
                out.append(f"           -> {obs[:obs_w]}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("iid")
    ap.add_argument("--msg", type=int, default=200)
    ap.add_argument("--obs", type=int, default=160)
    a = ap.parse_args()
    print(render(a.run if a.run.endswith("_n30") else a.run + "_n30", a.iid, a.msg, a.obs))


if __name__ == "__main__":
    main()
