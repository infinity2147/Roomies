"""Reproducible proxy-experiment scoreboard (one row per candidate x population).

    .venv/bin/python -m src.eval.px_scoreboard            # -> reports/scoreboard.md + results/scoreboard.json
    .venv/bin/python -m src.eval.px_scoreboard --no-cache # re-parse every trace

(Named px_scoreboard.py because src/eval/scoreboard.py is the older §8 per-system appender; this file does not touch it.)

Inputs (read-only):
  results/px/px_<cand>_s<seed>/<shard>/{task_results.jsonl,traces/,patches/,test_outputs/}  (dirs starting with _bad skipped)
     shard prefix -> population: s* full152, e* evalhalf85, t* trainhalf67 (ids from ops/queue/shards/*)
  results/px/pub_*  -> population "public" (public LB task set; informational only)
  ops/queue*/{done,failed,running,pending,parked}/*  "<submission_dir> <run> <shard_file> <mode>"  -> run -> bundle
  submissions/<dir>/{agent.yaml,configs/*.yaml,sub_agents/*.yaml,eval_config.yaml}  -> thinking / adapter / time cap
  results/px/time_*/ (A40 serial CONC=1 timing), results/kaggle/*-t30s (Kaggle L4 serial timing), ops/autopilot/lb_scores.tsv
Trace parsing is cached in results/.scoreboard_cache.json keyed by (path, mtime, size).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import re
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PX = ROOT / "results" / "px"
CACHE = ROOT / "results" / ".scoreboard_cache.json"
POP_OF_PREFIX = {"s": "full152", "e": "evalhalf85", "t": "trainhalf67", "p": "public"}
SHARD_DIRS = {"full152": "proxy", "evalhalf85": "proxy_evalhalf", "trainhalf67": "proxy_trainhalf", "public": "public"}

# ---------------------------------------------------------------- parent mapping (priority list of parent candidates)
# For a (task, seed) pair the first parent candidate that has that pair wins; parent runs from any population are used
# but restricted to the candidate's tasks (so eval-half candidates are only ever compared on eval-half tasks).
PARENT: dict[str, list[str]] = {
    "c8": [],
    "anchor": ["c8"], "c6a_t5": ["c8"], "c10": ["c8"],
    "c9a": ["c8"], "c9b": ["c8"], "c9c": ["c8"], "c9d": ["c8"], "c9e": ["c8"], "c9ae": ["c8"], "c9all": ["c8"],
    "c9ae_t5": ["c8"], "c9ae_t7": ["c8"],
    "c9e_evalhalf": ["c8"], "c9ae_evalhalf": ["c8"],
    "c11n": ["c8"], "c11t": ["c8"], "c11tc": ["c8"], "c11t_cap": ["c8"],
    "c13t": ["c8"], "c15n512": ["c8"], "c15t512": ["c8"], "c15t1024": ["c8"],
    "c14b": ["c11t"], "c14c": ["c11t"], "c14d": ["c11t"], "c14p": ["c11t"],
    "c16": ["c9e_evalhalf", "c9e"], "c17": ["c9e"],
    "c16_e2lora": ["c8"],  # bundle = C8 config + E2 adapter + 5-min cap (STATE 10-09 10:40), so C8 is the true parent
    "c18_e2lora": ["c8"], "c19_distill": ["c9ae_evalhalf"],
}
# Secondary comparisons shown in their own table.
EXTRA_CMP = [("c14b", "c8"), ("c14c", "c8"), ("c14d", "c8"), ("c14p", "c8"), ("c17", "c8"), ("c16", "c8"),
             ("c19_distill", "c8"), ("c9e_evalhalf", "c9ae_evalhalf"), ("c9e", "c9ae"), ("c17", "c11t"),
             ("c11t", "c9ae"), ("c9ae_t5", "c9ae"), ("c9ae_t7", "c9ae"), ("anchor", "c6a_t5")]

SUSPECT = {"c16_e2lora": "LoRA run under infra investigation (earlier attempt ran on base-only workers; 5-min cap confound)",
           "c18_e2lora": "LoRA run under infra investigation (~49 min/task, budget/timeouts); D30 rejection on hold",
           "c19_distill": "LoRA run under infra investigation (20/22 tasks hit 60-min timeout in first harvest)"}
NOTES = {  # decisions recorded in ops/autopilot/STATE.md / reports/council/DECISIONS.md
    "c8": "champion (LB 0.13)", "c9ae": "LB 0.10 (uncapped zip)", "c9ae_t5": "LB 0.08; 5-min cap",
    "c6a_t5": "LB 0.06; 5-min cap", "c9ae_t7": "7-min cap", "c11tc": "rejected (no gain, 5-min cap)",
    "c11t": "fails L4 time gate (D26)", "c11n": "fails L4 time gate (D28 note)", "c15t512": "fails L4 time gate",
    "c17": "fails A40 serial time gate (ratio 2.11 > 1.15)", "c16": "rejected (no gain vs C9e, graph-locate)",
    "c14p": "intra-task best-of-2", "c9e": "current daily release",
    "c11t_cap": "thinking capture runs (SFT data)",
}

# ---------------------------------------------------------------- 12-h projection inputs
L4_MEASURED = {  # Kaggle L4 serial, 30 ids (data/derived/l4_t30_ids.txt), min/task
    "c9ae": (4.92, "Kaggle L4 c9ae-t30s (D25)"), "c11n": (8.69, "Kaggle L4 c11n-t30s"),
    "c11t": (7.67, "Kaggle L4 c11t-t30s (D26)"), "c15t512": (8.97, "Kaggle L4 c15t512-t30s"),
}
A40_RATIO_C17_C9E = 2.11  # results/px/time_c17 vs time_c9e, CONC=1, same 30 ids (job 345996)
HIDDEN_TASKS, BUDGET_MIN = 120, 720


def l4_estimate(cand: str, cap: float | None) -> tuple[float | None, str]:
    base = cand.replace("_evalhalf", "")
    if base in L4_MEASURED:
        v, src = L4_MEASURED[base]
    elif base == "c9e":
        v, src = L4_MEASURED["c9ae"][0], "assumed = C9ae (same root, analyzer cap)"
    elif base == "c17":
        v, src = L4_MEASURED["c9ae"][0] * A40_RATIO_C17_C9E, "C9e(=C9ae) L4 x A40 serial ratio 2.11"
    elif base in ("c11tc", "c13t", "c14b", "c14c", "c14d", "c11t_cap"):
        v, src = L4_MEASURED["c11t"][0], "assumed = C11t (thinking root)"
    elif base == "c14p":
        v, src = 2 * L4_MEASURED["c11t"][0], "assumed 2 x C11t (two thinking solvers share one GPU)"
    elif base in ("c15n512", "c15t1024"):
        v, src = L4_MEASURED["c15t512"][0], "assumed = C15t512 (lower bound for t1024)"
    elif base in ("c16_e2lora", "c18_e2lora", "c19_distill"):
        v, src = L4_MEASURED["c9ae"][0], "assumed = C9ae (LoRA serving overhead unknown)"
    else:
        v, src = L4_MEASURED["c9ae"][0], "assumed = C9ae (non-thinking C8 family)"
    if cap:
        if cap < v:
            v, src = cap, src + f"; capped at {cap:g} min"
        else:
            src += f"; {cap:g}-min cap bounds tail"
    return v, src


# ---------------------------------------------------------------- trace parsing
BAD_ARGS_MARK = re.compile(r"`,\w+:|<\|\"\|>|`$")
TRUNC_NUDGE = "token limit before the tool call"
THINK_NUDGE = "token limit while thinking"


def parse_trace(path: str) -> dict:
    out = {"completion_tokens": None, "prompt_tokens": None, "trace_tool_calls": 0, "bad_tool_calls": 0,
           "budget_obs": 0, "trunc_nudges": 0, "think_nudges": 0, "trace_ok": False}
    try:
        t = json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return out
    out["trace_ok"] = True
    fm = t.get("final_metrics") or {}
    out["completion_tokens"] = fm.get("total_completion_tokens")
    out["prompt_tokens"] = fm.get("total_prompt_tokens")
    for s in t.get("steps", []):
        msg = s.get("message") or ""
        if (s.get("extra") or {}).get("event_type") == "continuation_nudge" and isinstance(msg, str):
            out["trunc_nudges"] += TRUNC_NUDGE in msg
            out["think_nudges"] += THINK_NUDGE in msg
        obs = s.get("observation")
        obs_txt = obs.get("content", "") if isinstance(obs, dict) else ""
        obs_txt = obs_txt if isinstance(obs_txt, str) else json.dumps(obs_txt)
        if "BudgetExceeded" in obs_txt:
            out["budget_obs"] += 1
        calls = s.get("tool_calls") or []
        invalid_obs = "mandatory input parameters" in obs_txt or "INVALID_ARGUMENTS" in obs_txt
        for c in calls:
            out["trace_tool_calls"] += 1
            name, args = c.get("function_name") or "", c.get("arguments")
            bad = not re.fullmatch(r"[a-z_0-9]+", name)
            if isinstance(args, dict):
                bad |= any(not re.fullmatch(r"[a-z_]+", str(k)) for k in args)
                bad |= bool(BAD_ARGS_MARK.search(json.dumps(args)[-2000:]))
            else:
                bad = True
            out["bad_tool_calls"] += bad or (invalid_obs and len(calls) == 1)
    return out


SYNTAX_RE = re.compile(r"^(E\s+)?(SyntaxError|IndentationError|TabError):", re.M)


def task_extras(args: tuple[str, str, str]) -> dict:
    shard_dir, iid, _ = args
    sd = Path(shard_dir)
    d = parse_trace(str(sd / "traces" / f"trace_{iid}.json"))
    pf = sd / "patches" / f"{iid}.patch"
    ptxt = pf.read_text(errors="ignore") if pf.exists() else ""
    d["leak"] = ("b/conftest.py" in ptxt) or ("b/pytest.ini" in ptxt)
    to = sd / "test_outputs" / f"{iid}.log"
    d["syntax_break"] = bool(to.exists() and SYNTAX_RE.search(to.read_text(errors="ignore")))
    return d


def file_key(p: Path) -> str:
    try:
        st = p.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except FileNotFoundError:
        return "missing"


# ---------------------------------------------------------------- loading
def shard_ids() -> dict[str, set[str]]:
    pops = {}
    for pop, sub in SHARD_DIRS.items():
        ids = set()
        for f in (ROOT / "ops/queue/shards" / sub).glob("*.txt"):
            ids |= {l.strip() for l in open(f) if l.strip()}
        pops[pop] = ids
    return pops


def run_bundles() -> dict[str, str]:
    m, rank = {}, {}
    for q in sorted(ROOT.glob("ops/queue*")):
        for state, r in (("done", 0), ("running", 1), ("parked", 2), ("pending", 3), ("failed", 4)):
            for f in (q / state).glob("*") if (q / state).is_dir() else []:
                if not f.is_file():
                    continue
                parts = f.read_text().split()
                if len(parts) >= 2 and (parts[1] not in rank or r < rank[parts[1]]):
                    m[parts[1]], rank[parts[1]] = parts[0], r
    return m


class _L(yaml.SafeLoader):
    pass


_L.add_constructor("!include", lambda l, n: {"__include__": l.construct_scalar(n)})


def _yload(p: Path):
    try:
        return yaml.load(p.read_text(), Loader=_L) or {}
    except Exception:  # noqa: BLE001
        return {}


def _gcc(agent_yaml: Path) -> dict:
    y = _yload(agent_yaml)
    g = y.get("generate_content_config") if isinstance(y, dict) else None
    if isinstance(g, dict) and "__include__" in g:
        return _yload((agent_yaml.parent / g["__include__"]).resolve())
    return g or {}


def bundle_info(sub: str | None) -> dict:
    info = {"adapter": None, "root_think": None, "analyzer_think": None, "cap_min": None, "analyzer": False}
    if not sub:
        return info
    d = ROOT / sub
    if not d.is_dir():
        return info
    ag = _yload(d / "agent.yaml")
    if isinstance(ag, dict) and ag.get("adapter"):
        info["adapter"] = str(ag["adapter"])
    elif (d / "adapters").is_dir():
        info["adapter"] = ",".join(sorted(p.name for p in (d / "adapters").iterdir()))

    def think(cfg: dict) -> str | None:
        tc = (cfg or {}).get("thinking_config") if isinstance(cfg, dict) else None
        if not tc:
            return None
        on = bool(tc.get("include_thoughts")) and (tc.get("thinking_budget") or 0) > 0
        return f"on({tc.get('thinking_budget')})" if on else "off"

    root = _gcc(d / "agent.yaml") or _yload(d / "configs/sampling.yaml")
    info["root_think"] = think(root)
    an = d / "sub_agents" / "code_analyzer.yaml"
    if an.exists():
        info["analyzer"] = True
        info["analyzer_think"] = think(_gcc(an))
    ec = _yload(d / "eval_config.yaml")
    if isinstance(ec, dict):
        info["cap_min"] = (ec.get("evaluation") or {}).get("max_time_minutes")
    return info


def err_class(e: str | None) -> str | None:
    if not e:
        return None
    if "session timeout" in e:
        return "timeout"
    if "tool call budget" in e or "LLM turns" in e or "turns budget" in e:
        return "budget"
    if "ContextWindowExceeded" in e:
        return "context"
    if "Failed to apply test_patch" in e:
        return "invalid_patch"
    if "without calling submit_patch" in e:
        return "no_submit"
    if any(k in e for k in ("NotFoundError", "InternalServerError", "TaskGroup", "No space left", "Connection")):
        return "infra"
    return "other"


def load_all(use_cache: bool) -> tuple[list[dict], dict]:
    rows, dupes = [], defaultdict(int)
    for f in sorted(PX.glob("*/*/task_results.jsonl")):
        run, shard = f.parent.parent.name, f.parent.name
        if run.startswith("_bad"):
            continue
        m = re.match(r"(px|pub)_(.+)_s(\d+)$", run)
        if not m or shard[0] not in POP_OF_PREFIX:
            continue
        pop = POP_OF_PREFIX[shard[0]] if m[1] == "px" else "public"
        seen = {}
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["instance_id"] in seen:
                dupes[run] += 1
            seen[r["instance_id"]] = r
        for iid, r in seen.items():
            rows.append({"cand": m[2], "seed": int(m[3]), "run": run, "shard": shard, "pop": pop,
                         "shard_dir": str(f.parent), "task": iid, "resolved": bool(r.get("resolved")),
                         "dur_s": r.get("duration_seconds") or 0.0, "tool_calls": r.get("tool_calls"),
                         "patch_size": r.get("agent_patch_size") or 0, "error": r.get("error"),
                         "eclass": err_class(r.get("error"))})
    cache = {}
    if use_cache and CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text())
        except Exception:  # noqa: BLE001
            cache = {}
    todo, keys = [], []
    for r in rows:
        sd = Path(r["shard_dir"])
        k = "|".join([str(sd.relative_to(ROOT)), r["task"], file_key(sd / "traces" / f"trace_{r['task']}.json"),
                      file_key(sd / "patches" / f"{r['task']}.patch"), file_key(sd / "test_outputs" / f"{r['task']}.log")])
        keys.append(k)
        if k not in cache:
            todo.append((r["shard_dir"], r["task"], k))
    if todo:
        with Pool(min(16, os.cpu_count() or 4)) as p:
            for (_, _, k), d in zip(todo, p.map(task_extras, todo, chunksize=16)):
                cache[k] = d
    new_cache = {k: cache[k] for k in keys}
    try:
        CACHE.write_text(json.dumps(new_cache))
    except OSError:
        pass
    for r, k in zip(rows, keys):
        r.update(new_cache[k])
    return rows, dupes


# ---------------------------------------------------------------- stats
def sign_test_p(w: int, l: int) -> float:
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n)


def paired(cand_map: dict, parent_maps: list[dict], tasks: set[str] | None = None, B: int = 2000) -> dict | None:
    """cand_map/parent_maps: {(task, seed): resolved}. Pairs = same task & seed label."""
    pairs = []
    for key, x in cand_map.items():
        if tasks is not None and key[0] not in tasks:
            continue
        for pm in parent_maps:
            if key in pm:
                pairs.append((key[0], int(x), int(pm[key])))
                break
    if not pairs:
        return None
    n = len(pairs)
    w = sum(x and not y for _, x, y in pairs)
    l = sum(y and not x for _, x, y in pairs)
    pc, pb = sum(x for _, x, _ in pairs) / n, sum(y for _, _, y in pairs) / n
    by_task = defaultdict(list)
    for t, x, y in pairs:
        by_task[t].append(x - y)
    tl = list(by_task.values())
    rng = random.Random(12345)
    boots = []
    for _ in range(B):
        s = c = 0
        for _ in range(len(tl)):
            v = tl[rng.randrange(len(tl))]
            s += sum(v)
            c += len(v)
        boots.append(s / c)
    boots.sort()
    return {"n_pairs": n, "n_tasks": len(tl), "cand": pc, "base": pb, "diff": pc - pb, "wins": w, "losses": l,
            "ci_lo": boots[int(0.025 * B)], "ci_hi": boots[int(0.975 * B) - 1], "sign_p": sign_test_p(w, l),
            "seeds": sorted({k[1] for k in cand_map if any(k in pm for pm in parent_maps)})}


def pctl(v: list[float], q: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    i = (len(v) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def passk(rows: list[dict]) -> dict | None:
    by = defaultdict(list)
    for r in rows:
        by[r["task"]].append(r["resolved"])
    multi = {t: v for t, v in by.items() if len(v) >= 2}
    if not multi:
        return None
    p1 = sum(sum(v) / len(v) for v in multi.values()) / len(multi)
    p2 = sum(1 - (math.comb(len(v) - sum(v), 2) / math.comb(len(v), 2)) for v in multi.values()) / len(multi)
    union = sum(any(v) for v in multi.values())
    stable = sum(all(v) for v in multi.values())
    return {"tasks": len(multi), "k_mean": sum(len(v) for v in multi.values()) / len(multi), "pass1": p1,
            "pass2": p2, "union": union, "union_rate": union / len(multi), "stable": stable,
            "stochastic": union - stable}


# ---------------------------------------------------------------- main
def fmt(x, nd=3, pct=False):
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:+.{nd}f}" if pct else f"{x:.{nd}f}"
    return str(x)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--md", default=str(ROOT / "reports" / "scoreboard.md"))
    ap.add_argument("--json", default=str(ROOT / "results" / "scoreboard.json"))
    a = ap.parse_args()

    pops = shard_ids()
    bmap = run_bundles()
    rows, dupes = load_all(not a.no_cache)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["cand"], r["pop"])].append(r)
    outcome = defaultdict(dict)  # cand -> {(task, seed): resolved}  (all populations)
    for r in rows:
        if r["pop"] != "public":
            outcome[r["cand"]][(r["task"], r["seed"])] = r["resolved"]

    lb = {}
    lbf = ROOT / "ops/autopilot/lb_scores.tsv"
    if lbf.exists():
        for line in lbf.read_text().splitlines()[1:]:
            p = line.split("\t")
            if len(p) >= 3:
                lb[p[1]] = p[2]

    table = []
    pop_order = {"full152": 0, "evalhalf85": 1, "trainhalf67": 2, "public": 3}
    for (cand, pop), rs in sorted(groups.items(), key=lambda kv: (pop_order[kv[0][1]], kv[0][0])):
        runs = sorted({r["run"] for r in rs})
        subs = sorted({bmap.get(r, "?") for r in runs})
        info = bundle_info(subs[0] if subs and subs[0] != "?" else None)
        seeds = sorted({r["seed"] for r in rs})
        n = len(rs)
        succ = sum(r["resolved"] for r in rs)
        tasks = pops.get(pop)
        par = PARENT.get(cand)
        cmp_ = cmp8 = None
        if par and pop != "public":
            cmp_ = paired({k: v for k, v in outcome[cand].items() if k[0] in tasks},
                          [outcome[p] for p in par], tasks)
            if par != ["c8"] and cand != "c8":
                cmp8 = paired({k: v for k, v in outcome[cand].items() if k[0] in tasks}, [outcome["c8"]], tasks)
        durs = [r["dur_s"] / 60 for r in rs]
        toks = [r["completion_tokens"] for r in rs if r.get("completion_tokens") is not None]
        tcalls = [r["tool_calls"] if r["tool_calls"] is not None else r["trace_tool_calls"] for r in rs]
        ec = defaultdict(int)
        for r in rs:
            ec[r["eclass"]] += 1
        budget = sum(r["eclass"] == "budget" or r.get("budget_obs", 0) > 0 for r in rs)
        expected = len(seeds) * len(tasks) if tasks else n
        mean_min = sum(durs) / n
        status = []
        if cand in SUSPECT:
            status.append("suspect")
        if mean_min < 1.0 or ec["infra"] > 0.3 * n:
            status.append("invalid")
        elif ec["infra"] > 0.05 * n:
            status.append("infra-errors")
        if n < expected:
            status.append(f"partial({n}/{expected})")
        if len(seeds) == 1 or n < 100:
            status.append("pilot")
        nleak = sum(r.get("leak", False) for r in rs)
        if nleak:
            clean = [r for r in rs if not r.get("leak")]
            status.append(f"CONTAMINATED: harness conftest/pytest.ini leak in {nleak}/{n} patches (D18: leak must be 0); "
                          f"pass@1 on leak-free rows {sum(r['resolved'] for r in clean) / max(len(clean), 1):.3f}")
        if cand in NOTES:
            status.append(NOTES[cand])
        if cand in SUSPECT:
            status.append(SUSPECT[cand])
        if dupes.get(runs[0]):
            status.append(f"{sum(dupes.get(x, 0) for x in runs)} re-run rows (last kept)")
        p1 = succ / n
        l4, l4src = l4_estimate(cand, info["cap_min"])
        frac1 = min(1.0, BUDGET_MIN / (HIDDEN_TASKS * l4)) if l4 else None
        frac15 = min(1.0, BUDGET_MIN / (HIDDEN_TASKS * l4 * 1.5)) if l4 else None
        table.append({
            "candidate": cand, "population": pop, "submission": ",".join(s.replace("submissions/", "") for s in subs),
            "parent": "/".join(par) if par else ("—" if par == [] else "?"), "adapter": info["adapter"],
            "root_think": info["root_think"], "analyzer_think": info["analyzer_think"] if info["analyzer"] else "n/a",
            "cap_min": info["cap_min"], "seeds": seeds, "runs": runs, "n": n, "succ": succ, "pass1": p1,
            "vs_parent": cmp_, "vs_c8": cmp8,
            "gen_tokens_per_task": (sum(toks) / len(toks)) if toks else None, "trace_coverage": len(toks) / n,
            "tool_calls_per_task": sum(tcalls) / n, "bad_tool_calls": sum(r.get("bad_tool_calls", 0) for r in rs),
            "bad_tool_calls_per_task": sum(r.get("bad_tool_calls", 0) for r in rs) / n,
            "trunc_nudges": sum(r.get("trunc_nudges", 0) for r in rs),
            "think_limit_nudges": sum(r.get("think_nudges", 0) for r in rs),
            "mean_min": mean_min, "p90_min": pctl(durs, 0.9), "timeouts": ec["timeout"], "budget": budget,
            "budget_task_err": ec["budget"], "context": ec["context"], "infra": ec["infra"], "no_submit": ec["no_submit"],
            "empty": sum(not r["patch_size"] for r in rs),
            "invalid_patch": sum(r["eclass"] == "invalid_patch" or r.get("syntax_break", False) for r in rs),
            "test_patch_conflict": ec["invalid_patch"], "syntax_break": sum(r.get("syntax_break", False) for r in rs),
            "leak": sum(r.get("leak", False) for r in rs), "status": "; ".join(status),
            "l4_min_task": l4, "l4_source": l4src, "frac_done_12h": frac1, "frac_done_12h_x1.5": frac15,
            "exp_12h": p1 * frac1 if frac1 is not None else None,
            "exp_12h_x1.5": p1 * frac15 if frac15 is not None else None,
            "passk": passk(rs),
        })

    # ------------------------------------------------ C8 reconciliation
    c8 = outcome["c8"]
    c8_seeds = sorted({s for _, s in c8})
    rec = {"per_seed": {}, "combos": {}, "as_seen_by": {}}
    for s in c8_seeds:
        v = [x for (t, ss), x in c8.items() if ss == s and t in pops["full152"]]
        rec["per_seed"][s] = {"n": len(v), "succ": sum(v), "rate": sum(v) / len(v)}
    for k in range(1, len(c8_seeds) + 1):
        S = c8_seeds[:k]
        v = [x for (t, ss), x in c8.items() if ss in S and t in pops["full152"]]
        rec["combos"]["s" + "+s".join(map(str, S))] = {"n": len(v), "succ": sum(v), "rate": sum(v) / len(v)}
    ev = [x for (t, _), x in c8.items() if t in pops["evalhalf85"]]
    rec["combos"]["all seeds, evalhalf85 ids only"] = {"n": len(ev), "succ": sum(ev), "rate": sum(ev) / len(ev)}
    for row in table:
        for key in ("vs_parent", "vs_c8"):
            c = row[key]
            if c and (row["parent"] == "c8" or key == "vs_c8"):
                rec["as_seen_by"][f"{row['candidate']} [{row['population']}]"] = {
                    "c8_rate": c["base"], "n_pairs": c["n_pairs"], "seeds": c["seeds"]}

    # ------------------------------------------------ extra comparisons
    extra = []
    for c, p in EXTRA_CMP:
        if c not in outcome or p not in outcome:
            continue
        pop = groups and next((pp for (cc, pp) in groups if cc == c and pp != "public"), None)
        res = paired(outcome[c], [outcome[p]], pops.get(pop))
        if res:
            extra.append({**res, "name": c, "vs": p, "pop": pop})

    # ------------------------------------------------ timing references
    timing = {}
    for d in sorted(PX.glob("time_*/*/task_results.jsonl")):
        v = [json.loads(l) for l in open(d) if l.strip()]
        timing[d.parent.parent.name] = {"n": len(v), "solved": sum(x["resolved"] for x in v),
                                        "min_per_task": sum(x["duration_seconds"] for x in v) / len(v) / 60,
                                        "hw": "A40 serial CONC=1"}
    for d in sorted((ROOT / "results/kaggle").glob("*-t30s/results/*/task_results.jsonl")):
        v = [json.loads(l) for l in open(d) if l.strip()]
        timing["kaggle:" + d.parent.name] = {"n": len(v), "solved": sum(x["resolved"] for x in v),
                                             "min_per_task": sum(x["duration_seconds"] for x in v) / len(v) / 60,
                                             "hw": "Kaggle L4 serial"}
    for d in sorted((ROOT / "results/kaggle").glob("*-t30s/results/*/kernel_summary.json")):
        k = json.loads(d.read_text())
        timing.setdefault("kaggle:" + d.parent.name, {"n": k.get("total"), "solved": k.get("resolved"),
                                                      "min_per_task": None, "hw": "Kaggle L4 serial"})
        timing["kaggle:" + d.parent.name]["wall_min_per_task"] = k.get("wall_seconds", 0) / max(k.get("total") or 1, 1) / 60

    out = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "rows": table, "c8_reconciliation": rec,
           "extra_comparisons": extra, "timing": timing, "lb": lb,
           "assumptions": {"hidden_tasks": HIDDEN_TASKS, "budget_min": BUDGET_MIN, "l4_measured": L4_MEASURED,
                           "a40_ratio_c17_c9e": A40_RATIO_C17_C9E}}
    Path(a.json).write_text(json.dumps(out, indent=1, default=str))
    Path(a.md).write_text(render_md(out))
    print(f"wrote {a.md} and {a.json} ({len(table)} rows, {len(rows)} task-runs)")


def render_md(o: dict) -> str:
    L = []
    P = L.append
    P(f"# Proxy experiment scoreboard\n\nGenerated {o['generated']} by `.venv/bin/python -m src.eval.px_scoreboard` "
      "(rerun to refresh; trace parsing cached in `results/.scoreboard_cache.json`). Machine-readable: `results/scoreboard.json`.\n")
    P("**Populations.** `full152` = proxy shards s0..s7 (152 tasks); `evalhalf85` = held-out half e0..e3 (85 tasks, used for "
      "fine-tuned models); `trainhalf67` = t0..t3; `public` = public-LB task set (informational). Never compare pass@1 across "
      "populations — use the paired Δ column, which is always computed on the candidate's own tasks.\n")
    P("**Columns.** Δ parent = paired diff on matched (task, seed-label) pairs vs the parent (parent runs from any population, "
      "restricted to the candidate's tasks); W/L = candidate-only / parent-only solves; CI = 95% task-clustered paired bootstrap "
      "(2000 resamples); p = exact two-sided sign test on W vs L. tok = mean generated (completion, incl. thinking) tokens/task from "
      "traces. calls = tool calls/task. badTC = rejected/invalid tool calls per task (missing mandatory args / INVALID_ARGUMENTS, "
      "malformed names/keys, plus tool calls truncated at the token limit). min, p90 = per-task **parallel-worker wall time on "
      "the proxy cluster (A40/L40/DGX, concurrent)** — not L4 serial time. TO = session timeouts; bud = tool-call/turn budget hit "
      "(task error or BudgetExceeded tool result); ctx = context-window errors; infra = model NotFound/5xx/ENOSPC; empty = no patch; "
      "inval = agent patch made the hidden test patch fail to apply, or test run shows Syntax/IndentationError (heuristic); "
      "leak = patch touches b/conftest.py or b/pytest.ini. Think = root/analyzer thinking (include_thoughts & budget>0).\n")

    for pop in ("full152", "evalhalf85", "trainhalf67", "public"):
        rows = [r for r in o["rows"] if r["population"] == pop]
        if not rows:
            continue
        P(f"\n## {pop}\n")
        P("| cand | bundle | parent | adapter | think root/anl | cap | seeds | n | succ | pass@1 | Δ parent [95% CI] | W/L | p | Δ vs C8 | "
          "tok/task | calls | badTC | min | p90 | TO | bud | ctx | infra | empty | inval | leak | status / notes |")
        P("|" + "---|" * 28)
        for r in sorted(rows, key=lambda r: -r["pass1"]):
            c, c8 = r["vs_parent"], r["vs_c8"]
            dpar = f"{c['diff']:+.3f} [{c['ci_lo']:+.3f},{c['ci_hi']:+.3f}] (n={c['n_pairs']})" if c else "—"
            wl = f"{c['wins']}/{c['losses']}" if c else "—"
            pv = f"{c['sign_p']:.3f}" if c else "—"
            d8 = f"{c8['diff']:+.3f} [{c8['ci_lo']:+.3f},{c8['ci_hi']:+.3f}] {c8['wins']}/{c8['losses']}" if c8 else ""
            tok = f"{r['gen_tokens_per_task']/1000:.1f}k" if r["gen_tokens_per_task"] else "–"
            if r["trace_coverage"] < 0.95:
                tok += f" ({r['trace_coverage']:.0%} traced)"
            P(f"| **{r['candidate']}** | {r['submission']} | {r['parent']} | {r['adapter'] or ''} | "
              f"{r['root_think'] or '?'}/{r['analyzer_think'] or '?'} | {r['cap_min'] or ''} | {','.join(map(str, r['seeds']))} | "
              f"{r['n']} | {r['succ']} | **{r['pass1']:.3f}** | {dpar} | {wl} | {pv} | {d8} | {tok} | "
              f"{r['tool_calls_per_task']:.0f} | {r['bad_tool_calls_per_task']:.2f} | {r['mean_min']:.1f} | {r['p90_min']:.1f} | "
              f"{r['timeouts']} | {r['budget']} | {r['context']} | {r['infra']} | {r['empty']} | {r['invalid_patch']} | "
              f"{r['leak']} | {r['status']} |")

    # pass@k
    P("\n## pass@k / oracle union (best-of-2 upside)\n")
    P("Per candidate, on tasks with ≥2 seed runs. pass@2 = unbiased estimate of P(at least one of 2 independent seeds solves) "
      "= mean_t[1 − C(k−c,2)/C(k,2)]; union = tasks solved by any seed (oracle, all k seeds); stable = solved by every seed. "
      "pass@2 − pass@1 is the ceiling for a perfect best-of-2 selector; a real selector (C14p) recovers only part of it, and "
      "best-of-2 doubles L4 time.\n")
    P("| cand | pop | tasks | mean k | pass@1 | pass@2 | Δ(2−1) | union (any seed) | union rate | stable | stochastic |")
    P("|" + "---|" * 11)
    pk_rows = [r for r in o["rows"] if r["passk"] and r["population"] != "public"]
    for r in sorted(pk_rows, key=lambda r: (r["population"], -r["passk"]["pass2"])):
        k = r["passk"]
        P(f"| {r['candidate']} | {r['population']} | {k['tasks']} | {k['k_mean']:.1f} | {k['pass1']:.3f} | {k['pass2']:.3f} | "
          f"{k['pass2']-k['pass1']:+.3f} | {k['union']} | {k['union_rate']:.3f} | {k['stable']} | {k['stochastic']} |")

    # extra comparisons
    P("\n## Secondary paired comparisons\n")
    P("| cand | vs | pop | n pairs | cand | base | Δ [95% CI] | W/L | sign p | seeds |")
    P("|" + "---|" * 10)
    for e in o["extra_comparisons"]:
        P(f"| {e['name']} | {e['vs']} | {e['pop']} | {e['n_pairs']} | {e['cand']:.3f} | {e['base']:.3f} | "
          f"{e['diff']:+.3f} [{e['ci_lo']:+.3f},{e['ci_hi']:+.3f}] | {e['wins']}/{e['losses']} | {e['sign_p']:.3f} | "
          f"{','.join(map(str, e['seeds']))} |")

    # C8 reconciliation
    rec = o["c8_reconciliation"]
    P("\n## C8 baseline reconciliation\n")
    P("| C8 seed (full152) | n | solved | rate |\n|---|---|---|---|")
    for s, v in rec["per_seed"].items():
        P(f"| s{s} | {v['n']} | {v['succ']} | {v['rate']:.3f} |")
    P("\n| pooled set | n | solved | rate |\n|---|---|---|---|")
    for s, v in rec["combos"].items():
        P(f"| {s} | {v['n']} | {v['succ']} | {v['rate']:.3f} |")
    P("\nC8 rate as seen by each paired comparison (base rate restricted to that candidate's matched pairs):\n")
    P("| comparison | C8 rate on pairs | n pairs | seeds paired |\n|---|---|---|---|")
    for k, v in sorted(rec["as_seen_by"].items(), key=lambda kv: kv[1]["c8_rate"]):
        P(f"| {k} | {v['c8_rate']:.3f} | {v['n_pairs']} | {','.join(map(str, v['seeds']))} |")
    P(RECON_TEXT)

    # 12 h projection
    P("\n## Expected 12-hour hidden score (projection)\n")
    P(PROJ_TEXT)
    P("| cand | pop | pass@1 | L4 min/task | source | frac of 120 done in 12 h | exp. score | frac @1.5× safety | exp. @1.5× | status |")
    P("|" + "---|" * 10)
    for r in sorted([r for r in o["rows"] if r["population"] in ("full152", "evalhalf85")],
                    key=lambda r: -(r["exp_12h_x1.5"] or 0)):
        P(f"| {r['candidate']} | {r['population']} | {r['pass1']:.3f} | {r['l4_min_task']:.2f} | {r['l4_source']} | "
          f"{r['frac_done_12h']:.2f} | {r['exp_12h']:.3f} | {r['frac_done_12h_x1.5']:.2f} | {r['exp_12h_x1.5']:.3f} | "
          f"{r['status'].split(';')[0][:60]} |")

    P("\n## Timing references\n")
    P("| run | hw | n | solved | mean min/task (sum of task durations) | wall min/task |\n|---|---|---|---|---|---|")
    for k, v in o["timing"].items():
        P(f"| {k} | {v['hw']} | {v['n']} | {v['solved']} | {fmt(v.get('min_per_task'), 2)} | {fmt(v.get('wall_min_per_task'), 2)} |")
    P("\nPublic LB: " + ", ".join(f"{k} = {v}" for k, v in o["lb"].items()) + "\n")
    return "\n".join(L) + "\n"


RECON_TEXT = """
**Why C8 shows 0.303 / 0.309 / 0.310 / 0.323 / 0.325 in different reports.** `px_report.py` prints, for every candidate, the
C8 rate *on that candidate's matched (task, seed) pairs*, and C8 seeds were added over time (s1, s2, s3, then s4), so the
"C8 baseline" quoted in each STATE.md entry is a different subset:

* **0.303** = C8 seed 1 alone (46/152): the base for every single-seed candidate (C9b, C9c, C9d, C10, C15t512, C15t1024, C14c).
* **0.309** = C8 s1+s2 (94/304): the base for 2-seed candidates (C9a, C9ae, C11n, C11t, ...) — e.g. "c8 0.309 vs anchor" (10:40).
* **0.310** = C8 s1+s2 restricted to the pairs C18 had completed (297 then, 303 now) — "C18 0.175 vs C8 0.310".
* **0.323** = C8 s1+s2+s3 restricted to the 437 pairs C17 has (C17 s3 is partial) — the C17 "+0.126/+0.137 vs C8" line.
* **0.325** = C8 s1+s2+s3 (148/456) — the 20:40 calibration entry ("c8 0.325") and the base for every 3-seed candidate
  (anchor, C6a_t5, C9ae_t5, C11tc); while C9ae_t5 was still incomplete (n=427) the same pairing printed 0.321.
* **0.324** = all four C8 seeds pooled (197/608), the base for C9ae_t7 (5 seeds; pairs on s1-s4).

Seed 3 is the high run (0.355) and seed 1 the low one (0.303), so the more seeds a comparison pairs on, the higher "C8"
looks; single-seed candidates were all judged against the weakest C8 seed, which inflates their Δ by ~+0.02.
None of these is an error — they are the same data on different pair sets. The per-seed spread (0.303-0.355, SD ≈ 0.02, i.e.
±3 tasks) is the run-to-run noise floor; any claimed gain under ~0.03 on a single seed pair is inside it.

**Recommended canonical C8 baseline.** Quote C8 on full152 as **pooled over all available seeds (s1-s4): 197/608 = 0.324**,
always with the seed list. For decisions use only the **paired Δ on matched (task, seed) pairs** (the table above shows the
matching C8 rate), never a candidate's pass@1 against a differently-seeded C8 number; for eval-half candidates use C8 (all seeds)
restricted to the 85 eval-half ids. Run new candidates on seeds that C8 already has (s1-s4) so every pair is matched.
"""

PROJ_TEXT = """Expected score = proxy pass@1 × fraction of the 120 hidden tasks finished in 720 min, where fraction =
min(1, 720 / (120 × L4 min/task)). Assumptions: (1) L4 serial min/task measured on Kaggle (30 ids) for C9ae 4.92, C11t 7.67,
C11n 8.69, C15t512 8.97; C9e ≈ C9ae; C17 = 4.92 × 2.11 (A40 serial C17/C9e ratio on the same 30 ids); other candidates
inherit their family's number (column "source"); LoRA serving overhead is ignored. (2) Bundles with `max_time_minutes` are
bounded by the cap. (3) Proxy pass@1 transfers to hidden tasks (it does not in absolute terms: LB 0.13 vs proxy 0.32 for C8 —
use this column for *ranking*), and eval-half pass@1 is on a different, easier/harder set than full152. (4) D28 found the real
scorer run ≥45 % slower than our L4 projection, so the "@1.5×" columns divide the fraction by 1.5. (5) Unfinished tasks score 0;
in practice an uncapped bundle that overruns the notebook limit can score **nothing** (D28 "Kaggle Error"), so fraction < 1 for an
uncapped bundle is a hard-failure risk, not partial credit — cap it before release.
"""

if __name__ == "__main__":
    main()
