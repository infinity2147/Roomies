#!/usr/bin/env python3
"""Where does the wall time go? L4 time budget of the Gemma-4-31B SWE agent (C9e family vs thinking variants).

Two data sources, both read-only:

1. Kaggle L4 serial captures (exact scorer hardware, CONCURRENCY=1): results/kaggle/<run>/results/<run>/capture.jsonl.
   Every chat request/response with t (request start), dt (latency) and usage. Tasks are segmented like
   scripts/kaggle_eval/capture_task_times.py (root task prompt). We fit a per-run latency model
       dt = a + b * new_prompt_tokens + c * completion_tokens + d * completion_tokens * prompt_tokens
   (new_prompt_tokens = tokens not covered by vLLM's prefix cache, estimated per conversation) and split each
   call's measured dt into overhead / prefill / decode in proportion to the model terms. Gaps between a response
   and the next request inside a task = tool execution + harness; the gap after a task's last call = verification
   of that task + sandbox setup of the next one.

2. Traces (full trajectories): Kaggle traces (L4, same runs as the captures), results/px/time_c9e (A40 serial),
   and proxy runs results/px/px_<cand>_s*/s*/ (concurrent workers; wall time inflated, so we never use their
   wall clock for LLM time). Each LLM call is re-costed with the L4 latency model of the matching family, tool time
   is taken from the trace (obs timestamp - call timestamp), and a per-task L4 setup+verify constant is added.
   Waste metrics (budget-exhaustion loops, identical repeats, rejected calls, analyzer, observation size, time after
   the final patch content was in place, post-verification tail, early-abandon rules) are expressed in L4 seconds.

Usage:  .venv/bin/python src/analysis/time_budget.py [--out reports/time_budget] [--quick]   (~1 min, CPU only)
Writes  <out>/tables.md (every table quoted in reports/time_budget_20261011.md), <out>/capture_tasks.jsonl (one row
per L4 task), <out>/trace_tasks.jsonl (one row per trace task), <out>/summary.json (latency models, interventions).

Caveats: "final patch content in place" = earliest root edit after which every non-trivial '+' line of the final
patch has appeared in some edit text (edit_file new_string / write_file content / mutating shell command); deletions
are not checked. Proxy tool times come from concurrent workers (slightly inflated). Traces contain no compaction
calls, so a per-root-call compaction cost measured on the matching L4 capture is added.
"""
import argparse
import glob
import json
import math
import os
import re
import statistics as st
from collections import Counter, defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = lambda *p: os.path.join(ROOT, *p)  # noqa: E731

KAGGLE = {  # run -> (family, has analyzer, thinking)
    "c9ae-t30s": ("c9ae", True, False),
    "c11t-t30s": ("c11t", True, True),
    "c11n-t30s": ("c11n", False, True),
    "c15t512-t30s": ("c15t512", True, True),
}
# trace sets: name -> (glob of run dirs, latency-model run)
TRACE_SETS = {
    "c9e_A40serial": (["results/px/time_c9e/l4_t30_ids"], "c9ae-t30s"),
    "c9e_px": (["results/px/px_c9e_s%d/s*" % i for i in range(1, 6)], "c9ae-t30s"),
    "c15n512_px": (["results/px/px_c15n512_s%d/s*" % i for i in range(1, 4)], "c15t512-t30s"),
    "c8_px": (["results/px/px_c8_s%d/s*" % i for i in range(1, 5)], "c9ae-t30s"),
    "c23_px": (["results/px/px_c23_s%d/s*" % i for i in range(1, 3)], "c9ae-t30s"),
    "c9ae_L4": ([], "c9ae-t30s"),  # capture only (no traces)
    "c11n_L4": (["results/kaggle/c11n-t30s/results/c11n-t30s"], "c11n-t30s"),
    "c15t512_L4": (["results/kaggle/c15t512-t30s/results/c15t512-t30s"], "c15t512-t30s"),
    "c11t_L4": (["results/kaggle/c11t-t30s/results/c11t-t30s"], "c11t-t30s"),
}
NO_COUNT = {"get_status", "submit_patch"}  # not charged to the 100-call budget
OBS_CAPS = (2000, 1000)
CPT = 3.7  # chars per token of tool output / history text (calibrated on c9ae + c11n captures, see summary.json)
TIME_CAPS_MIN = (4, 5, 6, 8, 10)
NOEDIT_K = (30, 40, 50, 60)
MUT_CMD = re.compile(r"sed\s+-i|perl\s+-p?i|>\s*(?!/tmp|/dev)[\w./-]+\.py\b|tee\s+(?!/tmp)[\w./-]+\.py|"
                     r"git\s+(checkout|restore|apply|stash)|\bpatch\s+-p|\.write_text\(|open\([^)]*['\"]w['\"]")
PY_RUN = re.compile(r"(^|[;&|\s])python3?\s+(?!-m\s+(pytest|py_compile|pip))(-c\s|/tmp/|[\w./-]+\.py)")


def cstr(c):
    return c if isinstance(c, str) else json.dumps(c)


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def stats(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return dict(n=0, mean=float("nan"), median=float("nan"), p90=float("nan"), sum=0.0)
    return dict(n=len(xs), mean=st.mean(xs), median=st.median(xs), p90=pct(xs, 0.9), sum=sum(xs))


# ============================================================================ L4 captures

def load_capture(run):
    path = next(iter(glob.glob(R("results/kaggle", run, "results", "*", "capture.jsonl"))))
    recs = []
    for line in open(path):
        r = json.loads(line)
        req, resp = r["request"], r.get("response") or {}
        ms = req.get("messages", [])
        c0 = cstr(ms[0].get("content")) if ms else ""
        if ms and ms[0]["role"] == "system" and c0.startswith("You are an autonomous"):
            kind = "root"
        elif ms and ms[0]["role"] == "system" and "code_analyzer" in c0[:60]:
            kind = "analyzer"
        elif c0.startswith("The following is a conversation history"):
            kind = "compact"
        else:
            kind = "other"
        task_key = repo = cap_min = None
        if kind == "root":
            for m in ms:
                c = cstr(m.get("content"))
                if m.get("role") == "user" and c.startswith("You are evaluating a software engineering task"):
                    task_key = c.split("## Task Budget")[0]
                    mm = re.search(r"for repository (\S+?)\.?\n", c)
                    repo = mm.group(1) if mm else None
                    mt = re.search(r"Time allowance: ([\d.]+) minutes", c)
                    cap_min = float(mt.group(1)) if mt else None
                    break
        u = resp.get("usage") or {}
        msg = ((resp.get("choices") or [{}])[0].get("message")) or {}
        tcs = msg.get("tool_calls") or []
        last = ms[-1] if ms else {}
        last_c = cstr(last.get("content")) if last.get("role") == "tool" else ""
        recs.append(dict(
            t=r["t"], dt=r["dt"], kind=kind, task_key=task_key, repo=repo, cap_min=cap_min,
            pt=u.get("prompt_tokens") or 0, ct=u.get("completion_tokens") or 0,
            msg_h=[hash(json.dumps(m, sort_keys=True)) for m in ms],
            msg_chars=[len(cstr(m.get("content"))) + len(json.dumps(m.get("tool_calls") or "")) + len(m.get("reasoning_content") or "") for m in ms],
            reasoning_chars=len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
            content_chars=len(msg.get("content") or ""),
            tc_chars=sum(len(tc["function"].get("arguments") or "") + len(tc["function"]["name"]) for tc in tcs),
            tools=[(tc["function"]["name"], tc["function"].get("arguments") or "") for tc in tcs],
            finish=((resp.get("choices") or [{}])[0].get("finish_reason")),
            budget_in="budget exhausted" in last_c, last_tool_chars=len(last_c),
            rejected_in=bool(re.search(r"mandatory input parameters are not present|old_string not found|"
                                       r"Source path \S*`|cannot be greater than end_line", last_c[:600])),
            status=r.get("status")))
    recs.sort(key=lambda x: x["t"])
    return recs


def segment(recs):
    """assign task index (serial run) and new-prompt-token estimates."""
    order, cur = {}, -1
    for r in recs:
        if r["kind"] == "root" and r["task_key"] is not None and r["task_key"] not in order:
            order[r["task_key"]] = len(order)
        if r["kind"] == "root" and r["task_key"] in order:
            cur = order[r["task_key"]]
        r["task"] = max(cur, 0)
    prev = {}
    for r in recs:
        conv = (r["task"], r["kind"])
        p = prev.get(conv)
        common = 0
        if p is not None:
            for a, b in zip(p["msg_h"], r["msg_h"]):
                if a != b:
                    break
                common += 1
        if p is not None and common == len(p["msg_h"]) and r["pt"] >= p["pt"]:
            r["new"] = r["pt"] - p["pt"]
            r["app_chars"] = sum(r["msg_chars"][common - 1:]) if common else 0  # prev assistant? (approx)
            r["app_chars"] = sum(r["msg_chars"][len(p["msg_h"]):])
            r["full_prefix"] = True
        else:
            tot = sum(r["msg_chars"]) or 1
            r["new"] = int(r["pt"] * (1 - sum(r["msg_chars"][:common]) / tot))
            r["full_prefix"] = False
        prev[conv] = r
    return len(order)


class LatModel:
    """dt = a + b*new + c*ct + d*ct*pt  (seconds; tokens)"""

    def __init__(self, coef, r2, n):
        self.a, self.b, self.c, self.d = coef
        self.r2, self.n = r2, n

    @classmethod
    def fit(cls, recs):
        X = np.array([[1.0, r["new"], r["ct"], r["ct"] * r["pt"]] for r in recs if r["ct"] > 0 and r["status"] == 200])
        y = np.array([r["dt"] for r in recs if r["ct"] > 0 and r["status"] == 200])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        coef = np.maximum(coef, 0)  # physical terms are non-negative
        pred = X @ coef
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        return cls(coef.tolist(), float(r2), len(y))

    def parts(self, new, ct, pt):
        return self.a, self.b * new, self.c * ct + self.d * ct * pt

    def __call__(self, new, ct, pt):
        return sum(self.parts(new, ct, pt))

    def desc(self):
        return (f"a={self.a:.3f}s/call, prefill={1 / self.b if self.b else float('inf'):.0f} tok/s, "
                f"decode={1 / (self.c + self.d * 4000):.1f} tok/s @4k ctx, {1 / (self.c + self.d * 16000):.1f} tok/s @16k, "
                f"R2={self.r2:.3f} (n={self.n})")


def capture_tasks(run, recs, ntask, model):
    fam, has_an, thinking = KAGGLE[run]
    tr_path = glob.glob(R("results/kaggle", run, "results", "*", "task_results.jsonl"))
    trs = sorted((json.loads(l) for l in open(tr_path[0])), key=lambda r: r["task_index"]) if tr_path else []
    by = defaultdict(list)
    for r in recs:
        by[r["task"]].append(r)
    starts = [by[i][0]["t"] for i in range(ntask)]
    last_end = max(r["t"] + r["dt"] for r in recs)
    out = []
    for i in range(ntask):
        rs = by[i]
        span_end = starts[i + 1] if i + 1 < ntask else last_end
        d = Counter()
        d["span_s"] = span_end - starts[i]
        seen = defaultdict(Counter)
        budget_t = None
        last_root_submit = False
        for j, r in enumerate(rs):
            a, p, dc = model.parts(r["new"], r["ct"], r["pt"])
            s = r["dt"] / max(a + p + dc, 1e-6)
            k = r["kind"]
            d[f"llm_{k}_s"] += r["dt"]
            d["llm_s"] += r["dt"]
            d["overhead_s"] += a * s
            d["prefill_s"] += p * s
            d["decode_s"] += dc * s
            d[f"calls_{k}"] += 1
            d["calls"] += 1
            d["ct"] += r["ct"]
            d["pt"] += r["pt"]
            d["new"] += r["new"]
            tot_c = r["reasoning_chars"] + r["content_chars"] + r["tc_chars"]
            if tot_c:
                rt = r["ct"] * r["reasoning_chars"] / tot_c
                nt = r["ct"] * r["content_chars"] / tot_c if r["tools"] else 0.0
                d["reason_tok"] += rt
                d["narr_tok"] += nt
                d["reason_decode_s"] += dc * s * rt / max(r["ct"], 1)
                d["narr_decode_s"] += dc * s * nt / max(r["ct"], 1)
            if r["kind"] in ("root", "analyzer"):
                for (fn, args) in r["tools"]:
                    key = fn + args
                    if fn not in NO_COUNT and seen[k][key] and budget_t is None and not r["budget_in"]:
                        d["repeat_calls"] += 1
                        d["repeat_s"] += r["dt"] / len(r["tools"])
                    seen[k][key] += 1
            nxt = next((x for x in rs[j + 1:] if x["kind"] == r["kind"]), None)
            if nxt is not None and nxt["rejected_in"] and budget_t is None:
                d["rejected_calls"] += 1
                d["rejected_s"] += r["dt"]
            if r["kind"] != "compact" and r["reasoning_chars"]:
                tot_c2 = r["reasoning_chars"] + r["content_chars"] + r["tc_chars"]
                rt2 = r["ct"] * r["reasoning_chars"] / tot_c2
                d["reason_calls"] += 1
                d["reason_gt512_tok"] += max(0.0, rt2 - 512)
            if r["kind"] == "root" and r["tools"] and all(fn == "submit_patch" for fn, _ in r["tools"]):
                if last_root_submit:
                    d["submit_repeat_calls"] += 1
                    d["submit_repeat_s"] += r["dt"]
                last_root_submit = True
            elif r["kind"] == "root":
                last_root_submit = False
            if r["budget_in"] and budget_t is None:
                budget_t = r["t"]
            if budget_t is not None:
                d["post_budget_calls"] += 1
            if j + 1 < len(rs):
                d["tool_gap_s"] += max(0.0, rs[j + 1]["t"] - (r["t"] + r["dt"]))
        d["between_s"] = max(0.0, span_end - (rs[-1]["t"] + rs[-1]["dt"])) if i + 1 < ntask else 0.0
        d["post_budget_s"] = (span_end - budget_t) if budget_t else 0.0
        row = dict(run=run, task=i, repo=rs[0]["repo"], cap_min=rs[0]["cap_min"], **d)
        if trs:
            tr = trs[i]
            assert rs[0]["repo"] is None or tr["repo"] == rs[0]["repo"], (run, i, tr["repo"], rs[0]["repo"])
            row.update(iid=tr["instance_id"], resolved=bool(tr["resolved"]), harness_dur_s=tr["duration_seconds"],
                       tool_calls=tr["tool_calls"], llm_calls=tr["total_llm_calls"])
        out.append(row)
    return out


def output_categories(recs, model):
    """completion tokens / decode seconds by what the call emitted (per task means), plus ct-per-call quantiles."""
    ntask = len({r["task"] for r in recs})
    cat_tok, cat_s, cat_n = Counter(), Counter(), Counter()
    per_call = defaultdict(list)
    for r in recs:
        a, p, dc = model.parts(r["new"], r["ct"], r["pt"])
        sc = r["dt"] / max(a + p + dc, 1e-6)
        dec = dc * sc
        tot = r["reasoning_chars"] + r["content_chars"] + r["tc_chars"] or 1
        rtok = r["ct"] * r["reasoning_chars"] / tot
        if r["kind"] == "compact":
            cat = "compaction summary"
        elif not r["tools"]:
            cat = f"{r['kind']} text-only (final answer / summary)"
        else:
            fn, args = r["tools"][0]
            if fn in ("edit_file", "write_file"):
                cat = f"{r['kind']} edit_file/write_file"
            elif fn == "run_command" and ("<<" in args or len(args) > 400):
                cat = f"{r['kind']} run_command script/heredoc"
            elif fn == "code_analyzer":
                cat = "root code_analyzer request"
            else:
                cat = f"{r['kind']} short tool call ({'read/grep/cmd' if fn in ('run_command', 'read_file') else 'other'})"
        per_call[r["kind"]].append(r["ct"])
        cat_n[cat] += 1
        cat_tok[cat] += r["ct"] - rtok
        cat_s[cat] += dec * (r["ct"] - rtok) / max(r["ct"], 1)
        if rtok:
            cat_tok["(reasoning, all calls)"] += rtok
            cat_s["(reasoning, all calls)"] += dec * rtok / max(r["ct"], 1)
            cat_n["(reasoning, all calls)"] += 1
        if r["content_chars"] and r["tools"]:
            nt = r["ct"] * r["content_chars"] / tot
            cat_tok["(narration text next to a tool call)"] += nt
            cat_s["(narration text next to a tool call)"] += dec * nt / max(r["ct"], 1)
            cat_n["(narration text next to a tool call)"] += 1
    q = {k: dict(n=len(v), mean=st.mean(v), p50=pct(v, .5), p90=pct(v, .9), p99=pct(v, .99)) for k, v in per_call.items()}
    cats = {k: dict(calls_per_task=cat_n[k] / ntask, tok_per_task=cat_tok[k] / ntask, decode_s_per_task=cat_s[k] / ntask)
            for k in cat_n}
    return dict(ct_per_call=q, categories=cats)


def calib_chars_per_token(recs):
    dc = dp = 0
    for r in recs:
        if r.get("full_prefix") and r["kind"] == "root" and r["new"] > 0 and r.get("app_chars"):
            dc += r["app_chars"]
            dp += r["new"]
    return dc / dp if dp else 3.5


# ============================================================================ traces

def parse_trace(t):
    """-> list of LLM calls sorted by time: dict(author, ts, pt, ct, msg_chars, think, tools=[...])"""
    calls = {}

    def get(author, ts):
        key = (author, round(ts or 0.0, 3))
        if key not in calls:
            calls[key] = dict(author=author, ts=ts or 0.0, pt=None, ct=None, msg_chars=0, think=False, tools=[],
                              text=None)
        return calls[key]

    pending_an = []  # root code_analyzer tools awaiting their result
    for s in t.get("steps", []):
        ex = s.get("extra") or {}
        if s.get("source") != "agent":
            o = s.get("observation")
            if o and (o.get("extra") or {}).get("tool_name") == "code_analyzer" and pending_an:
                tl = pending_an.pop(0)
                tl["obs"] = o.get("content") or ""
                tl["obs_ts"] = (o.get("extra") or {}).get("timestamp")
            continue
        tcs = s.get("tool_calls") or []
        obs = s.get("observation")
        for i, tc in enumerate(tcs):
            tex = tc.get("extra") or {}
            c = get(tex.get("author") or ex.get("author"), tex.get("timestamp") or ex.get("timestamp"))
            u = tex.get("usage")
            if u:
                c["pt"], c["ct"] = u.get("prompt_tokens"), u.get("completion_tokens")
            tool = dict(fn=tc.get("function_name"), args=tc.get("arguments") or {}, obs=None, obs_ts=None)
            if i == len(tcs) - 1 and obs is not None and tool["fn"] != "code_analyzer":
                tool["obs"] = obs.get("content") or ""
                tool["obs_ts"] = (obs.get("extra") or {}).get("timestamp")
            if tool["fn"] == "code_analyzer":
                pending_an.append(tool)
            c["tools"].append(tool)
        if s.get("metrics") or not tcs:
            c = get(ex.get("author"), ex.get("timestamp"))
            m = s.get("metrics") or {}
            if c["pt"] is None and m:
                c["pt"], c["ct"] = m.get("prompt_tokens"), m.get("completion_tokens")
            if s.get("message"):
                c["msg_chars"] = len(s["message"])
                c["think"] = ex.get("event_type") == "thinking"
                if not tcs:
                    c["text"] = s["message"]
        # a single tool_call step whose step-extra author/ts differ from the tc extra: message belongs to tc call
        if tcs and s.get("message") and not s.get("metrics"):
            tex = tcs[-1].get("extra") or {}
            c = get(tex.get("author") or ex.get("author"), tex.get("timestamp") or ex.get("timestamp"))
            c["msg_chars"] = len(s["message"])
            c["think"] = ex.get("event_type") == "thinking"
    out = sorted(calls.values(), key=lambda c: c["ts"])
    return [c for c in out if c["pt"] is not None and c["author"] is not None]


def obs_info(o):
    if o is None:
        return {}
    try:
        c = json.loads(o)
        return c if isinstance(c, dict) else {"_raw": c}
    except Exception:
        return {"_raw": o}


def err_class(fn, c):
    if not c or c.get("status") != "error":
        if isinstance(c, dict) and "error" in c and "status" not in c:
            return "adk_malformed" if "mandatory input parameters" in str(c.get("error")) else "adk_error"
        return None
    et = c.get("error_type") or ""
    msg = str(c.get("error_message") or "")
    if et == "BudgetExceeded":
        return "budget"
    if et == "TimeoutExceeded":
        return "timeout"
    if et == "FileEditError":
        return "edit_fail"
    if et in ("FileReadError", "FileWriteError", "ValueError"):
        return "bad_args" if re.search(r"[`,]|start_line|end_line|traversal|cannot be greater", msg) else "file_error"
    if et == "CommandError":
        return "cmd_nonzero"
    return "other_error"


def patch_plus_lines(text):
    out = set()
    files = set()
    for ln in (text or "").splitlines():
        if ln.startswith("+++ "):
            p = ln[4:].strip()
            files.add(p[2:] if p.startswith("b/") else p)
        elif ln.startswith("+") and not ln.startswith("+++"):
            s = ln[1:].strip()
            if len(s) >= 6 and re.search(r"[A-Za-z0-9]", s):
                out.add(s)
    return out, files


def is_test_path(p):
    return bool(re.search(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|conftest\.py$", p))


def analyze_task(tr, trace, patch, model, tool_scale, setup_s, cpt, compact_rate=0.0):
    calls = parse_trace(trace) if trace else []
    res = dict(iid=tr["instance_id"], repo=tr["repo"], resolved=bool(tr["resolved"]), patch_size=tr["agent_patch_size"],
               h_tool_calls=tr["tool_calls"], h_llm_calls=tr["total_llm_calls"], dur_s=tr["duration_seconds"],
               error=(tr.get("error") or "")[:80])
    if not calls:
        res["no_trace"] = True
        return res
    plus, pfiles = patch_plus_lines(patch)
    pfiles_src = {p for p in pfiles if not is_test_path(p)}
    plus_need = {l for l in plus}
    prev_pt = {}
    t_l4 = 0.0
    cum = []  # cumulative L4 time at end of each call (incl. tool time)
    tool_counted = 0
    budget_idx = None
    seen = defaultdict(dict)
    epoch = 0
    last_submit_epoch = None
    covered_text = []
    first_mut_idx = cover_idx = last_mut_idx = None
    verify_after_cover_idx = None
    root_tool_n = 0
    first_mut_root_n = None
    an_inv = 0
    an_calls_inv = Counter()
    an_loc_files = []
    excess = {cap: defaultdict(float) for cap in OBS_CAPS}
    cap_save = Counter()
    d = Counter()
    obs_sizes = []
    per_call = []
    for i, c in enumerate(calls):
        a = c["author"] or "?"
        conv = "root" if a == "swe_coder" else "analyzer"
        pt, ct = c["pt"] or 0, c["ct"] or 0
        pp = prev_pt.get(conv)
        if pp is not None and pt >= pp:
            new = pt - pp
        else:
            new = pt
            for cap in OBS_CAPS:
                excess[cap][conv] = 0.0
        prev_pt[conv] = pt
        llm = model(new, ct, pt)
        ov, pre, dec = model.parts(new, ct, pt)
        for cap in OBS_CAPS:
            ex = excess[cap][conv]
            pt2 = max(0.0, pt - ex)
            # newly-appended excess since last call is part of `new`
            cap_save[cap] += llm - model(max(0.0, new - c.get("_new_excess_%d" % cap, 0.0)), ct, pt2)
        # tool time
        ttool = 0.0
        if c["tools"]:
            obs_ts = [tl["obs_ts"] for tl in c["tools"] if tl.get("obs_ts")]
            if obs_ts:
                ttool = max(0.0, max(obs_ts) - c["ts"]) * tool_scale
                if any(tl["fn"] == "code_analyzer" for tl in c["tools"]):
                    ttool = 0.0  # analyzer runtime is accounted by its own LLM calls + tools
        ttool = min(ttool, 330.0)
        step = llm + ttool
        t_l4 += step
        cum.append(t_l4)
        d[f"llm_{conv}_s"] += llm
        d["llm_s"] += llm
        d["prefill_s"] += pre
        d["decode_s"] += dec
        d["overhead_s"] += ov
        d["tool_s"] += ttool
        d[f"calls_{conv}"] += 1
        d["calls"] += 1
        d["ct"] += ct
        d["pt"] += pt
        tot_c = c["msg_chars"] + sum(len(json.dumps(tl["args"])) for tl in c["tools"])
        if c["think"] and tot_c:
            d["reason_tok"] += ct * c["msg_chars"] / tot_c
            d["reason_s"] += dec * c["msg_chars"] / tot_c
        elif c["tools"] and c["msg_chars"] and tot_c:
            d["narr_tok"] += ct * c["msg_chars"] / tot_c
            d["narr_s"] += dec * c["msg_chars"] / tot_c
            d["narr_calls"] += 1
        if not c["tools"]:
            d["textonly_calls"] += 1
            d["textonly_s"] += llm
            if conv == "analyzer" and c.get("text"):
                m = re.search(r"LOCATION:\s*`?([\w./-]+\.\w+)", c["text"])
                if m:
                    an_loc_files.append(m.group(1).lstrip("./"))
        flags = set()
        if budget_idx is not None:
            flags.add("post_budget")
        for tl in c["tools"]:
            fn, args = tl["fn"], tl["args"]
            o = obs_info(tl.get("obs"))
            ec = err_class(fn, o)
            osz = len(tl.get("obs") or "")
            if fn != "code_analyzer" and tl.get("obs") is not None:
                obs_sizes.append(osz)
                d["obs_chars"] += osz
                for cap in OBS_CAPS:
                    e = max(0, osz - cap) / cpt
                    excess[cap][conv] += e
                    if i + 1 < len(calls):
                        calls[i + 1]["_new_excess_%d" % cap] = calls[i + 1].get("_new_excess_%d" % cap, 0.0) + e
                if osz > 4000:
                    d["obs_gt4k"] += 1
            if fn == "code_analyzer":
                an_inv += 1
                m = re.search(r"LOCATION:\s*`?([\w./-]+\.\w+)", tl.get("obs") or "")
                if m:
                    an_loc_files.append(m.group(1).lstrip("./"))
            if conv == "analyzer":
                an_calls_inv[an_inv] += 1
            if fn not in NO_COUNT and fn != "code_analyzer":
                tool_counted += 1
            if ec == "budget" and budget_idx is None:
                budget_idx = i
                d["budget_hit_tool_n"] = tool_counted
                flags.add("post_budget")
            if ec and ec != "budget":
                d[f"err_{ec}"] += 1
                flags.add("err_" + ec)
            if budget_idx is None and fn not in NO_COUNT:
                # identical call with no state change (edit / file write / redirect) since its previous occurrence
                key = fn + json.dumps(args, sort_keys=True)
                if key in seen[conv] and seen[conv][key][0] == epoch:
                    flags.add("repeat")
                    d["repeat_calls"] += 1
                    d[f"repeat_{conv}_n"] += 1
                    seen[conv][key] = (epoch, seen[conv][key][1] + 1)
                    if seen[conv][key][1] >= 3:
                        flags.add("loop")  # 3rd+ identical occurrence without any state change
                else:
                    seen[conv][key] = (epoch, 1)
            if conv == "root" and not ec and (fn in ("edit_file", "write_file") or (
                    fn == "run_command" and re.search(r">|<<|sed\s+-i|\brm\s|\bmv\s|\bcp\s|git\s+(checkout|stash|apply|reset)",
                                                      str(args.get("command", ""))))):
                epoch += 1
            if conv == "root" and fn not in NO_COUNT and fn != "code_analyzer":
                root_tool_n += 1
            # mutations / coverage (root only)
            if conv == "root":
                failed = bool(ec)
                txt = None
                if fn == "edit_file" and not failed:
                    txt = str(args.get("new_string", ""))
                elif fn == "write_file" and not failed:
                    txt = str(args.get("content", ""))
                elif fn == "run_command":
                    cmd = str(args.get("command", ""))
                    if not failed and MUT_CMD.search(cmd) and not re.search(r"cat\s*>\s*/tmp", cmd):
                        txt = cmd
                    elif not failed and re.search(r"<<\s*'?EOF", cmd) and "/tmp" not in cmd.split("<<")[0]:
                        txt = cmd
                if txt is not None:
                    flags.add("mut")
                    if first_mut_idx is None:
                        first_mut_idx = i
                        first_mut_root_n = root_tool_n
                    last_mut_idx = i
                    covered_text.append(txt)
                    if cover_idx is None and plus_need:
                        blob = "\n".join(covered_text)
                        if all(l in blob for l in plus_need):
                            cover_idx = i
                if fn == "run_command" and cover_idx is not None and i > cover_idx and verify_after_cover_idx is None:
                    cmd = str(args.get("command", ""))
                    out = str(o.get("stdout", "")) + str((o.get("details") or {}).get("stdout", "")) + str(o.get("error_message", ""))
                    if re.search(r"\bpytest\b", cmd):
                        if not ec and re.search(r"\d+ passed", out) and not re.search(r"\d+ (failed|error)", out):
                            verify_after_cover_idx = i
                    elif PY_RUN.search(cmd) and "py_compile" not in cmd:
                        if not ec and not re.search(r"Traceback|AssertionError|Error:|FAIL", out):
                            verify_after_cover_idx = i
            if fn == "submit_patch":
                d["submit_calls"] += 1
                if last_submit_epoch == epoch:
                    flags.add("submit_loop")  # re-submitting an unchanged tree (submit does not end the run)
                    d["submit_repeat_n"] += 1
                last_submit_epoch = epoch
            if fn == "get_status":
                d["get_status_calls"] += 1
        if "repeat" in flags and "post_budget" not in flags:
            d[f"repeat_{conv}_s"] += step
        for f in flags:
            if f == "repeat" and "post_budget" in flags:
                continue
            d[f + "_s"] += step
            d[f + "_n"] += 1
        if conv == "analyzer":
            if an_calls_inv[an_inv] > 21 and "post_budget" not in flags:
                d["an_excess20_s"] += step
            if an_inv > 1:
                d["an_extra_inv_s"] += step
        if conv == "analyzer" and (an_calls_inv[an_inv] > 21 or an_inv > 1):
            flags.add("an_overrun")
        per_call.append((i, conv, step, flags))
    # exclusive attribution of every call's L4 time (first matching bucket wins)
    for (i, conv, step, flags) in per_call:
        if "post_budget" in flags:
            b = "post_budget"
        elif "submit_loop" in flags:
            b = "submit_loop"
        elif flags & {"err_adk_malformed", "err_bad_args", "err_edit_fail"}:
            b = "rejected"
        elif "loop" in flags:
            b = "loop"
        elif "repeat" in flags:
            b = "repeat2"
        elif "an_overrun" in flags:
            b = "an_overrun"
        elif verify_after_cover_idx is not None and i > verify_after_cover_idx:
            b = "after_verify"
        elif cover_idx is not None and i > cover_idx:
            b = "after_cover_preverify"
        elif conv == "analyzer":
            b = "analyzer_ok"
        else:
            b = "root_ok"
        d["bk_" + b] += step
    d["compact_s"] = compact_rate * d["calls_root"]  # compaction calls are not in traces: per-root-call L4 rate
    total = t_l4 + setup_s + d["compact_s"]
    res.update(dict(d))
    res["l4_s"] = total
    res["l4_agent_s"] = t_l4
    res["setup_s"] = setup_s
    res["root_tool_n"] = root_tool_n
    res["an_invocations"] = an_inv
    res["an_calls_max_inv"] = max(an_calls_inv.values()) if an_calls_inv else 0
    res["an_loc_files"] = an_loc_files
    res["patch_files"] = sorted(pfiles)
    res["an_used"] = (any(any(p.endswith(f) or f.endswith(p) for p in pfiles_src) for f in an_loc_files)
                      if an_loc_files and pfiles_src else None)
    res["obs_n"] = len(obs_sizes)
    res["obs_p50"] = pct(obs_sizes, 0.5)
    res["obs_p90"] = pct(obs_sizes, 0.9)
    for cap in OBS_CAPS:
        res[f"cap{cap}_save_s"] = cap_save[cap]
    res["first_mut_s"] = cum[first_mut_idx] if first_mut_idx is not None else None
    res["first_mut_root_n"] = first_mut_root_n
    res["cover_s"] = cum[cover_idx] if cover_idx is not None else None
    res["cover_calls"] = cover_idx + 1 if cover_idx is not None else None
    res["last_mut_s"] = cum[last_mut_idx] if last_mut_idx is not None else None
    res["calls_total"] = len(calls)
    res["after_cover_s"] = (t_l4 - cum[cover_idx]) if cover_idx is not None else None
    res["after_cover_calls"] = (len(calls) - cover_idx - 1) if cover_idx is not None else None
    res["after_last_mut_s"] = (t_l4 - cum[last_mut_idx]) if last_mut_idx is not None else None
    res["after_verify_s"] = (t_l4 - cum[verify_after_cover_idx]) if verify_after_cover_idx is not None else None
    # after-cover time excluding the budget-loop part (to avoid double counting)
    if cover_idx is not None:
        res["after_cover_nobudget_s"] = sum(step for (i, conv, step, flags) in per_call
                                            if i > cover_idx and "post_budget" not in flags)
    if verify_after_cover_idx is not None:
        res["after_verify_nobudget_s"] = sum(step for (i, conv, step, flags) in per_call
                                             if i > verify_after_cover_idx and "post_budget" not in flags)
    # time-cap / no-edit abandon evaluation
    res["over_cap_s"] = {T: max(0.0, total - T * 60) for T in TIME_CAPS_MIN}
    noedit = {}
    # time after the K-th root counted tool call when no mutation happened before it
    rn = 0
    k_time = {}
    for (i, conv, step, flags) in per_call:
        if conv == "root":
            rn += sum(1 for tl_ in calls[i]["tools"] if tl_["fn"] not in NO_COUNT and tl_["fn"] != "code_analyzer")
            for K in NOEDIT_K:
                if K not in k_time and rn >= K:
                    k_time[K] = cum[i]
    for K in NOEDIT_K:
        if K in k_time and (first_mut_idx is None or cum[first_mut_idx] > k_time[K]):
            noedit[K] = t_l4 - k_time[K]
        else:
            noedit[K] = None
    res["noedit_abandon_save_s"] = noedit
    return res


def load_trace_set(name, dirs):
    rows = []
    for pat in dirs:
        for dd in sorted(glob.glob(R(pat))):
            if "/_bad" in dd:
                continue
            tp = os.path.join(dd, "task_results.jsonl")
            if not os.path.exists(tp):
                continue
            for line in open(tp):
                if not line.strip():
                    continue
                tr = json.loads(line)
                iid = tr["instance_id"]
                trp = os.path.join(dd, "traces", f"trace_{iid}.json")
                pp = os.path.join(dd, "patches", f"{iid}.patch")
                trace = json.load(open(trp)) if os.path.exists(trp) else None
                patch = open(pp, errors="replace").read() if os.path.exists(pp) else ""
                rows.append((dd, tr, trace, patch))
    return rows



# ============================================================================ tables / interventions

H120 = 120 / 3600.0  # mean seconds per task -> hours per 120 tasks
BUCKETS = ["post_budget", "submit_loop", "rejected", "loop", "repeat2", "an_overrun", "after_verify", "after_cover_preverify",
           "analyzer_ok", "root_ok"]
BUCKET_DESC = {
    "post_budget": "after the 100-call budget is exhausted (BudgetExceeded loops)",
    "submit_loop": "submit_patch re-called on an unchanged tree (run only ends on a text-only reply)",
    "rejected": "call rejected: malformed args (ADK missing params, backtick paths) or edit_file not-found",
    "loop": "3rd+ identical tool call with no state change in between",
    "repeat2": "2nd identical tool call with no state change",
    "an_overrun": "analyzer beyond 20 calls/invocation, or 2nd+ invocation",
    "after_verify": "after final patch content in place AND a passing verification",
    "after_cover_preverify": "after final patch content in place, before first passing verification",
    "analyzer_ok": "remaining analyzer work",
    "root_ok": "remaining root work",
}


def _m(rows, k):
    xs = [r.get(k) or 0.0 for r in rows]
    return st.mean(xs) if xs else float("nan")


def capture_table(cap_rows):
    out = "| run | n | solved | min/task mean / med / p90 | decode | prefill | per-call overhead | tool exec (in-task gaps) | setup+verify (between tasks) | LLM root / analyzer / compaction (s) | calls root / analyzer / compaction |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    for run in KAGGLE:
        for grp in ("all", "solved", "unsolved"):
            rs = [r for r in cap_rows if r["run"] == run]
            if grp != "all":
                if "resolved" not in rs[0]:
                    continue
                rs = [r for r in rs if r["resolved"] == (grp == "solved")]
            sp = [r["span_s"] / 60 for r in rs]
            tot = _m(rs, "span_s")
            f = lambda k: f"{_m(rs, k):.0f}s ({100 * _m(rs, k) / tot:.0f}%)"  # noqa: E731
            sol = sum(1 for r in rs if r.get("resolved")) if "resolved" in rs[0] else "–"
            out += (f"| {run} {grp if grp != 'all' else ''} | {len(rs)} | {sol} | {st.mean(sp):.2f} / {st.median(sp):.2f} / {pct(sp, .9):.2f} | "
                    f"{f('decode_s')} | {f('prefill_s')} | {f('overhead_s')} | {f('tool_gap_s')} | {f('between_s')} | "
                    f"{_m(rs, 'llm_root_s'):.0f} / {_m(rs, 'llm_analyzer_s'):.0f} / {_m(rs, 'llm_compact_s'):.0f} | "
                    f"{_m(rs, 'calls_root'):.0f} / {_m(rs, 'calls_analyzer'):.0f} / {_m(rs, 'calls_compact'):.1f} |\n")
    return out


def thinking_table(cap_rows):
    out = "| run | completion tok/task | reasoning tok | action tok | reasoning decode s | reasoning tok/call (calls with reasoning) | reasoning tok above 512/call | LLM calls | tok/call | compaction calls / s | post-budget s | repeat (pre-budget) s | rejected-call s | consecutive re-submit s |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    for run in KAGGLE:
        rs = [r for r in cap_rows if r["run"] == run]
        out += (f"| {run} | {_m(rs, 'ct'):.0f} | {_m(rs, 'reason_tok'):.0f} | {_m(rs, 'ct') - _m(rs, 'reason_tok'):.0f} | "
                f"{_m(rs, 'reason_decode_s'):.0f} | {_m(rs, 'reason_tok') / max(_m(rs, 'reason_calls'), 1e-9):.0f} | "
                f"{_m(rs, 'reason_gt512_tok'):.0f} | {_m(rs, 'calls'):.0f} | {_m(rs, 'ct') / _m(rs, 'calls'):.0f} | "
                f"{_m(rs, 'calls_compact'):.1f} / {_m(rs, 'llm_compact_s'):.0f} | {_m(rs, 'post_budget_s'):.0f} | {_m(rs, 'repeat_s'):.0f} | {_m(rs, 'rejected_s'):.0f} | {_m(rs, 'submit_repeat_s'):.0f} |\n")
    return out


def outcat_table(S):
    out = ""
    for run in KAGGLE:
        oc = S[f"outcat_{run}"]
        out += f"\n**{run}** completion tokens per call: " + ", ".join(
            f"{k} mean {v['mean']:.0f} / p50 {v['p50']} / p90 {v['p90']} / p99 {v['p99']}" for k, v in oc["ct_per_call"].items()) + "\n\n"
        out += "| what the call emitted | calls/task | completion tok/task | decode s/task |\n|---|---|---|---|\n"
        for k, v in sorted(oc["categories"].items(), key=lambda kv: -kv[1]["decode_s_per_task"]):
            out += f"| {k} | {v['calls_per_task']:.1f} | {v['tok_per_task']:.0f} | {v['decode_s_per_task']:.1f} |\n"
    return out


def bucket_table(trace_rows, sets):
    head = "| bucket | " + " | ".join(f"{s} s/task (%) [h/120]" for s in sets) + " |\n|---|" + "---|" * len(sets) + "\n"
    out = head
    tot = {s: _m([r for r in trace_rows if r["set"] == s], "l4_s") for s in sets}
    for b in BUCKETS + ["compact", "setup"]:
        k = {"compact": "compact_s", "setup": "setup_s"}.get(b, "bk_" + b)
        desc = {**BUCKET_DESC, "compact": "compaction LLM calls (rate from capture)",
                "setup": "sandbox setup + verification (capture mean)"}[b]
        cells = []
        for s in sets:
            v = _m([r for r in trace_rows if r["set"] == s], k)
            cells.append(f"{v:.0f} ({100 * v / tot[s]:.0f}%) [{v * H120:.2f}]")
        out += f"| {b}: {desc} | " + " | ".join(cells) + " |\n"
    out += "| **total (L4-estimated)** | " + " | ".join(f"**{tot[s]:.0f}** ({tot[s] / 60:.2f} min) [{tot[s] * H120:.2f}]" for s in sets) + " |\n"
    return out


def split_table(trace_rows, sets, keys):
    out = "| set | group | n | " + " | ".join(keys) + " |\n|---|---|---|" + "---|" * len(keys) + "\n"
    for s in sets:
        for grp in ("solved", "unsolved"):
            rs = [r for r in trace_rows if r["set"] == s and r["resolved"] == (grp == "solved")]
            cells = []
            for k in keys:
                xs = [r.get(k) or 0.0 for r in rs]
                cells.append(f"{st.mean(xs):.0f} / {st.median(xs):.0f} / {pct(xs, .9):.0f}" if xs else "–")
            out += f"| {s} | {grp} | {len(rs)} | " + " | ".join(cells) + " |\n"
    return out


def solved_timeline(trace_rows, sets):
    out = ("| set | solved n | cover found | L4 s/task | first edit s | final content in place s (calls) | after content: s (calls) | "
           "share of trajectory after content | after first passing verification s |\n|---|---|---|---|---|---|---|---|---|\n")
    for s in sets:
        rs = [r for r in trace_rows if r["set"] == s and r["resolved"]]
        cv = [r for r in rs if r.get("cover_s") is not None]
        g = lambda k, xs=None: [r.get(k) for r in (xs or rs) if r.get(k) is not None]  # noqa: E731
        ms = lambda xs: f"{st.mean(xs):.0f} / {st.median(xs):.0f}" if xs else "–"  # noqa: E731
        share = [r["after_cover_s"] / r["l4_agent_s"] for r in cv if r["l4_agent_s"]]
        out += (f"| {s} | {len(rs)} | {len(cv)} | {ms(g('l4_s'))} | {ms(g('first_mut_s'))} | {ms(g('cover_s', cv))} "
                f"({ms(g('cover_calls', cv))}) | {ms(g('after_cover_s', cv))} ({ms(g('after_cover_calls', cv))}) | "
                f"{st.mean(share):.0%} mean, {st.median(share):.0%} med | {ms(g('after_verify_nobudget_s', cv))} |\n")
    return out + "\n(cells: mean / median)\n"


def hopeless_table(trace_rows, sets, Ts=(3, 4, 5, 6, 8, 10, 12, 15)):
    out = "| set | T (L4 min) | tasks still running | solve rate of those | of their solves, content already in place at T | share of all L4 time spent after T | solved lost by a T-min cap |\n|---|---|---|---|---|---|---|\n"
    for s in sets:
        rs = [r for r in trace_rows if r["set"] == s]
        tot = sum(r["l4_s"] for r in rs)
        for T in Ts:
            run_ = [r for r in rs if r["l4_s"] > T * 60]
            sol = [r for r in run_ if r["resolved"]]
            inplace = [r for r in sol if r.get("cover_s") is not None and r["cover_s"] + r["setup_s"] <= T * 60]
            after = sum(max(0.0, r["l4_s"] - T * 60) for r in rs)
            out += (f"| {s} | {T} | {len(run_)} ({len(run_) / len(rs):.0%}) | {len(sol) / max(1, len(run_)):.0%} | "
                    f"{len(inplace)}/{len(sol)} | {after / tot:.0%} | {len(sol) - len(inplace)} ({(len(sol) - len(inplace)) / len(rs):.1%} of tasks) |\n")
    return out


def noedit_table(trace_rows, sets):
    out = "| set | rule: no source edit after K root tool calls -> submit & stop | triggered | solved lost | L4 s/task saved [h/120] |\n|---|---|---|---|---|\n"
    for s in sets:
        rs = [r for r in trace_rows if r["set"] == s]
        for K in NOEDIT_K:
            tr = [r for r in rs if r["noedit_abandon_save_s"].get(str(K), r["noedit_abandon_save_s"].get(K)) is not None]
            sv = sum(r["noedit_abandon_save_s"].get(str(K), r["noedit_abandon_save_s"].get(K)) for r in tr) / len(rs)
            out += f"| {s} | K={K} | {len(tr)} | {sum(r['resolved'] for r in tr)} | {sv:.0f} [{sv * H120:.2f}] |\n"
    return out


def analyzer_table(trace_rows, sets):
    out = "| set | analyzer L4 s/task | analyzer calls/task | invocations/task | tasks with >20 calls in one invocation | s/task beyond 20 calls or 2nd+ invocation | LOCATION file in final patch: yes / no / n.a. |\n|---|---|---|---|---|---|---|\n"
    for s in sets:
        rs = [r for r in trace_rows if r["set"] == s]
        if not any(r.get("calls_analyzer") for r in rs):
            continue
        u = Counter(r.get("an_used") for r in rs)
        out += (f"| {s} | {_m(rs, 'llm_analyzer_s'):.0f} | {_m(rs, 'calls_analyzer'):.0f} | {_m(rs, 'an_invocations'):.2f} | "
                f"{sum(1 for r in rs if (r.get('an_calls_max_inv') or 0) > 20)}/{len(rs)} | {_m(rs, 'bk_an_overrun'):.0f} | "
                f"{u[True]} / {u[False]} / {u[None]} |\n")
    return out


def obs_table(trace_rows, sets):
    out = "| set | observations/task | obs chars/task | median / p90 obs chars | obs > 4k chars per task | saving if capped at 2000 chars | at 1000 chars |\n|---|---|---|---|---|---|---|\n"
    for s in sets:
        rs = [r for r in trace_rows if r["set"] == s]
        out += (f"| {s} | {_m(rs, 'obs_n'):.0f} | {_m(rs, 'obs_chars'):.0f} | {st.median([r['obs_p50'] for r in rs]):.0f} / "
                f"{st.median([r['obs_p90'] for r in rs]):.0f} | {_m(rs, 'obs_gt4k'):.1f} | {_m(rs, 'cap2000_save_s'):.1f} s "
                f"[{_m(rs, 'cap2000_save_s') * H120:.2f} h] | {_m(rs, 'cap1000_save_s'):.1f} s [{_m(rs, 'cap1000_save_s') * H120:.2f} h] |\n")
    return out


def interventions(trace_rows, s, rejected_fix=0.5, budget_s=360.0):
    """per-task combined scenario on one set -> dict of savings (s/task) and the resulting L4 min/task."""
    rs = [r for r in trace_rows if r["set"] == s]
    n = len(rs)
    iv = {
        "I1 stop on BudgetExceeded (root+analyzer reply/submit at once)": _m(rs, "bk_post_budget"),
        "I2 loop breaker (3rd identical call w/o state change)": _m(rs, "bk_loop"),
        "I2b end with a text-only reply right after submit_patch (no re-submits)": _m(rs, "bk_submit_loop"),
        f"I3 avoid rejected calls (edit fallback; assume {rejected_fix:.0%} of their time saved)": rejected_fix * _m(rs, "bk_rejected"),
        "I4 analyzer hard cap 20 calls, single invocation": _m(rs, "bk_an_overrun"),
        "I5 submit right after the first passing verification of the final patch": _m(rs, "bk_after_verify"),
        "I6 cap observations at 2000 chars": _m(rs, "cap2000_save_s"),
        "I7 forbid narration text next to tool calls": _m(rs, "narr_s"),
    }
    base = _m(rs, "l4_s")
    combined = []
    for r in rs:
        sv = (r.get("bk_post_budget", 0) + r.get("bk_loop", 0) + r.get("bk_submit_loop", 0) + rejected_fix * r.get("bk_rejected", 0) +
              r.get("bk_an_overrun", 0) + r.get("bk_after_verify", 0) + r.get("cap2000_save_s", 0) + r.get("narr_s", 0))
        combined.append(r["l4_s"] - sv)
    res = dict(set=s, n=n, solved=sum(r["resolved"] for r in rs), base_s=base, items=iv, after_I1_I7_s=st.mean(combined))
    for T in (4, 5, 6, 8, 10):
        capped = [min(c, T * 60) for c in combined]
        lost = sum(1 for r in rs if r["resolved"] and (r.get("cover_s") is None or r["cover_s"] + r["setup_s"] > T * 60)
                   and r["l4_s"] > T * 60)
        res[f"cap{T}"] = dict(mean_s=st.mean(capped), lost=lost, lost_rate=lost / n)
    return res


def intervention_table(ivs):
    sets = [iv["set"] for iv in ivs]
    out = "| intervention | " + " | ".join(f"{s}: s/task [h/120]" for s in sets) + " |\n|---|" + "---|" * len(sets) + "\n"
    out += "| baseline L4-estimated | " + " | ".join(f"{iv['base_s']:.0f} ({iv['base_s'] / 60:.2f} min) [{iv['base_s'] * H120:.2f}]" for iv in ivs) + " |\n"
    for k in ivs[0]["items"]:
        out += f"| {k} | " + " | ".join(f"−{iv['items'][k]:.0f} [−{iv['items'][k] * H120:.2f}]" for iv in ivs) + " |\n"
    out += "| **after I1–I7 combined** | " + " | ".join(f"**{iv['after_I1_I7_s']:.0f}** ({iv['after_I1_I7_s'] / 60:.2f} min) [{iv['after_I1_I7_s'] * H120:.2f}]" for iv in ivs) + " |\n"
    for T in (4, 5, 6, 8, 10):
        out += f"| + max_time_minutes={T} (L4) | " + " | ".join(
            f"{iv[f'cap{T}']['mean_s']:.0f} ({iv[f'cap{T}']['mean_s'] / 60:.2f} min) [{iv[f'cap{T}']['mean_s'] * H120:.2f}]; solved lost {iv[f'cap{T}']['lost']}/{iv['n']} ({iv[f'cap{T}']['lost_rate']:.1%})"
            for iv in ivs) + " |\n"
    return out


def write_tables(path, cap_rows, trace_rows, S):
    main_sets = ["c9e_px", "c15n512_px", "c9e_A40serial", "c11n_L4", "c15t512_L4", "c11t_L4", "c8_px"]
    main_sets = [s for s in main_sets if any(r["set"] == s for r in trace_rows)]
    ivs = [interventions(trace_rows, s) for s in main_sets]
    S["interventions"] = ivs
    md = "# time_budget tables (generated by src/analysis/time_budget.py)\n\n"
    md += "## Latency models (L4, per capture)\n\n" + "\n".join(f"- {run}: {S[f'cap_{run}']['model']}" for run in KAGGLE) + "\n\n"
    md += "## T1 L4 capture wall-time decomposition (per task)\n\n" + capture_table(cap_rows)
    md += "\n## T2 Thinking cost (L4 captures, per task means)\n\n" + thinking_table(cap_rows)
    md += "\n## T3 Output tokens by what the call emitted (L4 captures)\n" + outcat_table(S)
    md += "\n## T4 Exclusive attribution of L4-estimated time (traces)\n\n" + bucket_table(trace_rows, main_sets)
    md += "\n## T5 Solved vs unsolved (mean / median / p90)\n\n" + split_table(
        trace_rows, main_sets, ["l4_s", "calls", "bk_post_budget", "bk_loop", "bk_rejected", "bk_after_verify", "llm_analyzer_s"])
    md += "\n## T6 Solved tasks: when is the fix in place?\n\n" + solved_timeline(trace_rows, main_sets)
    md += "\n## T7 Analyzer\n\n" + analyzer_table(trace_rows, main_sets)
    md += "\n## T8 Observation size\n\n" + obs_table(trace_rows, main_sets)
    md += "\n## T9 Hopeless detection: solve rate of tasks still running at T\n\n" + hopeless_table(trace_rows, ["c9e_px", "c15n512_px"])
    md += "\n## T10 Early abandon (no edit)\n\n" + noedit_table(trace_rows, ["c9e_px", "c15n512_px"])
    md += "\n## T11 Interventions (L4-estimated; h/120 = hours per 120 tasks)\n\n" + intervention_table(ivs)
    open(path, "w").write(md)
    return md

# ============================================================================ main

def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:.{nd}f}"


def tbl(head, rows):
    s = "| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n"
    for r in rows:
        s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=R("reports/time_budget"))
    ap.add_argument("--quick", action="store_true", help="only 1 seed of each proxy set")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    S = {}
    models, cap_rows, setup, compact_rate = {}, [], {}, {}
    cpt_all = {}
    # ---------------------------------------------------------------- captures
    for run in KAGGLE:
        recs = load_capture(run)
        n = segment(recs)
        m = LatModel.fit(recs)
        models[run] = m
        cpt_all[run] = calib_chars_per_token(recs)
        rows = capture_tasks(run, recs, n, m)
        S[f"outcat_{run}"] = output_categories(recs, m)
        cap_rows += rows
        # per-task setup+verify (between) on L4; last task has none
        betw = [r["between_s"] for r in rows[:-1]]
        setup[run] = st.mean(betw)
        compact_rate[run] = sum(r.get("llm_compact_s", 0) for r in rows) / max(1, sum(r.get("calls_root", 0) for r in rows))
        tool_gaps = [r["tool_gap_s"] for r in rows]
        ks = json.load(open(next(iter(glob.glob(R("results/kaggle", run, "results", "*", "kernel_summary.json"))))))
        S[f"cap_{run}"] = dict(model=m.desc(), coef=[m.a, m.b, m.c, m.d], chars_per_token=cpt_all[run],
                               tasks=n, kernel_wall_s=ks["wall_seconds"], sum_span_s=sum(r["span_s"] for r in rows),
                               setup_verify_mean_s=setup[run], tool_gap_mean_s=st.mean(tool_gaps),
                               calls=len(recs), kinds=Counter(r["kind"] for r in recs))
        print(f"[capture] {run}: {n} tasks, {len(recs)} calls; model {m.desc()}; chars/token {cpt_all[run]:.2f}")
    with open(os.path.join(a.out, "capture_tasks.jsonl"), "w") as f:
        for r in cap_rows:
            f.write(json.dumps(r) + "\n")
    # ---------------------------------------------------------------- traces
    trace_rows = []
    for name, (dirs, mrun) in TRACE_SETS.items():
        if not dirs:
            continue
        if a.quick and len(dirs) > 1:
            dirs = dirs[:1]
        model = models[mrun]
        tool_scale = 1.0
        rows = load_trace_set(name, dirs)
        for dd, tr, trace, patch in rows:
            r = analyze_task(tr, trace, patch, model, tool_scale, setup[mrun], CPT, compact_rate[mrun])
            r["set"] = name
            r["dir"] = os.path.relpath(dd, ROOT)
            trace_rows.append(r)
        print(f"[traces] {name}: {len(rows)} tasks")
    with open(os.path.join(a.out, "trace_tasks.jsonl"), "w") as f:
        for r in trace_rows:
            f.write(json.dumps(r, default=str) + "\n")
    S["trace_sets"] = sorted({r["set"] for r in trace_rows})
    S["missing_traces"] = Counter(r["set"] for r in trace_rows if r.get("no_trace"))
    md = write_tables(os.path.join(a.out, "tables.md"), cap_rows, [r for r in trace_rows if not r.get("no_trace")], S)
    print(md)
    json.dump(S, open(os.path.join(a.out, "summary.json"), "w"), indent=1, default=str)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
