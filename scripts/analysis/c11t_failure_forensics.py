#!/usr/bin/env python3
"""Failure forensics for proxy runs (default: C11t vs C9ae on the 152 proxy tasks).

Reads only results/px/<run>/s*/{task_results.jsonl,traces,patches,test_outputs}
and data/derived/proxy/valid_tasks.jsonl (gold patch + test_patch).
Writes one CSV row per task with per-run class + diagnostics. Idempotent.

Usage: python3 scripts/analysis/c11t_failure_forensics.py [--runs px_c11t_s1 px_c9ae_s1] [--out reports/autopilot/c11t_failures_20261007.csv]
"""
import argparse, csv, glob, json, os, re, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLASSES = [  # priority order, first match wins
    "test_file_edited",     # (c') test_patch fails to apply: agent edited test files
    "context_overflow",     # (b) litellm.ContextWindowExceededError (root or analyzer)
    "session_timeout",      # (g) 60-min session timeout
    "llm_turn_cap",         # harness max LLM turns
    "tool_budget_empty",    # (f) 100 tool calls used, no patch
    "no_submit",            # (a) finished without submit_patch and no diff
    "empty_patch",          # (a) submitted, but patch empty
    "test_hang",            # patch makes the test run hang (exit 124)
    "collection_error",     # patch breaks import/collection (Import/Syntax/NameError)
    "wrong_file",           # (c) patch touches none of the gold files
    "regression_only",      # (e) gold files touched, only pre-existing tests fail
    "wrong_fix",            # (d) gold files touched, FAIL_TO_PASS tests still fail
]


def norm_path(p):
    p = p.strip().strip('"\'')
    for pre in ("/workspace/", "./", "a/", "b/"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def diff_files(text):
    files = set()
    for m in re.finditer(r"^\+\+\+ (?:b/)?(\S+)", text, re.M):
        if m.group(1) != "/dev/null":
            files.add(norm_path(m.group(1)))
    for m in re.finditer(r"^diff --git a/(\S+) b/", text, re.M):
        files.add(norm_path(m.group(1)))
    return files


def is_test_path(p):
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_test\.py$|conftest\.py$", p))


def test_names_in_patch(test_patch):
    # any test identifier mentioned in the test_patch (def lines, hunk headers, parametrize ids);
    # a failing test whose name never appears in the test_patch is a pre-existing (PASS_TO_PASS) test
    return set(re.findall(r"\b(test_?\w+)", test_patch))


def failed_tests(test_out):
    ids = re.findall(r"^(?:FAILED|ERROR) (\S+)", test_out, re.M)
    names = set()
    for t in ids:
        t = t.split("::")[-1].split("[")[0]
        names.add(t)
    return ids, names


def load_tasks():
    tasks = {}
    with open(os.path.join(ROOT, "data/derived/proxy/valid_tasks.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            tasks[r["instance_id"]] = r
    return tasks


def load_run(run):
    base = os.path.join(ROOT, "results/px", run)
    rows = {}
    for shard in sorted(glob.glob(os.path.join(base, "s*"))):
        trf = os.path.join(shard, "task_results.jsonl")
        if not os.path.exists(trf):
            continue
        with open(trf) as f:
            for line in f:
                r = json.loads(line)
                r["_shard"] = shard
                rows[r["instance_id"]] = r
    return rows


def read_text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def trace_stats(trace, gold_files):
    """Per-trace diagnostics: tool calls by author, edit failures/loops, gold file reads, tokens, thinking."""
    st = dict(root_tool_calls=0, analyzer_tool_calls=0, root_llm_calls=0, analyzer_llm_calls=0,
              edit_calls=0, failed_edits=0, identical_failed_edits=0, submit_calls=0,
              read_gold=False, edited_gold=False, read_gold_root=False,
              output_tokens=0, root_output_tokens=0, prompt_tokens=0,
              thinking_steps=0, thinking_chars=0, reverted=False, nudges=0, max_output_hits=0)
    if not trace:
        return st
    gold_set = set(gold_files)
    failed_edit_args = Counter()
    for s in trace.get("steps", []):
        ex = s.get("extra") or {}
        author = ex.get("author")
        et = ex.get("event_type")
        if et == "continuation_nudge":
            st["nudges"] += 1
        if s.get("source") != "agent":
            continue
        is_root = author == "swe_coder"
        m = s.get("metrics") or {}
        ct = m.get("completion_tokens", 0) or 0
        st["output_tokens"] += ct
        st["prompt_tokens"] += m.get("prompt_tokens", 0) or 0
        if ct >= 4096:
            st["max_output_hits"] += 1
        n_llm = s.get("llm_call_count", 0) or 0
        if is_root:
            st["root_llm_calls"] += n_llm
            st["root_output_tokens"] += ct
            if et == "thinking" and (s.get("message") or "").strip():
                st["thinking_steps"] += 1
                st["thinking_chars"] += len(s["message"])
        else:
            st["analyzer_llm_calls"] += n_llm
        obs = s.get("observation") or {}
        status = None
        try:
            status = json.loads(obs.get("content", "") or "{}").get("status")
        except Exception:
            status = None
        for tc in s.get("tool_calls") or []:
            fn = tc.get("function_name")
            args = tc.get("arguments") or {}
            if is_root:
                st["root_tool_calls"] += 1
            else:
                st["analyzer_tool_calls"] += 1
            if fn == "submit_patch":
                st["submit_calls"] += 1
            txt = json.dumps(args)
            if fn in ("read_file", "edit_file", "write_file"):
                fp = norm_path(str(args.get("filepath") or args.get("path") or ""))
                if fp in gold_set:
                    if fn == "read_file":
                        st["read_gold"] = True
                        if is_root:
                            st["read_gold_root"] = True
                    else:
                        st["edited_gold"] = True
            if fn == "run_command":
                cmd = str(args.get("command", ""))
                if any(g in cmd for g in gold_set):
                    st["read_gold"] = True
                    if is_root:
                        st["read_gold_root"] = True
                if re.search(r"git (checkout|restore|stash)\b.*(--|\.)|git checkout -- \.", cmd):
                    st["reverted"] = True
            if fn == "edit_file":
                st["edit_calls"] += 1
                if status == "error":
                    st["failed_edits"] += 1
                    failed_edit_args[txt] += 1
    if failed_edit_args:
        st["identical_failed_edits"] = max(failed_edit_args.values())
    return st


def classify(r, task, patch_text, test_out, st):
    err = r.get("error") or ""
    psize = r.get("agent_patch_size") or 0
    exit_code = r.get("test_exit_code")
    gold_files = diff_files(task["patch"])
    patch_files = diff_files(patch_text) if patch_text else set()
    touched_gold = bool(patch_files & gold_files)
    fids, fnames = failed_tests(test_out)
    ftp_names = test_names_in_patch(task["test_patch"])
    sub = ""
    # harness errors (timeout / turn cap / overflow) only count as the primary cause when the patch
    # was never evaluated (exit -1) or is empty; otherwise the submitted patch ran and the test
    # outcome is the primary cause (the budget error is then a tag: submit_loop / nudges).
    unevaluated = exit_code in (None, -1) or psize == 0
    if err.startswith("Failed to apply test_patch"):
        c = "test_file_edited"
        sub = ",".join(sorted(p for p in patch_files if is_test_path(p)))[:120]
    elif "ContextWindowExceeded" in err and unevaluated:
        c = "context_overflow"
        sub = "analyzer" if st["analyzer_tool_calls"] > st["root_tool_calls"] else "root"
    elif "session timeout" in err and unevaluated:
        c = "session_timeout"
        sub = "empty_patch" if psize == 0 else "patch_submitted"
    elif "maximum allowed LLM turns" in err and unevaluated:
        c = "llm_turn_cap"
        sub = "empty_patch" if psize == 0 else "patch_submitted"
    elif ("tool call budget" in err and unevaluated) or (r.get("tool_calls", 0) >= 100 and psize == 0):
        c = "tool_budget_empty"
        sub = "analyzer_ate_budget" if st["analyzer_tool_calls"] >= 40 else ("edit_loop" if st["failed_edits"] >= 8 or st["identical_failed_edits"] >= 5 else "explore_loop")
    elif "without calling submit_patch" in err:
        c = "no_submit"
    elif psize == 0:
        c = "empty_patch"
        if st["reverted"]:
            sub = "reverted"
        elif st["failed_edits"] >= 8 or st["identical_failed_edits"] >= 5:
            sub = "edit_loop"
        elif st["analyzer_tool_calls"] >= 40:
            sub = "analyzer_ate_budget"
        elif st["edit_calls"] == 0:
            sub = "never_edited"
        else:
            sub = "other"
    elif exit_code == 124:
        c = "test_hang"
    elif exit_code in (2, 4) or re.search(r"^E\s+(ImportError|ModuleNotFoundError|SyntaxError|NameError|IndentationError)|error during collection|ERROR collecting", test_out, re.M):
        c = "collection_error"
        m = re.search(r"E\s+((?:ImportError|ModuleNotFoundError|SyntaxError|NameError|IndentationError|AttributeError)[^\n]{0,80})", test_out)
        sub = (m.group(1) if m else "")[:100]
    elif not touched_gold:
        c = "wrong_file"
        sub = "no_patch_files" if not patch_files else ("read_gold" if st["read_gold"] else "never_read_gold")
    elif fnames and not (fnames & ftp_names):
        c = "regression_only"
        sub = ",".join(sorted(fnames))[:120]
    else:
        c = "wrong_fix"
        if not fnames:
            sub = "no_FAILED_lines"
        else:
            sub = f"{len(fids)} failing: " + ",".join(sorted(fnames))[:100]
    return c, sub, gold_files, patch_files, fids


def analyze(run, tasks):
    rows = load_run(run)
    out = {}
    for iid, r in rows.items():
        task = tasks.get(iid)
        if task is None:
            continue
        shard = r["_shard"]
        patch_text = read_text(os.path.join(shard, "patches", f"{iid}.patch"))
        test_out = read_text(os.path.join(shard, "test_outputs", f"{iid}.log"))
        tpath = os.path.join(shard, "traces", f"trace_{iid}.json")
        trace = None
        if os.path.exists(tpath):
            try:
                with open(tpath) as f:
                    trace = json.load(f)
            except Exception as e:
                print(f"warn: bad trace {tpath}: {e}", file=sys.stderr)
        gold_files = diff_files(task["patch"])
        st = trace_stats(trace, gold_files)
        if r["resolved"]:
            c, sub, patch_files, fids = "resolved", "", diff_files(patch_text), []
        else:
            c, sub, _, patch_files, fids = classify(r, task, patch_text, test_out, st)
        out[iid] = dict(
            instance_id=iid, repo=r["repo"], resolved=int(bool(r["resolved"])), cls=c, subclass=sub,
            error=(r.get("error") or "")[:60].replace("\n", " "), test_exit_code=r.get("test_exit_code"),
            duration_s=round(r.get("duration_seconds") or 0), tool_calls=r.get("tool_calls"),
            patch_size=r.get("agent_patch_size"), gold_files="|".join(sorted(gold_files)),
            patch_files="|".join(sorted(patch_files))[:200], touched_gold=int(bool(patch_files & gold_files)),
            n_failed_tests=len(fids), submit_loop=int(st["submit_calls"] >= 10),
            budget_error=("turn_cap" if "LLM turns" in (r.get("error") or "") else "timeout" if "session timeout" in (r.get("error") or "") else "tool_budget" if "tool call budget" in (r.get("error") or "") else ""), **st,
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["px_c11t_s1", "px_c9ae_s1"])
    ap.add_argument("--out", default="reports/autopilot/c11t_failures_20261007.csv")
    a = ap.parse_args()
    tasks = load_tasks()
    per_run = {run: analyze(run, tasks) for run in a.runs}
    main_run, ref_run = a.runs[0], (a.runs[1] if len(a.runs) > 1 else None)
    ids = sorted(set(per_run[main_run]) | (set(per_run[ref_run]) if ref_run else set()))
    fields = list(next(iter(per_run[main_run].values())).keys())
    out_path = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        hdr = ["instance_id", "repo"] + [f"{main_run}:{k}" for k in fields if k not in ("instance_id", "repo")]
        if ref_run:
            hdr += [f"{ref_run}:{k}" for k in fields if k not in ("instance_id", "repo")]
        w.writerow(hdr)
        for iid in ids:
            m = per_run[main_run].get(iid) or {}
            row = [iid, m.get("repo") or (per_run[ref_run].get(iid) or {}).get("repo")]
            row += [m.get(k, "") for k in fields if k not in ("instance_id", "repo")]
            if ref_run:
                rr = per_run[ref_run].get(iid) or {}
                row += [rr.get(k, "") for k in fields if k not in ("instance_id", "repo")]
            w.writerow(row)
    # summary to stdout
    print(f"wrote {out_path} ({len(ids)} tasks)")
    for run in a.runs:
        cnt = Counter(v["cls"] for v in per_run[run].values())
        print(f"\n== {run}: {sum(v['resolved'] for v in per_run[run].values())}/{len(per_run[run])} resolved")
        for c in ["resolved"] + CLASSES:
            if cnt.get(c):
                subs = Counter(v["subclass"].split(":")[0][:40] for v in per_run[run].values() if v["cls"] == c and c not in ("wrong_fix", "regression_only", "test_file_edited", "collection_error"))
                print(f"  {c:18s} {cnt[c]:3d}  {dict(subs) if subs else ''}")
    if ref_run:
        print(f"\n== transitions {ref_run} -> {main_run}")
        tr = Counter((per_run[ref_run][i]["cls"], per_run[main_run][i]["cls"]) for i in ids if i in per_run[ref_run] and i in per_run[main_run])
        for (a_, b_), n in sorted(tr.items(), key=lambda x: -x[1]):
            if a_ != b_:
                print(f"  {a_:18s} -> {b_:18s} {n}")
        print("\n== per-class examples (main run failures)")
        for c in CLASSES:
            ex = [(v["instance_id"], v["subclass"][:70], v["tool_calls"], v["root_output_tokens"], v["read_gold"]) for v in per_run[main_run].values() if v["cls"] == c]
            if ex:
                print(f"  [{c}]")
                for e in ex[:8]:
                    print("    ", e)
        print("\n== failing-task diagnostics (main run)")
        fails = [v for v in per_run[main_run].values() if not v["resolved"]]
        import statistics as S
        def med(k): return S.median([v[k] for v in fails]) if fails else 0
        print(f"  n_fail={len(fails)} read_gold={sum(v['read_gold'] for v in fails)} read_gold_root={sum(v['read_gold_root'] for v in fails)} edited_gold={sum(v['edited_gold'] for v in fails)} thinking_present={sum(v['thinking_steps']>0 for v in fails)}")
        print(f"  median tool_calls={med('tool_calls')} root_output_tokens={med('root_output_tokens')} output_tokens={med('output_tokens')} duration_s={med('duration_s')} ; tool_calls>=100: {sum(v['tool_calls']>=100 for v in fails)}")
        print(f"  edit-loop tag (failed_edits>=8 or identical>=5): {sum((v['failed_edits']>=8 or v['identical_failed_edits']>=5) for v in fails)} ; submit>=10: {sum(v['submit_calls']>=10 for v in fails)} ; analyzer_tool_calls>=40: {sum(v['analyzer_tool_calls']>=40 for v in fails)}")


if __name__ == "__main__":
    main()
