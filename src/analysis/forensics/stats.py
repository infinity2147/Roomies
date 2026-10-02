"""Aggregate statistics over reports/council/trajectory_table.csv (prints markdown).

Usage: .venv/bin/python -m src.analysis.forensics.stats
"""

from __future__ import annotations

import csv
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CFGS = ["c1", "c2", "c3", "c4", "c5a", "c5b", "c6a", "c6b"]


def load() -> list[dict]:
    rows = list(csv.DictReader(open(ROOT / "reports" / "council" / "trajectory_table.csv")))
    for r in rows:
        for k, v in list(r.items()):
            if v == "":
                r[k] = None
            else:
                try:
                    r[k] = float(v) if "." in v else int(v)
                except ValueError:
                    pass
    return rows


def med(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "n/a"
    q = st.quantiles(xs, n=4) if len(xs) > 1 else [xs[0]] * 3
    return f"{st.median(xs):.0f} [{q[0]:.0f}-{q[2]:.0f}] (n={len(xs)})"


def rate(sub, key="resolved"):
    n = len(sub)
    k = sum(1 for r in sub if r[key])
    return f"{k}/{n} ({k / n:.0%})" if n else "0/0"


def main() -> None:
    rows = load()
    fails = [r for r in rows if not r["resolved"]]
    succ = [r for r in rows if r["resolved"]]
    stoch = [r for r in rows if r["task_class"] == "stochastic"]
    P = print

    P("## Buckets over all failures (n=%d)" % len(fails))
    for b, n in Counter(r["bucket"] for r in fails).most_common():
        by = Counter(r["task_class"] for r in fails if r["bucket"] == b)
        P(f"- {b}: {n} ({n / len(fails):.0%})  stochastic={by['stochastic']} never={by['never']}")

    P("\n## Gold-file contact among failures")
    read = [r for r in fails if r["gold_read_t"] is not None]
    edited = [r for r in fails if r["n_gold_edits"]]
    in_patch = [r for r in fails if r["files_overlap"]]
    close = [r for r in fails if (r["hunk_overlap"] or 0) > 0]
    full = [r for r in fails if (r["hunk_overlap"] or 0) >= 1]
    P(f"- read a gold file: {len(read)}/{len(fails)}; edited a gold file (successful edit): {len(edited)}/{len(fails)}; "
      f"gold file in final patch: {len(in_patch)}/{len(fails)}; patch overlaps >=1 gold hunk: {len(close)}/{len(fails)}; "
      f"overlaps all gold hunks: {len(full)}/{len(fails)}")
    P(f"- never read any gold file: {len(fails) - len(read)}/{len(fails)}")

    P("\n## Timing (seconds since session start): median [IQR]")
    for name, sub in [("success", succ), ("failure", fails), ("stochastic-success", [r for r in stoch if r["resolved"]]),
                      ("stochastic-failure", [r for r in stoch if not r["resolved"]])]:
        P(f"- {name}: gold_read_t {med([r['gold_read_t'] for r in sub])}; first_edit_t {med([r['first_edit_t'] for r in sub])}; "
          f"gold_edit_t {med([r['gold_edit_t'] for r in sub])}; duration {med([r['duration'] for r in sub])}")

    P("\n## Within-task paired timing (stochastic tasks; task medians, success vs failure)")
    by_task = defaultdict(list)
    for r in stoch:
        by_task[r["instance_id"]].append(r)
    for t, rs in sorted(by_task.items()):
        s = [r for r in rs if r["resolved"]]
        f = [r for r in rs if not r["resolved"]]
        def m(xs):
            xs = [x for x in xs if x is not None]
            return f"{st.median(xs):.0f}" if xs else "-"
        P(f"- {t}: S={len(s)} F={len(f)} | gold_read S {m([r['gold_read_t'] for r in s])} F {m([r['gold_read_t'] for r in f])} "
          f"(F never read: {sum(r['gold_read_t'] is None for r in f)}) | first_edit S {m([r['first_edit_t'] for r in s])} "
          f"F {m([r['first_edit_t'] for r in f])} (F never edited: {sum(r['first_edit_t'] is None for r in f)})")

    P("\n## Success rate by time of first source edit")
    for lo, hi in [(0, 60), (60, 120), (120, 180), (180, 240), (240, 300), (300, 600)]:
        sub = [r for r in rows if r["first_edit_t"] is not None and lo <= r["first_edit_t"] < hi]
        ss = [r for r in sub if r["task_class"] == "stochastic"]
        P(f"- first edit in [{lo},{hi})s: all {rate(sub)}; stochastic tasks {rate(ss)}")
    ne = [r for r in rows if r["first_edit_t"] is None]
    P(f"- never made a successful source edit: {rate(ne)}")
    P("\n## Success rate by number of tool calls")
    for lo, hi in [(0, 20), (20, 30), (30, 45), (45, 70), (70, 200)]:
        sub = [r for r in rows if lo <= r["n_calls"] < hi]
        P(f"- calls in [{lo},{hi}): {rate(sub)}")

    P("\n## Verification (ran pytest / tests.py / check.py after first edit)")
    for name, sub in [("all", rows), ("stochastic", stoch)]:
        edited_rows = [r for r in sub if r["first_edit_t"] is not None]
        v = [r for r in edited_rows if r["n_test_runs_after_edit"]]
        nv = [r for r in edited_rows if not r["n_test_runs_after_edit"]]
        P(f"- {name} (rows with an edit, n={len(edited_rows)}): verified {rate(v)} vs not verified {rate(nv)}")
    # stratified by task: Mantel-Haenszel style pooled difference
    num = den = 0.0
    for t, rs in by_task.items():
        rs = [r for r in rs if r["first_edit_t"] is not None]
        v = [r for r in rs if r["n_test_runs_after_edit"]]
        nv = [r for r in rs if not r["n_test_runs_after_edit"]]
        if v and nv:
            w = len(v) * len(nv) / len(rs)
            num += w * (sum(r["resolved"] for r in v) / len(v) - sum(r["resolved"] for r in nv) / len(nv))
            den += w
    if den:
        P(f"- stochastic tasks, task-stratified (MH-weighted) success difference verified - unverified: {num / den:+.2f}")

    P("\n## Malformed tool calls")
    for name, sub in [("success", succ), ("failure", fails)]:
        P(f"- {name}: rows with >=1 edit_file missing-arg failure {sum(1 for r in sub if r['n_edit_missing_arg'])}/{len(sub)}; "
          f"rows with >=5 {sum(1 for r in sub if r['n_edit_missing_arg'] >= 5)}/{len(sub)}; "
          f"mean malformed calls/run {st.mean(r['n_malformed'] for r in sub):.1f}")
    loops = [r for r in rows if r["longest_edit_fail_streak"] >= 5]
    P(f"- runs with >=5 consecutive failed edits (no successful edit in between): {len(loops)}; resolved {sum(r['resolved'] for r in loops)}; "
      f"buckets {dict(Counter(r['bucket'] for r in loops))}")
    tot = Counter()
    for r in rows:
        tot["malformed"] += r["n_malformed"]
        tot["calls"] += r["n_calls"]
        tot["edit_missing"] += r["n_edit_missing_arg"]
        tot["edit_ok"] += r["n_edit_ok"]
        tot["tmp_blocked"] += r["n_tmp_write_blocked"]
    P(f"- totals: malformed {tot['malformed']}/{tot['calls']} calls; edit/write missing-arg {tot['edit_missing']} vs successful edits/writes {tot['edit_ok']}; "
      f"write_file to /tmp blocked {tot['tmp_blocked']}")

    P("\n## Degenerate repetition (same tool+args issued >=5 times in one run)")
    for c in CFGS:
        sub = [r for r in rows if r["config"] == c]
        L = [r for r in sub if r["repeat_loop"]]
        P(f"- {c}: runs with loop {len(L)}/30 (resolved {sum(r['resolved'] for r in L)}); duplicate-call share "
          f"{sum(r['n_dup_calls'] for r in sub) / max(1, sum(r['n_calls'] for r in sub)):.0%}")
    L = [r for r in rows if r["repeat_loop"]]
    P(f"- all: {len(L)}/240 runs loop; success {rate(L)} vs non-loop {rate([r for r in rows if not r['repeat_loop']])}; "
      f"loop buckets {dict(Counter(r['bucket'] for r in L))}")
    nl = [r for r in fails if r["first_edit_t"] is None]
    P(f"- failures that never made a source edit: {len(nl)}/{len(fails)}; of them in a repetition loop {sum(r['repeat_loop'] for r in nl)}; "
      f"hit time limit {sum(r['hit_time_limit'] for r in nl)}; attempted edit_file at all {sum(1 for r in nl if r['n_edit_file'])}")

    P("\n## Timeouts")
    to = [r for r in rows if r["hit_time_limit"]]
    P(f"- runs that hit the 8-min limit (duration>=470s or timeout error): {len(to)}; with non-empty patch {sum(1 for r in to if r['agent_size'])}; resolved {sum(r['resolved'] for r in to)}; "
      f"had read gold {sum(1 for r in to if r['gold_read_t'] is not None)}; had edited gold {sum(1 for r in to if r['n_gold_edits'])}")
    P(f"- resolved among time-limit runs by first_edit_t: <=240s {sum(r['resolved'] for r in to if r['first_edit_t'] is not None and r['first_edit_t'] <= 240)}/{sum(1 for r in to if r['first_edit_t'] is not None and r['first_edit_t'] <= 240)}, "
      f">240s {sum(r['resolved'] for r in to if r['first_edit_t'] is not None and r['first_edit_t'] > 240)}/{sum(1 for r in to if r['first_edit_t'] is not None and r['first_edit_t'] > 240)}, never edited {sum(1 for r in to if r['first_edit_t'] is None)}")
    P(f"- timeouts by config: {dict(Counter(r['config'] for r in to))}")
    nos = [r for r in rows if not r["submit_called"]]
    P(f"- submit_patch never called: {len(nos)} rows; of those resolved {sum(r['resolved'] for r in nos)} (patch is harvested from workspace)")

    P("\n## Patch hygiene")
    for name, sub in [("success", succ), ("failure", fails)]:
        P(f"- {name}: scratch files (repro*.py etc.) in patch {sum(1 for r in sub if r['agent_scratch_files'])}/{len(sub)}; extra (non-gold) src files in patch {sum(1 for r in sub if r['extra_src_files'])}/{len(sub)}; "
          f"test files in patch {sum(1 for r in sub if r['agent_test_files'])}/{len(sub)}; config files {sum(1 for r in sub if r['agent_config_files'])}/{len(sub)}; "
          f"median size ratio agent/gold {med([r['agent_size'] / r['gold_size'] for r in sub if r['gold_size'] and r['agent_size']])}")
    P(f"- test_patch apply conflicts: {sum(1 for r in rows if r['bucket'] == 'test_patch_conflict')} rows "
      f"{dict(Counter(r['instance_id'] for r in rows if r['bucket'] == 'test_patch_conflict'))}")

    P("\n## SFT candidate funnel (successful runs)")
    cur = succ
    steps = [("resolved", lambda r: True),
             ("final patch touches no test/config/scratch file", lambda r: not (r["agent_test_files"] or r["agent_config_files"] or r["agent_scratch_files"])),
             ("no test-file edit anywhere in trajectory", lambda r: not r["n_test_file_edits"]),
             ("no degenerate repetition loop", lambda r: not r["repeat_loop"]),
             ("did not hit time limit (submitted)", lambda r: not r["hit_time_limit"]),
             ("<=40 tool calls", lambda r: r["n_calls"] <= 40),
             ("zero malformed calls", lambda r: not r["n_malformed"])]
    for name, fn in steps:
        cur = [r for r in cur if fn(r)]
        P(f"- {name}: {len(cur)} runs / {len(set(r['instance_id'] for r in cur))} tasks")

    P("\n## Gold difficulty vs solve rate (per task)")
    tasks = {}
    for r in rows:
        tasks[r["instance_id"]] = r
    for cls in ["always", "stochastic", "never"]:
        ts = [r for r in tasks.values() if r["task_class"] == cls]
        P(f"- {cls} (n={len(ts)}): median gold size {st.median(r['gold_size'] for r in ts):.0f} lines, "
          f"median gold hunks {st.median(r['gold_n_hunks'] for r in ts):.0f}, multi-file {sum(r['gold_n_files'] > 1 for r in ts)}")

    P("\n## Per-task matrix (bucket code / gold-hunk overlap)")
    ab = {"resolved": "OK", "test_patch_conflict": "TP", "timeout_no_src_edit": "TO", "no_patch": "NP",
          "touched_tests_only": "TT", "wrong_location": "WL", "right_file_wrong_fix": "RF", "scratch_only": "SC"}
    by = defaultdict(dict)
    for r in rows:
        by[r["instance_id"]][r["config"]] = r
    P("| task | solves | gold files | hunks | size | " + " | ".join(CFGS) + " |")
    P("|---|---|---|---|---|" + "---|" * len(CFGS))
    for iid in sorted(by, key=lambda i: (-by[i]["c1"]["task_solves"], i)):
        d = by[iid]
        g = d["c1"]
        P(f"| {iid} | {g['task_solves']}/8 | {g['gold_n_files']} | {g['gold_n_hunks']} | {g['gold_size']} | "
          + " | ".join(f"{ab[d[c]['bucket']]} {d[c]['hunk_overlap']:.2g}" for c in CFGS) + " |")

    P("\n## Per config")
    for c in CFGS:
        sub = [r for r in rows if r["config"] == c]
        P(f"- {c}: resolved {sum(r['resolved'] for r in sub)}; buckets {dict(Counter(r['bucket'] for r in sub))}")


if __name__ == "__main__":
    main()
