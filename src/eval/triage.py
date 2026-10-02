"""Failure triage for an evaluation results dir (local or downloaded from Kaggle).

Per task: resolved, duration, tool calls, LLM calls, patch files vs gold files (localization),
skill/tool usage from traces, and a failure bucket:
  resolved | no_patch | wrong_location | touched_tests_only | right_file_wrong_fix | agent_error
Usage: .venv/bin/python -m src.eval.triage results/<run> [--out reports/triage_<run>.md]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from unidiff import PatchSet

from src.dataio.loaders import ROOT, load_tasks


def patch_files(p: str) -> list[str]:
    try:
        return [f.path for f in PatchSet(p)]
    except Exception:  # noqa: BLE001
        return []


_LOG_TOOL = re.compile(r"\[\s*[\d.]+s\]\S*\s+\S+\s+(?:\x1b\[[0-9;]*m)*(\w+)")
_SKILL_FILE = re.compile(r'"file_path": "scripts/(\w+)\.py"')


def tool_usage_from_log(log_path: Path) -> Counter:
    """Count tool calls from the rich-formatted session log (Kaggle outputs have no traces)."""
    c: Counter = Counter()
    if not log_path.exists():
        return c
    for line in log_path.read_text(errors="ignore").splitlines():
        plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
        m = re.match(r"\s*\[\s*[\d.]+s\]\s+\S+\s+(\w+)", plain)
        if not m or m.group(1) in ("I", "The"):
            continue
        name = m.group(1)
        if name == "run_skill_script":
            f = _SKILL_FILE.search(plain)
            name = f"skill:{f.group(1)}" if f else "skill:malformed"
        c[name] += 1
    return c


def tool_usage(trace_path: Path) -> Counter:
    c: Counter = Counter()
    if not trace_path.exists():
        return tool_usage_from_log(trace_path.parent.parent / "logs" / (trace_path.stem.removeprefix("trace_") + ".log"))
    try:
        tr = json.loads(trace_path.read_text())
    except Exception:  # noqa: BLE001
        return c
    for step in tr.get("steps", []):
        for call in step.get("tool_calls", []) or []:
            name = call.get("function_name") or call.get("name") or "?"
            if name == "run_skill_script":
                args = call.get("arguments") or {}
                name = f"skill:{str(args.get('file_path', '?')).rsplit('/', 1)[-1]}"
            c[name] += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rd = Path(a.results_dir)
    tasks = {t.instance_id: t for t in load_tasks()}
    rows = [json.loads(l) for l in open(rd / "task_results.jsonl")]
    lines = []
    buckets: Counter = Counter()
    usage_all: Counter = Counter()
    for r in rows:
        iid = r["instance_id"]
        t = tasks[iid]
        gold = [f.path for f in PatchSet(t.patch) if not f.is_added_file] or patch_files(t.patch)
        pf = rd / "patches" / f"{iid}.patch"
        ptxt = pf.read_text() if pf.exists() else ""
        files = patch_files(ptxt)
        src_files = [f for f in files if "test" not in f]
        usage = tool_usage(rd / "traces" / f"trace_{iid}.json")
        usage_all.update(usage)
        if r.get("resolved"):
            b = "resolved"
        elif r.get("error") and not ptxt:
            b = "agent_error"
        elif not ptxt.strip():
            b = "no_patch"
        elif not src_files:
            b = "touched_tests_only"
        elif not set(src_files) & set(gold):
            b = "wrong_location"
        else:
            b = "right_file_wrong_fix"
        buckets[b] += 1
        lines.append(f"| {iid} | {b} | {r.get('duration_seconds', 0):.0f} | {r.get('tool_calls', '')} | "
                     f"{', '.join(src_files)[:60]} | {', '.join(gold)[:60]} | "
                     f"{' '.join(f'{k}={v}' for k, v in usage.most_common(5))} | {(r.get('error') or '')[:60]} |")
    n = len(rows)
    dur = [r.get("duration_seconds", 0) for r in rows]
    head = [f"# Triage: {rd.name}\n",
            f"resolved {buckets['resolved']}/{n} ({buckets['resolved'] / max(n, 1):.1%}); mean time {sum(dur) / max(n, 1):.0f}s; max {max(dur, default=0):.0f}s\n",
            "Buckets: " + ", ".join(f"{k}={v}" for k, v in buckets.most_common()) + "\n",
            "Tool usage: " + ", ".join(f"{k}={v}" for k, v in usage_all.most_common(15)) + "\n",
            "| task | bucket | sec | tools | patched src | gold | usage | error |", "|---|---|---|---|---|---|---|---|"]
    report = "\n".join(head + lines) + "\n"
    out = Path(a.out) if a.out else ROOT / "reports" / f"triage_{rd.name}.md"
    out.write_text(report)
    print("\n".join(head[:4]))
    print("wrote", out)


if __name__ == "__main__":
    main()
