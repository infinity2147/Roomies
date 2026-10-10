#!/usr/bin/env python3
"""Trajectory-level failure signals for proxy runs (default: C9e s1+s2; also C17 s1..s3).

Deterministic signals per (run, task): gold-file / gold-function read & touched, analyzer localisation,
edit-call health (malformed / not-found / ok), repeated identical calls, reproduction behaviour,
agent-side test runs, final-patch hygiene (empty, test/scratch files, syntax), hidden-test outcome split
into FAIL_TO_PASS (F2P) vs regressions, budget errors, waste after the last code mutation.

F2P is reconstructed from results/verify_prajna_proxy_empty/logs/<iid>.log (tests that fail on the
unpatched base; all 152 tasks pass with the gold patch in verify_prajna_proxy_gold).

Inputs (read-only): results/px/<run>/<shard>/{task_results.jsonl,traces,patches,test_outputs},
data/derived/proxy/valid_tasks.jsonl, data/derived/proxy/repos/<repo> (git, base commits).
Outputs: results/failure_analysis/<name>_all.jsonl (every run) and <name>_failures.jsonl (resolved=false).

Usage: .venv/bin/python src/analysis/failure_c9e.py [--runs px_c9e_s1 px_c9e_s2] [--name c9e]
"""
import argparse, ast, glob, json, os, re, subprocess, sys, tempfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPOS = os.path.join(ROOT, "data/derived/proxy/repos")
EMPTY_LOGS = os.path.join(ROOT, "results/verify_prajna_proxy_empty/logs")

# ----------------------------------------------------------------------------- diff helpers

def norm_path(p):
    p = (p or "").strip().strip("\"'`")
    for pre in ("/workspace/", "./", "a/", "b/"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def parse_diff(text):
    """-> {path: {"old_lines": set(int), "new": bool, "deleted": bool, "added": int, "removed": int}}"""
    files = {}
    cur = None
    old_ln = None
    old_path = None
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            cur = None
            continue
        if line.startswith("--- "):
            old_path = line[4:].split("\t")[0]
            continue
        if line.startswith("+++ "):
            new_path = line[4:].split("\t")[0]
            path = norm_path(new_path if new_path != "/dev/null" else old_path)
            cur = files.setdefault(path, dict(old_lines=set(), new=old_path == "/dev/null",
                                               deleted=new_path == "/dev/null", added=0, removed=0))
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m and cur is not None:
            old_ln = int(m.group(1))
            continue
        if cur is None or old_ln is None:
            continue
        if line.startswith("-"):
            cur["old_lines"].add(old_ln)
            cur["removed"] += 1
            old_ln += 1
        elif line.startswith("+"):
            # insertion point: between old_ln-1 and old_ln
            cur["old_lines"].add(max(old_ln - 1, 1))
            cur["added"] += 1
        elif line.startswith("\\"):
            pass
        else:
            old_ln += 1
    return files


def is_test_path(p):
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|(^|/)pytest\.ini$", p))


def is_doc_path(p):
    return bool(re.search(r"\.(rst|md|txt)$|(^|/)docs?/|CHANGES|CHANGELOG|HISTORY", p, re.I))


def is_scratch_new(p):
    b = os.path.basename(p)
    return bool(re.search(r"repro|debug|scratch|tmp|temp|\.orig$|\.rej$|\.bak$|\.pyc$|^test_.*\.py$|_test\.py$|verify|check_", b, re.I)) or ("/" not in p and b.endswith(".py"))


# ----------------------------------------------------------------------------- source / functions

_src_cache = {}


def repo_dir(repo):
    name = repo.split("/")[1]
    for d in (name, name.replace("-", "_"), name.replace("_", "-")):
        if os.path.isdir(os.path.join(REPOS, d)):
            return os.path.join(REPOS, d)
    return None


def git_show(repo, commit, path):
    key = (repo, commit, path)
    if key not in _src_cache:
        d = repo_dir(repo)
        txt = None
        if d:
            p = subprocess.run(["git", "-C", d, "show", f"{commit}:{path}"], capture_output=True)
            if p.returncode == 0:
                txt = p.stdout.decode("utf-8", "replace")
        _src_cache[key] = txt
    return _src_cache[key]


_def_cache = {}


def defs_of(repo, commit, path):
    """[(start, end, qualname, kind)] for every def/class in the original file."""
    key = (repo, commit, path)
    if key in _def_cache:
        return _def_cache[key]
    out = []
    src = git_show(repo, commit, path) if path.endswith(".py") else None
    if src:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = None
        if tree is not None:
            def walk(node, prefix):
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        q = f"{prefix}.{ch.name}" if prefix else ch.name
                        start = min([ch.lineno] + [d.lineno for d in getattr(ch, "decorator_list", [])])
                        out.append((start, ch.end_lineno, q, "class" if isinstance(ch, ast.ClassDef) else "func"))
                        walk(ch, q)
                    else:
                        walk(ch, prefix)
            walk(tree, "")
    _def_cache[key] = out
    return out


def enclosing(defs, line):
    """innermost def/class covering line -> (qualname, start, end) or ('<module>', None, None)"""
    best = None
    for s, e, q, k in defs:
        if s <= line <= e and (best is None or (e - s) < (best[2] - best[1])):
            best = (q, s, e)
    return best or ("<module>", None, None)


def funcs_for_diff(repo, commit, dfiles):
    """-> {path: {qualname: (start,end)}} for each changed old line; new files -> '<newfile>'"""
    res = {}
    for p, info in dfiles.items():
        if info["new"]:
            res[p] = {"<newfile>": (None, None)}
            continue
        defs = defs_of(repo, commit, p)
        fs = {}
        for ln in info["old_lines"]:
            q, s, e = enclosing(defs, ln)
            fs[q] = (s, e)
        res[p] = fs
    return res


def compile_check(repo, commit, patch_text, dfiles):
    """apply agent patch to original copies of touched .py files and py_compile them -> (ok, msg)"""
    pyfiles = [p for p, i in dfiles.items() if p.endswith(".py") and not i["deleted"]]
    if not pyfiles:
        return True, ""
    with tempfile.TemporaryDirectory() as td:
        for p, i in dfiles.items():
            if i["new"]:
                continue
            src = git_show(repo, commit, p)
            if src is None:
                continue
            fp = os.path.join(td, p)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w") as f:
                f.write(src)
        pf = os.path.join(td, "__agent.patch")
        with open(pf, "w") as f:
            f.write(patch_text if patch_text.endswith("\n") else patch_text + "\n")
        r = subprocess.run(["git", "apply", "--unsafe-paths", "--directory=", "-p1", pf], cwd=td, capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run(["patch", "-p1", "-s", "-i", pf], cwd=td, capture_output=True, text=True)
            if r.returncode != 0:
                return None, "apply_failed"
        for p in pyfiles:
            fp = os.path.join(td, p)
            if not os.path.exists(fp):
                continue
            try:
                with open(fp) as f:
                    compile(f.read(), p, "exec")
            except SyntaxError as e:
                return False, f"{type(e).__name__}: {p}:{e.lineno} {e.msg}"[:160]
    return True, ""


# ----------------------------------------------------------------------------- tests

def failed_ids(text):
    return re.findall(r"^(?:FAILED|ERROR) (\S+)", text or "", re.M)


_f2p_cache = {}


def f2p_for(iid):
    if iid not in _f2p_cache:
        p = os.path.join(EMPTY_LOGS, f"{iid}.log")
        txt = open(p, errors="replace").read() if os.path.exists(p) else ""
        _f2p_cache[iid] = set(failed_ids(txt))
    return _f2p_cache[iid]


def split_hidden(iid, test_out):
    f2p = f2p_for(iid)
    f2p_files = {t for t in f2p if "::" not in t}  # collection errors on base -> whole file is F2P
    fails = set(failed_ids(test_out))
    f2p_fail, regress = set(), set()
    for t in fails:
        if t in f2p or t.split("::")[0] in f2p_files:
            f2p_fail.add(t)
        else:
            regress.add(t)
    tot = len([t for t in f2p if "::" in t])
    m = re.search(r"(\d+) passed", test_out or "")
    base_txt = read_text(os.path.join(EMPTY_LOGS, f"{iid}.log"))
    imp_agent = set(re.findall(r"cannot import name '(\w+)'", test_out or ""))
    imp_base = set(re.findall(r"cannot import name '(\w+)'", base_txt))
    agent_syntax = bool(re.search(r"^E\s+(SyntaxError|IndentationError)|^E\s+File .*\.py\", line \d+", test_out or "", re.M))
    return dict(missing_required_symbol=sorted(imp_agent & imp_base), agent_broke_import=sorted(imp_agent - imp_base),
                hidden_syntax_err=agent_syntax,f2p_total=tot if not f2p_files else -1, f2p_fail=len(f2p_fail), regress=len(regress),
                regress_ids=sorted(regress)[:6], f2p_fail_ids=sorted(f2p_fail)[:6],
                hidden_passed=int(m.group(1)) if m else 0,
                hidden_collect_err=bool(re.search(r"ERROR collecting|error during collection|^E\s+(ImportError|ModuleNotFoundError|SyntaxError|IndentationError)", test_out or "", re.M)))


# ----------------------------------------------------------------------------- trace

MUT_CMD = re.compile(r"sed\s+-i|perl\s+-p?i|>\s*(?!/tmp|/dev)[\w./-]+\.py\b|tee\s+(?!/tmp)[\w./-]+\.py|git\s+(checkout|restore|apply|stash)|\bpatch\s+-p|\.write_text\(|open\([^)]*['\"]w['\"]")
PY_RUN = re.compile(r"(^|[;&|\s])python3?\s+(?!-m\s+(pytest|py_compile|pip))(-c\s|/tmp/|[\w./-]+\.py)")
FAIL_OUT = re.compile(r"Traceback|Error\b|assert|FAIL|BUG|Bug|bug|wrong|unexpected|Expected|expected|!=|False", re.M)


def obs_json(s):
    o = s.get("observation") or {}
    try:
        c = json.loads(o.get("content") or "{}")
        return c if isinstance(c, dict) else {"_raw": c}
    except Exception:
        return {"_raw": o.get("content")}


def call_failed(c):
    return c.get("status") == "error" or "error" in c and "status" not in c


def read_ranges_from_call(fn, args, c):
    """-> list of (path, start, end) regions the call displayed"""
    out = []
    if fn == "read_file":
        p = norm_path(str(args.get("filepath") or args.get("path") or ""))
        if c.get("status") == "ok":
            out.append((norm_path(c.get("filepath") or p), c.get("start_line") or 1, c.get("end_line") or 10 ** 6))
    elif fn == "run_command" and not call_failed(c):
        cmd = str(args.get("command", ""))
        for m in re.finditer(r"sed\s+-n\s+['\"]?(\d+),(\d+)p['\"]?\s+([\w./-]+)", cmd):
            out.append((norm_path(m.group(3)), int(m.group(1)), int(m.group(2))))
        for m in re.finditer(r"\b(?:cat|nl\s+-ba|head\s+-n\s*\d+|head\s+-\d+)\s+([\w./-]+\.py)", cmd):
            out.append((norm_path(m.group(1)), 1, 400))
        # grep -n output lines "path:line:" give one-line glimpses
        stdout = str(c.get("stdout", ""))
        for m in re.finditer(r"^(?:\./)?([\w./-]+\.py):(\d+):", stdout, re.M):
            out.append((norm_path(m.group(1)), int(m.group(2)), int(m.group(2))))
    return out


def trace_signals(trace, task, gold_funcs):
    st = Counter()
    info = dict(analyzer_loc=None, analyzer_loc_gold_file=None, analyzer_loc_gold_func=None, analyzer_conf=None,
                read_gold_file=False, read_gold_file_root=False, read_gold_func=False, glimpse_gold_file=False,
                edited_files=[], first_edit_t=None, last_mut_t=None, first_submit_t=None,
                repro_written=False, repro_runs_pre=0, repro_pre_failed=False, repro_runs_post=0, repro_post_clean=None,
                pytest_runs=0, pytest_runs_post=0, last_pytest_post=None, pytest_hidden_file_run=False,
                py_compile_runs=0, overflow_author=None, last_text="", identical_max=0, end_t=0.0,
                calls_after_last_mut=0, malformed_kinds=[])
    if not trace:
        return st, info
    gold_files = set(gold_funcs)
    tp_files = set(parse_diff(task["test_patch"]))
    steps = trace.get("steps", [])
    seen = Counter()
    seen_an = Counter()
    first_mut = None
    root_calls = []  # (t, fn, args, c)
    for s in steps:
        ex = s.get("extra") or {}
        author = ex.get("author")
        et = ex.get("event_type")
        t = ex.get("elapsed_s") or 0.0
        st["max_gap_s"] = max(st["max_gap_s"], int(t - info["end_t"]))
        info["end_t"] = max(info["end_t"], t)
        if s.get("source") == "agent":
            st["agent_steps"] += 1
        if et == "continuation_nudge":
            st["nudges"] += 1
        if s.get("source") != "agent":
            continue
        if et == "thinking":
            st["thinking_steps"] += 1
        if et == "final" and author == "code_analyzer":
            msg = s.get("message") or ""
            st["analyzer_answers"] += 1
            m = re.search(r"LOCATION:\s*`?([\w./-]+\.py)`?(?::(\d+)(?:-(\d+))?)?", msg)
            if m:
                p = norm_path(m.group(1))
                a, b = int(m.group(2) or 0), int(m.group(3) or m.group(2) or 0)
                info["analyzer_loc"] = f"{p}:{a}-{b}"
                info["analyzer_loc_gold_file"] = any(p == g or p.endswith("/" + g) or g.endswith("/" + p) for g in gold_files)
                if info["analyzer_loc_gold_file"]:
                    gf = next(g for g in gold_files if p == g or p.endswith("/" + g) or g.endswith("/" + p))
                    hit = False
                    for q, (gs, ge) in gold_funcs[gf].items():
                        if gs is None:
                            hit = hit or q == "<module>"
                            continue
                        if a and not (b < gs - 3 or a > ge + 3):
                            hit = True
                    info["analyzer_loc_gold_func"] = hit
            mc = re.search(r"CONFIDENCE:\s*(\w+)", msg)
            info["analyzer_conf"] = mc.group(1).lower() if mc else None
        if et == "final" and author == "swe_coder":
            info["last_text"] = (s.get("message") or "")[:400]
        tcs = s.get("tool_calls") or []
        c = obs_json(s)
        for tc in tcs:
            fn = tc.get("function_name")
            args = tc.get("arguments") or {}
            is_root = author == "swe_coder"
            key = json.dumps([fn, args], sort_keys=True)
            failed = call_failed(c)
            if c.get("error_type") == "BudgetExceeded":
                st["budget_exceeded_calls"] += 1
            if is_root:
                st["root_calls"] += 1
                if fn not in ("submit_patch", "get_status"):
                    if seen[key]:
                        st["repeat_identical_root"] += 1
                    seen[key] += 1
                root_calls.append((t, fn, args, c))
            else:
                st["analyzer_calls"] += 1
                if seen_an[key]:
                    st["repeat_identical_analyzer"] += 1
                seen_an[key] += 1
            # malformed args: harness complained about missing params / bogus keys
            errtxt = str(c.get("error") or c.get("error_message") or "")
            malformed = "mandatory input parameters are not present" in errtxt or (
                fn == "read_file" and c.get("error_type") == "FileReadError" and re.search(r"[`,]|start_line|end_line", errtxt))
            if malformed:
                st["malformed_calls"] += 1
                st[f"malformed_{fn}"] += 1
            for (p, a, b) in read_ranges_from_call(fn, args, c):
                gm = next((g for g in gold_files if p == g or p.endswith("/" + g)), None)
                if gm is None:
                    continue
                if a == b:
                    info["glimpse_gold_file"] = True
                    continue
                info["read_gold_file"] = True
                if is_root:
                    info["read_gold_file_root"] = True
                for q, (gs, ge) in gold_funcs[gm].items():
                    if gs is None or (not (b < gs or a > ge)):
                        info["read_gold_func"] = True
            if fn == "submit_patch":
                st["submit_calls"] += 1
                if info["first_submit_t"] is None:
                    info["first_submit_t"] = t
            if fn == "get_status":
                st["get_status_calls"] += 1
            if fn == "code_analyzer":
                st["analyzer_invocations"] += 1
            if fn == "edit_file":
                st["edit_calls"] += 1
                if malformed:
                    pass
                elif failed:
                    st["edit_notfound"] += 1
                else:
                    st["edit_ok"] += 1
                    info["edited_files"].append(norm_path(str(args.get("filepath", ""))))
                    first_mut = first_mut or t
                    info["last_mut_t"] = t
            if fn == "write_file":
                st["write_calls"] += 1
                if not failed:
                    first_mut = first_mut or t
                    info["last_mut_t"] = t
                    info["edited_files"].append(norm_path(str(args.get("filepath", ""))))
            if fn == "run_command" and is_root:
                cmd = str(args.get("command", ""))
                if re.search(r"cat\s*>\s*/tmp/\S+\.py|/tmp/\S*repro|tee\s+/tmp/\S+\.py", cmd):
                    info["repro_written"] = True
                if MUT_CMD.search(cmd) and not re.search(r"cat\s*>\s*/tmp", cmd) and not failed:
                    st["mutating_cmds"] += 1
                    first_mut = first_mut or t
                    info["last_mut_t"] = t
                if "py_compile" in cmd:
                    info["py_compile_runs"] += 1
                if re.search(r"\bpytest\b", cmd):
                    info["pytest_runs"] += 1
                    if any(tf.split("/")[-1].replace(".py", "") in cmd for tf in tp_files):
                        info["pytest_hidden_file_run"] = True
                    if first_mut is not None:
                        info["pytest_runs_post"] += 1
                        out = str(c.get("stdout", "")) + str((c.get("details") or {}).get("stdout", "")) + str(c.get("error_message", ""))
                        mres = re.findall(r"(\d+) (passed|failed|error)", out)
                        res = "pass" if (not failed and re.search(r"passed", out) and not re.search(r"\d+ (failed|error)", out)) else ("fail" if (failed or re.search(r"\d+ (failed|error)", out)) else "unknown")
                        if "no tests ran" in out or "ERROR: file or directory not found" in out:
                            res = "notests"
                        info["last_pytest_post"] = res
                elif PY_RUN.search(cmd) and "py_compile" not in cmd and "cat >" not in cmd.split("python")[0][-40:]:
                    out = str(c.get("stdout", "")) + str((c.get("details") or {}).get("stdout", "")) + str(c.get("error_message", ""))
                    bad = failed or bool(re.search(r"Traceback|AssertionError|Error:|FAIL|BUG", out))
                    if first_mut is None:
                        info["repro_runs_pre"] += 1
                        if bad or FAIL_OUT.search(out):
                            info["repro_pre_failed"] = True
                    else:
                        info["repro_runs_post"] += 1
                        info["repro_post_clean"] = not bad
    info["identical_max"] = max(seen.values()) if seen else 0
    info["first_edit_t"] = first_mut
    if info["last_mut_t"] is not None:
        info["calls_after_last_mut"] = sum(1 for (t, fn, a, c) in root_calls if t > info["last_mut_t"])
        info["calls_after_last_mut_nosubmit"] = sum(1 for (t, fn, a, c) in root_calls if t > info["last_mut_t"] and fn not in ("submit_patch", "get_status"))
    return st, info


# ----------------------------------------------------------------------------- per-run analysis

def load_tasks():
    return {json.loads(l)["instance_id"]: json.loads(l) for l in open(os.path.join(ROOT, "data/derived/proxy/valid_tasks.jsonl"))}


def read_text(p):
    try:
        return open(p, errors="replace").read()
    except FileNotFoundError:
        return ""


def auto_category(r):
    """deterministic primary label (semantic refinement of 'near_miss'/'wrong_function' is done by hand)."""
    err = r["error"] or ""
    if r["infra_stall"]:
        return "infra_stall"
    if err.startswith("Failed to apply test_patch"):
        return "test_file_edited"
    if r["patch_empty"]:
        if "ContextWindowExceeded" in err:
            return "12_context_overflow"
        if "timeout" in err or "tool call budget" in err or "LLM turns" in err:
            return "11_budget_exhaustion"
        if r["malformed_calls"] >= 5 and r["edit_ok"] == 0:
            return "7_malformed_tool_calls"
        return "empty_patch"
    if r["patch_syntax_ok"] is False or r["hidden_syntax_err"] or r["agent_broke_import"]:
        return "6_syntax_import"
    if r["missing_required_symbol"]:
        return "missing_required_symbol"
    if not r["touched_gold_file"]:
        return "14_localization" if not r["read_gold_file"] else "1_wrong_diagnosis_wrong_file"
    if not r["touched_gold_func"]:
        return "3_correct_file_wrong_function"
    if r["f2p_fail"] == 0 and r["regress"] > 0:
        return "4_regression_only"
    return "near_miss_gold_func_touched"


def analyze_run(run, tasks):
    rows = []
    for trf in sorted(glob.glob(os.path.join(ROOT, "results/px", run, "*/task_results.jsonl"))):
        shard_dir = os.path.dirname(trf)
        for line in open(trf):
            r = json.loads(line)
            iid = r["instance_id"]
            task = tasks.get(iid)
            if task is None:
                continue
            repo, commit = task["repo"], task["base_commit"]
            patch = read_text(os.path.join(shard_dir, "patches", f"{iid}.patch"))
            test_out = read_text(os.path.join(shard_dir, "test_outputs", f"{iid}.log"))
            tp = os.path.join(shard_dir, "traces", f"trace_{iid}.json")
            trace = None
            if os.path.exists(tp):
                try:
                    trace = json.load(open(tp))
                except Exception:
                    trace = None
            gdiff = parse_diff(task["patch"])
            gold_src = {p: i for p, i in gdiff.items() if not is_test_path(p) and not is_doc_path(p)} or gdiff
            gold_funcs = funcs_for_diff(repo, commit, gold_src)
            adiff = parse_diff(patch)
            agent_funcs = funcs_for_diff(repo, commit, adiff)
            st, info = trace_signals(trace, task, gold_funcs)
            src_files = {p for p in adiff if not is_test_path(p) and not is_doc_path(p) and not (adiff[p]["new"] and is_scratch_new(p))}
            touched_gold_file = bool(set(adiff) & set(gold_src))
            gf_pairs = {(p, q) for p, fs in gold_funcs.items() for q in fs}
            af_pairs = {(p, q) for p, fs in agent_funcs.items() for q in fs}

            def func_hit(gp, gq, ap, aq):
                if gp != ap:
                    return False
                # same def, or a def nested inside the gold def
                return gq == aq or aq.startswith(gq + ".")
            touched_gold_func = any(func_hit(gp, gq, ap, aq) for gp, gq in gf_pairs for ap, aq in af_pairs)
            # gold function partially covered (some gold funcs touched, some not)
            gold_funcs_hit = sum(1 for gp, gq in gf_pairs if any(func_hit(gp, gq, ap, aq) for ap, aq in af_pairs))
            syn_ok, syn_msg = compile_check(repo, commit, patch, adiff) if patch.strip() else (None, "")
            hid = split_hidden(iid, test_out)
            dur = r.get("duration_seconds") or 0.0
            row = dict(
                run=run, shard=os.path.basename(shard_dir), instance_id=iid, repo=repo, resolved=bool(r["resolved"]),
                error=(r.get("error") or "")[:90].replace("\n", " ") or None, test_exit_code=r.get("test_exit_code"),
                duration_s=round(dur, 1), tool_calls=r.get("tool_calls"), llm_calls=r.get("total_llm_calls"),
                gold_files=sorted(gold_src), gold_funcs=sorted(f"{p}::{q}" for p, q in gf_pairs),
                gold_size=sum(i["added"] + i["removed"] for i in gold_src.values()), gold_n_files=len(gold_src),
                patch_files=sorted(adiff), patch_funcs=sorted(f"{p}::{q}" for p, q in af_pairs)[:12],
                patch_size=r.get("agent_patch_size") or 0, patch_empty=not patch.strip(),
                patch_lines=sum(i["added"] + i["removed"] for i in adiff.values()),
                patch_touches_tests=sorted(p for p in adiff if is_test_path(p)),
                patch_scratch_files=sorted(p for p in adiff if adiff[p]["new"] and is_scratch_new(p)),
                patch_touches_docs=sorted(p for p in adiff if is_doc_path(p)),
                patch_extra_src_files=sorted(src_files - set(gold_src)),
                patch_syntax_ok=syn_ok, patch_syntax_msg=syn_msg,
                touched_gold_file=touched_gold_file, touched_gold_func=touched_gold_func,
                gold_funcs_hit=gold_funcs_hit, gold_funcs_n=len(gf_pairs),
                read_gold_file=info["read_gold_file"], read_gold_file_root=info["read_gold_file_root"],
                read_gold_func=info["read_gold_func"], glimpse_gold_file=info["glimpse_gold_file"],
                analyzer_invocations=st["analyzer_invocations"], analyzer_answers=st["analyzer_answers"],
                analyzer_loc=info["analyzer_loc"], analyzer_loc_gold_file=info["analyzer_loc_gold_file"],
                analyzer_loc_gold_func=info["analyzer_loc_gold_func"], analyzer_conf=info["analyzer_conf"],
                root_calls=st["root_calls"], analyzer_calls=st["analyzer_calls"],
                edit_calls=st["edit_calls"], edit_ok=st["edit_ok"], edit_notfound=st["edit_notfound"],
                malformed_calls=st["malformed_calls"], malformed_edit=st["malformed_edit_file"], malformed_read=st["malformed_read_file"],
                write_calls=st["write_calls"], mutating_cmds=st["mutating_cmds"],
                repeat_identical_root=st["repeat_identical_root"], repeat_identical_analyzer=st["repeat_identical_analyzer"],
                identical_max=info["identical_max"], submit_calls=st["submit_calls"], get_status_calls=st["get_status_calls"],
                budget_exceeded_calls=st["budget_exceeded_calls"], nudges=st["nudges"], thinking_steps=st["thinking_steps"],
                repro_written=info["repro_written"], repro_runs_pre=info["repro_runs_pre"], repro_pre_failed=info["repro_pre_failed"],
                repro_runs_post=info["repro_runs_post"], repro_post_clean=info["repro_post_clean"],
                pytest_runs=info["pytest_runs"], pytest_runs_post=info["pytest_runs_post"], last_pytest_post=info["last_pytest_post"],
                pytest_hidden_file_run=info["pytest_hidden_file_run"], py_compile_runs=info["py_compile_runs"],
                first_mut_s=None if info["first_edit_t"] is None else round(info["first_edit_t"], 1),
                last_mut_s=None if info["last_mut_t"] is None else round(info["last_mut_t"], 1),
                first_submit_s=None if info["first_submit_t"] is None else round(info["first_submit_t"], 1),
                time_after_last_mut_s=None if info["last_mut_t"] is None else round(max(dur, info["end_t"]) - info["last_mut_t"], 1),
                calls_after_last_mut=info.get("calls_after_last_mut"), calls_after_last_mut_nosubmit=info.get("calls_after_last_mut_nosubmit"),
                **hid,
            )
            tail_gap = (dur - info["end_t"]) if trace else dur
            row["max_gap_s"] = int(max(st["max_gap_s"], tail_gap))
            row["infra_stall"] = (not r["resolved"]) and ("timeout" in (r.get("error") or "")) and (st["agent_steps"] == 0 or row["max_gap_s"] > 900)
            row["context_overflow"] = "ContextWindowExceeded" in (row["error"] or "")
            row["budget_error"] = ("timeout" if "timeout" in (row["error"] or "") else "tool_budget" if "tool call budget" in (row["error"] or "")
                                   else "llm_turns" if "LLM turns" in (row["error"] or "") else "context" if row["context_overflow"] else None)
            row["agent_confident"] = (row["last_pytest_post"] == "pass") or (row["repro_post_clean"] is True)
            row["false_confidence"] = (not row["resolved"]) and not row["patch_empty"] and row["agent_confident"]
            row["near_miss"] = (not row["resolved"]) and row["touched_gold_func"] and row["patch_syntax_ok"] is not False and not row["hidden_syntax_err"] and not row["agent_broke_import"] and not row["patch_touches_tests"]
            if not row["resolved"]:
                row["auto_primary"] = auto_category(row)
                sec = []
                if row["malformed_calls"] >= 3: sec.append("7")
                if row["repeat_identical_root"] >= 5 or row["submit_calls"] >= 10: sec.append("10")
                if row["budget_error"] in ("timeout", "tool_budget", "llm_turns"): sec.append("11")
                if row["context_overflow"]: sec.append("12")
                if not row["repro_runs_pre"] or not row["repro_pre_failed"]: sec.append("8")
                if row["pytest_runs_post"] == 0 or row["false_confidence"]: sec.append("9")
                row["auto_secondary"] = sec
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["px_c9e_s1", "px_c9e_s2"])
    ap.add_argument("--name", default="c9e")
    ap.add_argument("--outdir", default="results/failure_analysis")
    ap.add_argument("--labels", default="results/failure_analysis/manual_labels_sample61.jsonl",
                    help="manual semantic labels (one JSON per sampled run, id=<run>__<iid>); merged if present")
    a = ap.parse_args()
    tasks = load_tasks()
    rows = []
    for run in a.runs:
        rows += analyze_run(run, tasks)
    AUTO2CODE = {"infra_stall": "infra", "12_context_overflow": "12", "11_budget_exhaustion": "11", "empty_patch": "empty_patch",
                 "6_syntax_import": "6", "7_malformed_tool_calls": "7", "3_correct_file_wrong_function": "3",
                 "1_wrong_diagnosis_wrong_file": "1", "14_localization": "14", "4_regression_only": "4",
                 "missing_required_symbol": "13?", "test_file_edited": "infra(test_file_edited)", "near_miss_gold_func_touched": "4/5?"}
    labels = {}
    lp = os.path.join(ROOT, a.labels)
    if os.path.exists(lp):
        for line in open(lp):
            if line.strip():
                d = json.loads(line)
                labels[d["id"].replace(".txt", "")] = d
    for r in rows:
        if r["resolved"]:
            continue
        d = labels.get(f"{r['run']}__{r['instance_id']}")
        r["manual_sampled"] = d is not None
        for k in ("primary", "secondary", "fixable_by", "understood_issue", "found_gold_file", "identified_gold_function",
                  "expected_behaviour_correct", "repro", "verification", "interpreted_results_correctly", "hidden_req_note", "evidence"):
            r[f"manual_{k}"] = (d or {}).get(k)
        auto = AUTO2CODE.get(r["auto_primary"], r["auto_primary"])
        # a serving stall (>15 min without any step, then session timeout) is decisive regardless of earlier behaviour
        r["primary_final"] = "infra" if r["infra_stall"] else (str(d["primary"]) if d else auto)
        r["primary_source"] = "deterministic(infra_stall)" if r["infra_stall"] else ("manual" if d else "auto")
    od = os.path.join(ROOT, a.outdir)
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, f"{a.name}_all.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    fails = [r for r in rows if not r["resolved"]]
    with open(os.path.join(od, f"{a.name}_failures.jsonl"), "w") as f:
        for r in fails:
            f.write(json.dumps(r) + "\n")
    print(f"{a.name}: {len(rows)} runs, {len(fails)} failures -> {od}")
    print(Counter(r["auto_primary"] for r in fails).most_common())


if __name__ == "__main__":
    main()
