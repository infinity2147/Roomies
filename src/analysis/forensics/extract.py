"""Build a per-(task, run) feature table from the 8 x 30 Kaggle pilot runs.

Usage: .venv/bin/python -m src.analysis.forensics.extract [--out reports/council/trajectory_table.csv]

Sources per run: results/kaggle/<run>/results/<run>/{task_results.jsonl, traces/, patches/, test_outputs/}
Gold: data/tasks.jsonl (patch, test_patch). Times are the ADK `elapsed_s` (seconds since session start).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from unidiff import PatchSet

ROOT = Path(__file__).resolve().parents[3]
RUNS = ["c1_n30", "c2_n30", "c3_n30", "c4_n30", "c5a_n30", "c5b_n30", "c6a_n30", "c6b_n30"]
TOOLS = ["run_command", "read_file", "edit_file", "write_file", "submit_patch", "get_status", "run_skill_script"]

TEST_RE = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
CONFIG_RE = re.compile(r"(^|/)(pyproject\.toml|setup\.cfg|tox\.ini|pytest\.ini|\.pre-commit-config\.yaml)$")
READ_CMD = re.compile(r"\b(cat|sed|head|tail|nl|awk|less|more)\b")
TEST_CMD = re.compile(r"\bpytest\b|unittest")
SCRATCH_RE = re.compile(r"(^|/)(repro|reproduce|debug|check_|scratch|tmp|temp_test)[^/]*$")
MALFORMED_MARK = re.compile(r"`,\w+:|<\|\"\|>|`$")


def is_test(p: str) -> bool:
    return bool(TEST_RE.search(p))


def run_dir(run: str) -> Path:
    return ROOT / "results" / "kaggle" / run / "results" / run


def load_tasks() -> dict:
    return {json.loads(l)["instance_id"]: json.loads(l) for l in open(ROOT / "data" / "tasks.jsonl") if l.strip()}


def parse_patch(txt: str):
    try:
        return PatchSet(txt)
    except Exception:  # noqa: BLE001
        return []


def patch_stats(ps, gold_files: tuple = ()) -> dict:
    """Split patch files into src / tests / config / scratch (new files that the gold patch does not add)."""
    files, src, tests, other, hunks, scratch = [], [], [], [], [], []
    added = removed = 0
    for f in ps:
        files.append(f.path)
        if is_test(f.path):
            tests.append(f.path)
        elif f.is_added_file and f.path not in gold_files and ("/" not in f.path or SCRATCH_RE.search(f.path)):
            scratch.append(f.path)
        elif f.path.endswith(".py") or not CONFIG_RE.search(f.path):
            src.append(f.path)
        if CONFIG_RE.search(f.path):
            other.append(f.path)
        for h in f:
            hunks.append((f.path, h.source_start, h.source_length))
            added += h.added
            removed += h.removed
    return dict(files=files, src=src, tests=tests, config=other, scratch=scratch, hunks=hunks, added=added, removed=removed)


def hunk_overlap(gold_hunks, agent_hunks, slack=3) -> float:
    """Fraction of gold hunks whose source line range (+-slack) overlaps an agent hunk in the same file."""
    if not gold_hunks:
        return 0.0
    hit = 0
    for gf, gs, gl in gold_hunks:
        for af, as_, al in agent_hunks:
            if af == gf and as_ <= gs + gl + slack and gs - slack <= as_ + max(al, 1):
                hit += 1
                break
    return hit / len(gold_hunks)


def parse_test_output(path: Path) -> dict:
    if not path.exists():
        return dict(t_failed=None, t_passed=None, t_errors=None, t_err_types="")
    txt = path.read_text(errors="ignore")
    out = dict(t_failed=0, t_passed=0, t_errors=0)
    m = None
    for m in re.finditer(r"^=*\s*((?:\d+ \w+(?:, )?)+) in [\d.]+s", txt, re.M):
        pass
    if m:
        for n, kind in re.findall(r"(\d+) (\w+)", m.group(1)):
            if kind.startswith("fail"):
                out["t_failed"] = int(n)
            elif kind == "passed":
                out["t_passed"] = int(n)
            elif kind.startswith("error"):
                out["t_errors"] = int(n)
    types = Counter(re.findall(r"^E\s+(\w+(?:Error|Exception|Warning))\b", txt, re.M))
    if "assert" in txt and re.search(r"^E\s+assert", txt, re.M):
        types["assert"] += len(re.findall(r"^E\s+assert", txt, re.M))
    out["t_err_types"] = ";".join(f"{k}={v}" for k, v in types.most_common(4))
    return out


def args_text(a) -> str:
    try:
        return json.dumps(a, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(a)


def mentions(text: str, path: str) -> bool:
    return path in text


def norm_fp(fp: str) -> str:
    fp = str(fp or "").split("`")[0].strip()
    return fp.removeprefix("/workspace/").removeprefix("./")


def trace_features(trace_path: Path, gold_src: list[str]) -> dict:
    f: dict = {}
    tr = json.loads(trace_path.read_text()) if trace_path.exists() else {"steps": []}
    calls = []
    for s in tr.get("steps", []):
        if s.get("source") != "agent":
            continue
        obs = (s.get("observation") or {}).get("content", "")
        for tc in s.get("tool_calls") or []:
            ex = tc.get("extra") or {}
            calls.append((tc.get("function_name"), tc.get("arguments") or {}, obs, ex.get("elapsed_s")))
    c = Counter(name for name, *_ in calls)
    f["n_calls"] = len(calls)
    sigs = Counter(f"{n}|{args_text(a)}" for n, a, *_ in calls if n not in ("get_status", "submit_patch"))
    f["n_dup_calls"] = sum(v - 1 for v in sigs.values())
    f["max_identical_repeat"] = max(sigs.values(), default=0)
    f["repeat_loop"] = int(f["max_identical_repeat"] >= 5)
    fm = tr.get("final_metrics") or {}
    f["completion_tokens"] = fm.get("total_completion_tokens")
    f["prompt_tokens"] = fm.get("total_prompt_tokens")
    f["n_llm_steps"] = sum(1 for s in tr.get("steps", []) if s.get("source") == "agent")
    for t in TOOLS:
        f[f"n_{t}"] = c.get(t, 0)
    f["n_other_tool"] = sum(v for k, v in c.items() if k not in TOOLS)
    f["n_locate"] = sum(1 for n, a, *_ in calls if n == "run_skill_script" and "locate" in args_text(a))
    malformed = edit_ok = edit_fail = edit_missing_arg = 0
    first_gold_mention = first_gold_read = first_edit = first_gold_edit = None
    first_edit_idx = None
    gold_edits = tests_run = tests_after_edit = repro_after_edit = 0
    test_file_edits = tmp_write_blocked = gold_edit_missing = 0
    longest_fail_streak = streak = 0
    last_t = None
    edited_files: list[str] = []
    for i, (name, a, obs, t) in enumerate(calls):
        last_t = t if t is not None else last_t
        at = args_text(a)
        bad_keys = any(not re.fullmatch(r"[a-z_]+", k) for k in a) if isinstance(a, dict) else True
        try:
            oj = json.loads(obs) if obs else {}
        except Exception:  # noqa: BLE001
            oj = {}
        missing = "mandatory input parameters" in str(oj.get("error", "")) or oj.get("error_code") == "INVALID_ARGUMENTS"
        if bad_keys or missing or MALFORMED_MARK.search(at):
            malformed += 1
        if any(mentions(at, g) for g in gold_src) and first_gold_mention is None:
            first_gold_mention = (i, t)
        if name == "read_file" and norm_fp(a.get("filepath")) in gold_src and oj.get("status") == "ok":
            if first_gold_read is None:
                first_gold_read = (i, t)
        if name == "run_command":
            cmd = str(a.get("command", ""))
            if first_gold_read is None and READ_CMD.search(cmd) and any(g in cmd for g in gold_src):
                first_gold_read = (i, t)
            is_test_run = bool(TEST_CMD.search(cmd))
            tests_run += is_test_run
            if first_edit_idx is not None:
                tests_after_edit += is_test_run
                if re.search(r"\bpython3?\b", cmd) and not is_test_run:
                    repro_after_edit += 1
        if name == "run_skill_script" and ("tests.py" in at or "check.py" in at):
            tests_run += 1
            if first_edit_idx is not None:
                tests_after_edit += 1
        if name in ("edit_file", "write_file") and oj.get("status") != "ok":
            streak += 1
            longest_fail_streak = max(longest_fail_streak, streak)
        elif name in ("edit_file", "write_file"):
            streak = 0
        if name in ("edit_file", "write_file"):
            fp = norm_fp(a.get("filepath"))
            if missing:
                edit_missing_arg += 1
                if fp in gold_src:
                    gold_edit_missing += 1
            if oj.get("status") == "ok":
                if name == "write_file" and fp.startswith("/tmp"):
                    continue
                if is_test(fp):
                    test_file_edits += 1
                edit_ok += 1
                edited_files.append(fp)
                if first_edit is None and not is_test(fp) and fp.endswith(".py"):
                    first_edit = (i, t)
                    first_edit_idx = i
                if fp in gold_src:
                    gold_edits += 1
                    if first_gold_edit is None:
                        first_gold_edit = (i, t)
            else:
                edit_fail += 1
                if "Path traversal" in str(oj.get("error_message", "")):
                    tmp_write_blocked += 1
        if name == "run_command" and re.search(r"sed -i|> *\S+\.py|tee ", str(a.get("command", ""))):
            cmd = str(a.get("command", ""))
            for g in gold_src:
                if g in cmd and re.search(r"sed -i", cmd):
                    gold_edits += 1
                    if first_gold_edit is None:
                        first_gold_edit = (i, t)
                    if first_edit is None:
                        first_edit = (i, t)
                        first_edit_idx = i
    f.update(
        n_malformed=malformed, n_edit_ok=edit_ok, n_edit_fail=edit_fail, n_edit_missing_arg=edit_missing_arg, n_gold_edit_missing_arg=gold_edit_missing,
        longest_edit_fail_streak=longest_fail_streak,
        n_gold_edits=gold_edits, n_test_runs=tests_run, n_test_runs_after_edit=tests_after_edit,
        n_repro_after_edit=repro_after_edit, n_test_file_edits=test_file_edits, n_tmp_write_blocked=tmp_write_blocked,
        last_call_t=round(last_t, 1) if last_t else None,
        edited_files="|".join(sorted(set(edited_files))),
        submit_called=int(c.get("submit_patch", 0) > 0),
    )
    for key, v in [("gold_mention", first_gold_mention), ("gold_read", first_gold_read), ("first_edit", first_edit),
                   ("gold_edit", first_gold_edit)]:
        f[f"{key}_call"] = v[0] if v else None
        f[f"{key}_t"] = round(v[1], 1) if v and v[1] is not None else None
    return f


def classify(r: dict) -> str:
    if r["resolved"]:
        return "resolved"
    err = r["error"] or ""
    if "Failed to apply test_patch" in err:
        return "test_patch_conflict"
    if not r["agent_src_files"]:
        if "timeout" in err.lower() or r["duration"] >= 470:
            return "timeout_no_src_edit"
        if not r["agent_files"]:
            return "no_patch"
        return "touched_tests_only" if r["agent_test_files"] else "scratch_only"
    if not r["files_overlap"]:
        return "wrong_location"
    return "right_file_wrong_fix"


def build() -> list[dict]:
    tasks = load_tasks()
    rows = []
    for run in RUNS:
        rd = run_dir(run)
        for line in open(rd / "task_results.jsonl"):
            tr = json.loads(line)
            iid = tr["instance_id"]
            t = tasks[iid]
            gs = patch_stats(parse_patch(t["patch"]))
            gold_src = [p for p in gs["files"] if not is_test(p)]
            pf = rd / "patches" / f"{iid}.patch"
            ptxt = pf.read_text(errors="ignore") if pf.exists() else ""
            ag = patch_stats(parse_patch(ptxt), tuple(gs["files"]))
            r = dict(run=run, config=run.removesuffix("_n30"), instance_id=iid, repo=iid.split("_")[0],
                     resolved=int(bool(tr.get("resolved"))), duration=round(tr.get("duration_seconds") or 0, 1),
                     error=(tr.get("error") or "").split("\n")[0][:120], test_exit_code=tr.get("test_exit_code"),
                     reported_tool_calls=tr.get("tool_calls"))
            r.update(trace_features(rd / "traces" / f"trace_{iid}.json", gold_src))
            r.update(gold_files="|".join(gold_src), gold_n_files=len(gold_src), gold_n_hunks=len(gs["hunks"]),
                     gold_size=gs["added"] + gs["removed"],
                     agent_files="|".join(ag["files"]), agent_src_files="|".join(ag["src"]),
                     agent_test_files="|".join(ag["tests"]), agent_config_files="|".join(ag["config"]),
                     agent_scratch_files="|".join(ag["scratch"]),
                     agent_size=ag["added"] + ag["removed"], agent_n_hunks=len(ag["hunks"]))
            ov = set(ag["src"]) & set(gold_src)
            r["files_overlap"] = len(ov)
            r["gold_files_covered"] = round(len(ov) / max(len(gold_src), 1), 2)
            r["extra_src_files"] = len(set(ag["src"]) - set(gold_src))
            r["hunk_overlap"] = round(hunk_overlap(gs["hunks"], ag["hunks"]), 2)
            r.update(parse_test_output(rd / "test_outputs" / f"{iid}.log"))
            r["hit_time_limit"] = int(r["duration"] >= 470 or "timeout" in r["error"].lower())
            r["bucket"] = classify(r)
            rows.append(r)
    # per-task solve counts
    solved = Counter(r["instance_id"] for r in rows if r["resolved"])
    for r in rows:
        k = solved.get(r["instance_id"], 0)
        r["task_solves"] = k
        r["task_class"] = "always" if k == len(RUNS) else ("never" if k == 0 else "stochastic")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "council" / "trajectory_table.csv"))
    a = ap.parse_args()
    rows = build()
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
