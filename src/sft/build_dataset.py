"""E1: build SFT sequences from capture.jsonl (exact per-call prompts/responses recorded by the
capture proxy) for tasks the harness marked resolved.

Calls are grouped per task (by the harness user prompt), ordered by time, and split into
"segments": a call continues the current segment if its prompt messages == previous prompt +
previous response + tool results (i.e. no compaction happened in between). Each segment becomes ONE
training sequence = last call's prompt + its response, with the loss mask on every assistant turn
generated inside that segment (earlier, compacted-away turns are context only).

Usage (legacy, thinking-off captures with capture.jsonl inside the run dir):
  .venv-harness/bin/python -m src.sft.build_dataset --runs results/kaggle/c6a_full_r2/results/c6a_full_r2 ... \
           --out data/derived/sft/c6a_e1.jsonl [--max-tokens 32768]

Usage (E1 capture mode: ap_worker.sbatch with APQ=ops/queue_cap CAPTURE=1, thinking ON):
  .venv-harness/bin/python -m src.sft.build_dataset --capture results/capture --out data/derived/sft/e1_capture.jsonl
  Each results/capture/<jobid>_<slot>.jsonl holds every chat-completion call of that worker slot; the sibling
  .items.jsonl lists the queue items the slot ran ({"t","item","run"}). A call belongs to the item whose start
  precedes it (items are sequential per slot), i.e. to (run, shard); the shard's task list
  (ops/queue/shards/proxy/<shard>.txt) restricts the problem-statement match to the root call's first user
  message (resolves the two duplicated pyglove statements, which live in different shards). Sub-agent
  (code_analyzer) sessions are recognised by their system prompt and attached to the task whose root agent
  issued the identical `code_analyzer(request=...)` call in the same item. Pass/fail = results/px/<run>/<shard>/
  task_results.jsonl. D5 filters (reports/council/DECISIONS.md): resolved, clean patch, no test/config edit in
  the trajectory, no repetition loop (drop, or --loop-policy mask), explicit submit_patch, malformed turns
  masked, <=2 root trajectories per task. Rendering = Gemma-4 chat template with enable_thinking=True and the
  captured `reasoning` re-attached to every trained assistant turn as `reasoning_content` (what ADK sends back
  in history), so the loss covers `<|channel>thought ... <channel|>` + tool call / answer.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from src.sft.format import EMPTY_THOUGHT, MODEL, ROOT, to_template_msgs

TASKS = ROOT / "data" / "tasks.jsonl"


def task_key(user_msg: str, tasks: dict[str, str]) -> str | None:
    for iid, ps in tasks.items():
        if ps[:400] in user_msg:
            return iid
    return None


def resp_to_msg(resp: dict) -> dict:
    m = resp["choices"][0]["message"]
    out = {"role": "assistant"}
    if m.get("tool_calls"):
        out["tool_calls"] = [{"type": "function", "id": tc["id"], "function": tc["function"]} for tc in m["tool_calls"]]
    if m.get("content"):
        out["content"] = m["content"]
    return out


def strip_ids(msgs):
    out = []
    for m in msgs:
        # ids and echoed thinking (ADK sends reasoning_content back in history) do not break a segment
        m = {k: v for k, v in m.items() if k not in ("tool_call_id", "reasoning_content", "reasoning") and v not in (None, "")}
        if "tool_calls" in m:
            m["tool_calls"] = [{"name": t["function"]["name"], "arguments": t["function"]["arguments"] if isinstance(t["function"]["arguments"], str) else json.dumps(t["function"]["arguments"])} for t in m["tool_calls"]]
        out.append(m)
    return out


def segments(calls: list[dict]) -> list[list[dict]]:
    segs, cur, prev_full = [], [], None
    for c in calls:
        msgs = c["request"]["messages"]
        if prev_full is not None and strip_ids(msgs[: len(prev_full)]) == strip_ids(prev_full):
            cur.append(c)
        else:
            if cur:
                segs.append(cur)
            cur = [c]
        prev_full = msgs + [resp_to_msg(c["response"])]
    if cur:
        segs.append(cur)
    return segs


def render_segment(seg: list[dict], tokenizer, strip_reasoning: bool = False) -> tuple[list[int], list[int]]:
    last = seg[-1]
    msgs = to_template_msgs(last["request"]["messages"] + [resp_to_msg(last["response"])])
    if strip_reasoning:  # distillation: ADK echoes reasoning_content in history and the template renders it even with
        # enable_thinking=False, so 57% of v1 targets started with a thought block (reports/lora_forensics_20261010.md §4)
        msgs = [{k: v for k, v in m.items() if k not in ("reasoning_content", "reasoning")} for m in msgs]
    tools = last["request"].get("tools")
    first_gen = len(seg[0]["request"]["messages"])  # assistant turns at index >= this are trained
    ids: list[int] = []
    mask: list[int] = []
    for i, m in enumerate(msgs):
        if m["role"] != "assistant" or i < first_gen:
            continue
        p = tokenizer.apply_chat_template(msgs[:i], add_generation_prompt=True, tokenize=False, tools=tools, enable_thinking=False)
        if p.endswith(EMPTY_THOUGHT):  # first generation of a model turn: keep history format so later
            p = p[: -len(EMPTY_THOUGHT)]  # prompts stay exact prefixes (3-token difference, see format.py)
        p_ids = tokenizer(p, add_special_tokens=False)["input_ids"]
        full = tokenizer.apply_chat_template(msgs[: i + 1], tokenize=False, tools=tools, enable_thinking=False)
        # generated text = continuation of the history render after the prompt (minus empty-thought tokens)
        hist = tokenizer.apply_chat_template(msgs[:i], tokenize=False, tools=tools, enable_thinking=False)
        gen_text = full[len(hist):] if full.startswith(hist) else full[len(p):]
        if gen_text.startswith("<|turn>model\n"):
            gen_text = gen_text[len("<|turn>model\n"):]
        stop = "<|tool_response>" if m.get("tool_calls") else ""
        gen_text = gen_text.split("<|tool_response>")[0] + stop if m.get("tool_calls") else gen_text
        g_ids = tokenizer(gen_text, add_special_tokens=False)["input_ids"]
        # context tokens not yet in the sequence
        if ids and p_ids[: len(ids)] == ids:
            ctx = p_ids[len(ids):]
        else:  # first trained turn (or empty-thought prefix difference): restart from this prompt
            ids, mask, ctx = [], [], p_ids
        ids += ctx
        mask += [0] * len(ctx)
        ids += g_ids
        mask += [1] * len(g_ids)
    return ids, mask

# ============================================================================= E1 capture mode

PROXY_TASK_FILES = [ROOT / "data" / "derived" / "proxy" / "tasks.jsonl",
                    ROOT / "data" / "derived" / "proxy" / "tasks_google.jsonl"]
SHARDS_DIR = ROOT / "ops" / "queue" / "shards" / "proxy"
RESULTS_PX = ROOT / "results" / "px"
# LORO folds by org/repo group (reports/autopilot/e1_inventory.md §5); repo = longest instance_id prefix below.
FOLDS = {"F1": ["click", "flask", "jinja", "werkzeug"],
         "F2": ["pyglove", "fiddle", "ml_collections", "etils"],
         "F3": ["tenacity", "typer", "sqlmodel", "sqlparse"],
         "F4": ["marshmallow", "attrs", "tqdm", "requests_oauthlib"]}
REPOS = sorted((r for rs in FOLDS.values() for r in rs), key=len, reverse=True)
FOLD_OF = {r: f for f, rs in FOLDS.items() for r in rs}
# D5 "clean patch / no test edit": any touched path matching this is disqualifying
TEST_CFG_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)(test_[^/]*|[^/]*_test)\.py$|(^|/)conftest\.py$"
                         r"|(^|/)(pytest\.ini|tox\.ini|setup\.cfg|setup\.py|pyproject\.toml|noxfile\.py|MANIFEST\.in)$"
                         r"|(^|/)\.github/|(^|/)(repro|reproduce|scratch|tmp|debug)[^/]*\.py$")
EDIT_TOOLS = {"edit_file", "write_file"}
ANALYZER_TOOL = "code_analyzer"
ITEM_RE = re.compile(r"^\d+_([a-z]+\d+)_(.+)$")  # 08_s3_px_c11t_s2 -> shard s3, run px_c11t_s2


def repo_of_iid(iid: str) -> str | None:
    iid = iid.removeprefix("mined_")
    for r in REPOS:
        if iid.startswith(r + "_"):
            return r
    return None


def load_proxy_tasks(files=None) -> dict[str, dict]:
    out = {}
    for f in files or PROXY_TASK_FILES:
        if Path(f).exists():
            for l in open(f):
                r = json.loads(l)
                out[r["instance_id"]] = r
    return out


def load_items(items_file: Path) -> list[dict]:
    """[{t, item, run, shard}] sorted by t for one slot tag."""
    out = []
    for l in open(items_file):
        l = l.strip()
        if not l:
            continue
        r = json.loads(l)
        m = ITEM_RE.match(r["item"])
        r["shard"] = m.group(1) if m else None
        r.setdefault("run", m.group(2) if m else None)
        out.append(r)
    return sorted(out, key=lambda r: r["t"])


def agent_of(call: dict, marker: str = "code_analyzer") -> str:
    msgs = call["request"]["messages"]
    sys_txt = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" and isinstance(msgs[0].get("content"), str) else ""
    return "analyzer" if marker in sys_txt[:300] else "root"


def first_user(call: dict) -> str | None:
    for m in call["request"]["messages"]:
        if m["role"] == "user":
            c = m.get("content")
            if isinstance(c, list):
                c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
            return c
    return None


def resp_msg(call: dict) -> dict:
    return call["response"]["choices"][0]["message"]


def resp_tool_calls(call: dict) -> list[dict]:
    return resp_msg(call).get("tool_calls") or []


def tc_args(tc: dict) -> dict:
    a = tc["function"].get("arguments")
    if isinstance(a, str):
        try:
            return json.loads(a) if a else {}
        except json.JSONDecodeError:
            return {"_raw": a}
    return a or {}


def match_task(user_msg: str, tasks: dict[str, dict], candidates: set[str], n: int = 400) -> tuple[str | None, str]:
    """-> (instance_id | None, 'ok'|'none'|'ambiguous'): problem statement prefix must appear in the user
    message; `candidates` (the shard's task ids) restricts the search so duplicated statements across shards
    cannot collide."""
    hits = [iid for iid in candidates if iid in tasks and tasks[iid]["problem_statement"][:n] in user_msg]
    if len(hits) == 1:
        return hits[0], "ok"
    return None, ("none" if not hits else "ambiguous")


def assign_capture(capdir: Path, tasks: dict[str, dict], shards_dir: Path = SHARDS_DIR, marker: str = "code_analyzer"):
    """Read results/capture/*.jsonl (+ .items.jsonl). Returns (calls, report):
    calls = list of records with added keys tag, item, run, shard, agent, instance_id, status_assign;
    report = per-(tag,item) counters used for validation."""
    calls, report = [], {}
    shard_ids = {}
    for cap in sorted(capdir.glob("*.jsonl")):
        if cap.name.endswith(".items.jsonl"):
            continue
        tag = cap.stem
        items_file = capdir / f"{tag}.items.jsonl"
        items = load_items(items_file) if items_file.exists() else []
        starts = [it["t"] for it in items]
        recs = []
        for l in open(cap):
            l = l.strip()
            if not l:
                continue
            try:
                c = json.loads(l)
            except json.JSONDecodeError:
                continue
            if c.get("status") != 200 or "response" not in c or not c["response"].get("choices"):
                continue
            k = bisect.bisect_right(starts, c["t"]) - 1
            it = items[k] if k >= 0 else None
            c.update(tag=tag, item=it["item"] if it else None, run=it["run"] if it else None,
                     shard=it["shard"] if it else None, agent=agent_of(c, marker), instance_id=None, status_assign="no_item")
            recs.append(c)
        # root calls: task by statement prefix within the shard
        for c in recs:
            if c["item"] is None or c["agent"] != "root":
                continue
            if c["shard"] not in shard_ids:
                f = shards_dir / f"{c['shard']}.txt"
                shard_ids[c["shard"]] = set(f.read_text().split()) if f.exists() else set()
            u = first_user(c) or ""
            iid, st = match_task(u, tasks, shard_ids[c["shard"]])
            c["instance_id"], c["status_assign"] = iid, st
        # analyzer calls: first user message == root's code_analyzer(request=...) in the same item
        req_map: dict[tuple, set] = defaultdict(set)
        for c in recs:
            if c["agent"] != "root" or not c["instance_id"]:
                continue
            tcs = list(resp_tool_calls(c))
            for m in c["request"]["messages"]:
                if m["role"] == "assistant":
                    tcs += m.get("tool_calls") or []
            for tc in tcs:
                if tc["function"]["name"] == ANALYZER_TOOL:
                    req = tc_args(tc).get("request")
                    if isinstance(req, str):
                        req_map[(c["item"], req.strip())].add(c["instance_id"])
        for c in recs:
            if c["item"] is None or c["agent"] != "analyzer":
                continue
            owners = req_map.get((c["item"], (first_user(c) or "").strip()), set())
            if len(owners) == 1:
                c["instance_id"], c["status_assign"] = next(iter(owners)), "ok"
            else:
                c["status_assign"] = "none" if not owners else "ambiguous"
        for c in recs:
            key = (tag, c["item"])
            r = report.setdefault(key, Counter())
            r["calls"] += 1
            r[c["agent"]] += 1
            r[c["status_assign"]] += 1
        calls += recs
    return calls, report


def validate_report(report: dict, strict: bool) -> bool:
    ok = True
    print("assignment per (slot, item): calls root analyzer ok none ambiguous")
    for (tag, item), r in sorted(report.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        bad = r["none"] + r["ambiguous"] + r["no_item"]
        ok &= bad == 0
        print(f"  {tag} {item}: {r['calls']} {r['root']} {r['analyzer']} {r['ok']} {r['none']} {r['ambiguous']}"
              + ("  <-- UNASSIGNED" if bad else ""))
    if not ok:
        print("assignment validation FAILED: some calls do not match a task of their shard" + ("" if strict else " (continuing, --no-strict)"))
        if strict:
            sys.exit(2)
    return ok


def load_outcomes(run: str, shard: str, results_px: Path = RESULTS_PX) -> tuple[dict[str, bool], Path]:
    d = results_px / run / shard
    f = d / "task_results.jsonl"
    if not f.exists():
        return {}, d
    return {json.loads(l)["instance_id"]: bool(json.loads(l).get("resolved")) for l in open(f) if l.strip()}, d


def patch_paths(patch_text: str) -> list[str]:
    out = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            pth = line[4:].split("\t")[0].strip()
            if pth != "/dev/null":
                out.append(pth[2:] if pth[:2] in ("a/", "b/") else pth)
    return out


def edited_paths(calls: list[dict]) -> list[str]:
    out = []
    for c in calls:
        for tc in resp_tool_calls(c):
            if tc["function"]["name"] in EDIT_TOOLS:
                out += [v for v in tc_args(tc).values() if isinstance(v, str) and "/" in v or isinstance(v, str) and v.endswith(".py")]
    return out


def loop_turns(calls: list[dict], k: int = 4) -> set[int]:
    """Indices (into `calls`) of turns that repeat the previous tool call verbatim, once a run reaches k
    identical consecutive calls (D5 repetition loop). The first call of the run is not flagged."""
    sig = []
    for c in calls:
        tcs = resp_tool_calls(c)
        sig.append(json.dumps([(t["function"]["name"], tc_args(t)) for t in tcs], sort_keys=True) if tcs else None)
    flagged = set()
    i = 0
    while i < len(sig):
        j = i
        while j + 1 < len(sig) and sig[j + 1] == sig[i] and sig[i] is not None:
            j += 1
        if j - i + 1 >= k:
            flagged.update(range(i + 1, j + 1))
        i = j + 1
    return flagged


def malformed(call: dict) -> bool:
    """Turn to mask (D5: mask, don't drop): truncated generation or an unparsed tool call left in content."""
    ch = call["response"]["choices"][0]
    if ch.get("finish_reason") == "length":
        return True
    m = ch["message"]
    content = m.get("content") or ""
    return not m.get("tool_calls") and ("<|tool_call>" in content or content.lstrip().startswith("call:"))


REQUIRE_SUBMIT = True  # --allow-no-submit: the harness grades the final diff whether or not submit_patch was called


def d5_root_filter(calls: list[dict], resolved: bool, patch_text: str | None) -> tuple[list[str], set[int]]:
    """-> (reasons to drop, turn indices to mask). Empty reasons = keep."""
    reasons = []
    if not resolved:
        reasons.append("unresolved")
    if patch_text is None:
        reasons.append("no_patch")
    elif any(TEST_CFG_RE.search(p) for p in patch_paths(patch_text)):
        reasons.append("dirty_patch")
    if any(TEST_CFG_RE.search(p) for p in edited_paths(calls)):
        reasons.append("test_edit")
    if REQUIRE_SUBMIT and not any(tc["function"]["name"] == "submit_patch" for c in calls for tc in resp_tool_calls(c)):
        reasons.append("no_submit")
    return reasons, {i for i, c in enumerate(calls) if malformed(c)}


def resp_to_msg_thinking(resp: dict) -> dict:
    """Captured response -> history assistant message incl. the thinking (vLLM returns it as `reasoning`;
    ADK/LiteLLM send it back in later requests as `reasoning_content`, which the Gemma-4 template renders
    as <|channel>thought ... <channel|> on tool-call turns after the last user message)."""
    out = resp_to_msg(resp)
    m = resp["choices"][0]["message"]
    r = m.get("reasoning") or m.get("reasoning_content")
    if r and r.strip():
        out["reasoning_content"] = r.strip()
    return out


THOUGHT_OPEN, THOUGHT_CLOSE = "<|channel>thought\n", "\n<channel|>"


def render_segment_thinking(seg: list[dict], tokenizer, masked_turns: set[int] = frozenset(), inject: bool = True):
    """Thinking-ON rendering of one segment (consecutive calls without compaction) -> (ids, mask, info).
    Trained assistant turns = those produced by calls in `seg`; context = everything before. For each
    trained turn the prompt is the template of the preceding messages with add_generation_prompt (exactly
    what vLLM built, enable_thinking=True => `<|think|>` in the system turn and no empty thought channel),
    and the target is the template delta for that assistant message (thought channel + tool calls +
    `<|tool_response>` stop, or thought channel + answer + `<turn|>`). The template drops the thought on
    turns without tool calls, so for those the channel is prepended by hand."""
    last = seg[-1]
    msgs = list(last["request"]["messages"]) + [resp_to_msg_thinking(last["response"])]
    first_gen = len(seg[0]["request"]["messages"])
    by_index = {len(c["request"]["messages"]): k for k, c in enumerate(seg)}  # assistant index -> call k
    if inject:  # make sure every trained turn carries its own captured thinking
        for i, k in by_index.items():
            if i < len(msgs) and msgs[i]["role"] == "assistant" and not msgs[i].get("reasoning_content"):
                r = resp_msg(seg[k]).get("reasoning") or resp_msg(seg[k]).get("reasoning_content")
                if r and r.strip():
                    msgs[i]["reasoning_content"] = r.strip()
    tm = to_template_msgs(msgs)
    tools = last["request"].get("tools")
    kw = dict(tokenize=False, tools=tools, enable_thinking=True)
    ids, mask = [], []
    info = Counter()
    for i, m in enumerate(tm):
        if m["role"] != "assistant" or i < first_gen:
            continue
        p = tokenizer.apply_chat_template(tm[:i], add_generation_prompt=True, **kw)
        hist = tokenizer.apply_chat_template(tm[:i], **kw)
        full = tokenizer.apply_chat_template(tm[: i + 1], **kw)
        if not full.startswith(hist):
            info["render_prefix_fail"] += 1
            continue
        gen = full[len(hist):]
        if gen.startswith("<|turn>model\n"):
            gen = gen[len("<|turn>model\n"):]
        if m.get("tool_calls"):
            gen = gen.split("<|tool_response>")[0] + "<|tool_response>"
        else:
            if gen.endswith("\n"):
                gen = gen[:-1]
            if m.get("reasoning_content") and not gen.startswith(THOUGHT_OPEN):
                gen = THOUGHT_OPEN + m["reasoning_content"] + THOUGHT_CLOSE + gen
        p_ids = tokenizer(p, add_special_tokens=False)["input_ids"]
        g_ids = tokenizer(gen, add_special_tokens=False)["input_ids"]
        if ids and p_ids[: len(ids)] == ids:
            ctx = p_ids[len(ids):]
        else:
            if ids:
                info["token_prefix_break"] += 1
            ids, mask, ctx = [], [], p_ids
        train = 0 if by_index.get(i) in masked_turns else 1
        info["turns"] += 1
        info["masked_turns"] += 1 - train
        info["thinking_turns"] += bool(m.get("reasoning_content"))
        ids += ctx + g_ids
        mask += [0] * len(ctx) + [train] * len(g_ids)
    return ids, mask, info


def build_capture(a, tokenizer) -> dict:
    tasks = load_proxy_tasks(a.tasks_files)
    capdir = Path(a.capture)
    calls, report = assign_capture(capdir, tasks, Path(a.shards_dir), a.analyzer_marker)
    validate_report(report, strict=a.strict)
    results_px = Path(a.results_px)
    # group: (tag,item,iid) -> root calls ; (tag,item,iid,request) -> analyzer calls
    root_calls, ana_calls = defaultdict(list), defaultdict(list)
    for c in calls:
        if c["status_assign"] != "ok":
            continue
        if c["agent"] == "root":
            root_calls[(c["tag"], c["item"], c["instance_id"])].append(c)
        else:
            ana_calls[(c["tag"], c["item"], c["instance_id"], (first_user(c) or "").strip())].append(c)
    stats = Counter()
    kept: dict[str, list] = defaultdict(list)  # iid -> [(n_calls, key, calls, masked)]
    for key, cs in root_calls.items():
        cs.sort(key=lambda c: c["t"])
        tag, item, iid = key
        resolved_map, rdir = load_outcomes(cs[0]["run"], cs[0]["shard"], results_px)
        pf = rdir / "patches" / f"{iid}.patch"
        reasons, masked = d5_root_filter(cs, resolved_map.get(iid, False), pf.read_text() if pf.exists() else None)
        loops = loop_turns(cs)
        if loops:
            if a.loop_policy == "drop":
                reasons.append("loop")
            else:
                masked |= loops
        stats["root_traj_total"] += 1
        if reasons:
            for r in reasons:
                stats[f"drop_{r}"] += 1
            stats["root_traj_dropped"] += 1
            continue
        kept[iid].append((len(cs), key, cs, masked))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_seq = n_tok = n_train = 0
    with open(out, "w") as f:
        for iid, lst in sorted(kept.items()):
            lst.sort(key=lambda x: x[0])
            if len(lst) > a.max_per_task:
                stats["capped_trajs"] += len(lst) - a.max_per_task
            for n_calls, (tag, item, _), cs, masked in lst[: a.max_per_task]:
                stats["root_traj_kept"] += 1
                run, shard = cs[0]["run"], cs[0]["shard"]
                base = {"run": run, "shard": shard, "slot": tag, "instance_id": iid, "repo": repo_of_iid(iid),
                        "fold": FOLD_OF.get(repo_of_iid(iid))}
                groups = [("root", 0, cs, masked)]
                k = 0
                for (t2, i2, iid2, _req), acs in sorted(ana_calls.items(), key=lambda kv: min(c["t"] for c in kv[1])):
                    if (t2, i2, iid2) == (tag, item, iid):
                        k += 1
                        acs.sort(key=lambda c: c["t"])
                        groups.append(("analyzer", k, acs, {i for i, c in enumerate(acs) if malformed(c)} | (loop_turns(acs) if a.loop_policy == "mask" else set())))
                        if a.loop_policy == "drop" and loop_turns(acs):
                            stats["drop_analyzer_loop"] += 1
                            groups.pop()
                            continue
                        stats["analyzer_traj_kept"] += 1
                for agent, traj, gcs, gmask in groups:
                    for s, seg in enumerate(segments(gcs)):
                        # masked indices are relative to gcs; map to this segment
                        off = gcs.index(seg[0])
                        seg_mask = {i - off for i in gmask if off <= i < off + len(seg)}
                        if a.distill_thinking_off:  # thinking distillation: teacher = thinking run, student = thinking-off root
                            ids, mask = render_segment(seg, tokenizer, strip_reasoning=True)
                            info = Counter(turns=1)
                        else:
                            ids, mask, info = render_segment_thinking(seg, tokenizer, seg_mask, inject=not a.no_inject_reasoning)
                        for kk, v in info.items():
                            stats[kk] += v
                        if not ids or sum(mask) == 0:
                            stats["empty_seq"] += 1
                            continue
                        if len(ids) > a.max_tokens:
                            stats["too_long"] += 1
                            continue
                        f.write(json.dumps({**base, "agent": agent, "traj": traj, "segment": s, "n_calls": len(seg),
                                            "input_ids": ids, "loss_mask": mask}) + "\n")
                        n_seq += 1
                        n_tok += len(ids)
                        n_train += sum(mask)
                        stats[f"seq_{agent}"] += 1
    stats.update(sequences=n_seq, tokens=n_tok, trainable=n_train, tasks_kept=len(kept))
    print(f"sequences={n_seq} tokens={n_tok} trainable={n_train} {dict(sorted(stats.items()))} -> {out}")
    if a.stats_json:
        Path(a.stats_json).write_text(json.dumps(dict(stats), indent=1))
    return dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--tasks-file", default=str(TASKS))
    ap.add_argument("--capture", help="E1 capture mode: directory with <jobid>_<slot>.jsonl + .items.jsonl")
    ap.add_argument("--tasks-files", nargs="+", default=[str(p) for p in PROXY_TASK_FILES])
    ap.add_argument("--shards-dir", default=str(SHARDS_DIR))
    ap.add_argument("--results-px", default=str(RESULTS_PX))
    ap.add_argument("--analyzer-marker", default="code_analyzer", help="substring of the sub-agent system prompt")
    ap.add_argument("--loop-policy", choices=["drop", "mask"], default="drop", help="D5 repetition loop: strict drop or lenient mask")
    ap.add_argument("--max-per-task", type=int, default=2)
    ap.add_argument("--no-inject-reasoning", action="store_true", help="keep history exactly as captured (no thinking re-attached)")
    ap.add_argument("--allow-no-submit", action="store_true", help="keep resolved runs that never called submit_patch")
    ap.add_argument("--distill-thinking-off", action="store_true",
                    help="render captured THINKING runs in thinking-OFF format without reasoning (distil actions into a fast root)")
    ap.add_argument("--no-strict", dest="strict", action="store_false", help="continue when some calls cannot be assigned")
    ap.add_argument("--stats-json")
    a = ap.parse_args()
    global REQUIRE_SUBMIT
    REQUIRE_SUBMIT = not a.allow_no_submit
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    if a.capture:
        build_capture(a, tok)
        return
    tasks = {json.loads(l)["instance_id"]: json.loads(l)["problem_statement"] for l in open(a.tasks_file)}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_seq = n_tok = n_train = 0
    stats = defaultdict(int)
    with open(out, "w") as f:
        for run in a.runs:
            rd = Path(run)
            resolved = {json.loads(l)["instance_id"]: json.loads(l)["resolved"] for l in open(rd / "task_results.jsonl")}
            by_task = defaultdict(list)
            for l in open(rd / "capture.jsonl"):
                c = json.loads(l)
                if c.get("status") != 200 or "response" not in c:
                    continue
                users = [m["content"] for m in c["request"]["messages"] if m["role"] == "user" and isinstance(m.get("content"), str)]
                iid = task_key(users[0], tasks) if users else None
                if iid:
                    by_task[iid].append(c)
            for iid, calls in by_task.items():
                if not resolved.get(iid):
                    stats["unresolved_tasks"] += 1
                    continue
                calls.sort(key=lambda c: c["t"])
                for k, seg in enumerate(segments(calls)):
                    ids, mask = render_segment(seg, tok)
                    if not ids or sum(mask) == 0:
                        continue
                    if len(ids) > a.max_tokens:
                        stats["too_long"] += 1
                        continue
                    f.write(json.dumps({"run": rd.name, "instance_id": iid, "segment": k, "input_ids": ids, "loss_mask": mask}) + "\n")
                    n_seq += 1
                    n_tok += len(ids)
                    n_train += sum(mask)
                stats["resolved_tasks"] += 1
    print(f"sequences={n_seq} tokens={n_tok} trainable={n_train} {dict(stats)} -> {out}")


if __name__ == "__main__":
    main()
