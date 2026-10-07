"""E2: convert open OpenHands SWE trajectories (nebius/SWE-rebench-openhands-trajectories, CC-BY-4.0, teacher
Qwen3-Coder-480B) into SFT sequences in OUR deployment format (ADK harness tools, our C11t system prompt, thinking ON).

Mapping (OpenHands -> harness):
  execute_bash{command}                         -> run_command{command}
  str_replace_editor view (file)                -> read_file{filepath,start_line,end_line} (150-line window, as the harness)
  str_replace_editor view (directory)           -> run_command{find <dir> -maxdepth 2 ...}
  str_replace_editor str_replace                -> edit_file{filepath,old_string,new_string}
  str_replace_editor create (source file)       -> write_file{filepath,content}
  str_replace_editor create (scratch/test file) -> run_command{cat > /tmp/<name> <<'EOF' ...} (+ later paths rewritten)
  think{thought} + assistant narration          -> reasoning_content of the next action turn (thinking channel)
  finish                                        -> submit_patch{}
  task_tracker                                  -> dropped (call + its observation)
Paths: /workspace/<owner>__<repo>__<ver> -> /workspace. Observations truncated to the harness limit (5000 chars).
Filters: resolved=1; repo not in the competition public repos or our proxy repos (held-out eval stays clean);
no str_replace on test files; <= --max-turns assistant actions; at least one source edit.
Long trajectories are cut into windows (system + issue prompt + consecutive turns <= --window-tokens), approximating
what the scorer's events compaction leaves in context; every action turn inside a window is trained.

Usage (login node; tokenizer only, no GPU):
  .venv-harness/bin/python -m src.sft.convert_openhands --n 500 --out data/derived/sft/e2_nebius_pilot.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from src.sft.build_dataset import render_segment_thinking
from src.sft.format import MODEL, ROOT

PARQUET = ROOT / "data/external/nebius/trajectories.parquet"
DEPLOY_CAPTURE = ROOT / "results/kaggle/c11t-t30s/results/c11t-t30s/capture.jsonl"
PUBLIC_REPOS = {"fastapi/fastapi", "textualize/rich", "psf/requests", "encode/httpx"}
OBS_LIMIT = 5000
SCRATCH_RE = re.compile(r"(^|/)(tests?/|test_[^/]*$|[^/]*_test\.py$|(repro|reproduce|debug|verify|check|comprehensive|demo|example|simple|final|edge)[^/]*\.py$)")
TEST_RE = re.compile(r"(^|/)(tests?/|test_[^/]*$|[^/]*_test\.py$|conftest\.py$)")


def deploy_template() -> tuple[str, list[dict], str]:
    """(system prompt, tools, user-prompt suffix) exactly as the scorer sent them for the C11t root agent."""
    for line in open(DEPLOY_CAPTURE):
        req = json.loads(line)["request"]
        if len(req["messages"]) == 2 and any(t["function"]["name"] == "code_analyzer" for t in req["tools"]):
            user = req["messages"][1]["content"]
            return req["messages"][0]["content"], req["tools"], user[user.index("## Task Budget"):]
    raise SystemExit("no root request found in deployment capture")


def est_tokens(m: dict) -> int:
    n = len(m.get("content") or "") + len(m.get("reasoning_content") or "")
    n += sum(len(json.dumps(tc["function"]["arguments"])) for tc in m.get("tool_calls") or [])
    return n // 3 + 8


class Converter:
    def __init__(self, repo_dir: str):
        self.root = repo_dir.rstrip("/")
        self.moves: dict[str, str] = {}  # scratch path -> /tmp path

    def path(self, p: str) -> str:
        p = p.replace(self.root, "/workspace")
        return self.moves.get(p, p)

    def text(self, s: str) -> str:
        s = (s or "").replace(self.root, "/workspace")
        for src, dst in self.moves.items():
            s = s.replace(src, dst)
            rel = src[len("/workspace/"):] if src.startswith("/workspace/") else None
            if rel:
                s = re.sub(rf"(?<![\w/.]){re.escape(rel)}(?![\w])", dst, s)
        return s

    def call(self, name: str, args: dict, files_in_patch: set[str]) -> tuple[str, dict] | None | str:
        """-> (tool, args) | None (drop) | 'think' | 'finish' | 'bad'"""
        if name == "think":
            return "think"
        if name == "task_tracker":
            return None
        if name == "finish":
            return "finish"
        if name == "execute_bash":
            if args.get("is_input") in (True, "true") or not args.get("command"):
                return None
            return "run_command", {"command": self.text(args["command"])}
        if name != "str_replace_editor":
            return "bad"
        cmd, p = args.get("command"), self.path(args.get("path", ""))
        if cmd == "view":
            if "." not in p.rsplit("/", 1)[-1] and not args.get("view_range"):
                return "run_command", {"command": f"find {p} -maxdepth 2 -not -path '*/.*' | head -100"}
            vr = args.get("view_range") or [1, 150]
            s = max(1, int(vr[0])); e = int(vr[1]) if len(vr) > 1 and int(vr[1]) > 0 else s + 149
            return "read_file", {"filepath": p, "start_line": s, "end_line": min(e, s + 149)}
        if cmd == "str_replace":
            if TEST_RE.search(p):
                return "bad"
            return "edit_file", {"filepath": p, "old_string": self.text(args.get("old_str", "")),
                                 "new_string": self.text(args.get("new_str", ""))}
        if cmd == "create":
            rel = p[len("/workspace/"):] if p.startswith("/workspace/") else p
            body = self.text(args.get("file_text", ""))
            if SCRATCH_RE.search(rel) or rel not in files_in_patch:
                dst = "/tmp/" + rel.rsplit("/", 1)[-1]
                self.moves[p] = dst
                return "run_command", {"command": f"cat > {dst} <<'EOF'\n{body}\nEOF"}
            return "write_file", {"filepath": p, "content": body}
        return None


def patch_files(diff: str) -> set[str]:
    return set(re.findall(r"^\+\+\+ b/(.+)$", diff or "", flags=re.M))


def convert(row: dict, system: str, tools: list[dict], suffix: str, max_turns: int) -> tuple[list[dict] | None, str]:
    tr = row["trajectory"]
    user0 = tr[1]["content"] or ""
    m = re.search(r"<uploaded_files>\s*(\S+)\s*</uploaded_files>", user0)
    iss = re.search(r"<issue_description>\s*(.*?)\s*</issue_description>", user0, flags=re.S)
    if not m or not iss:
        return None, "no_prompt_parse"
    cv = Converter(m.group(1))
    files = patch_files(row["model_patch"])
    user = f"You are evaluating a software engineering task for repository {row['repo']}.\n\nProblem Statement:\n{iss.group(1)}\n\n{suffix}"
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    pending: list[str] = []
    drop_ids: set[str] = set()
    n_act, n_src_edit, k = 0, 0, 0
    for msg in tr[2:]:
        if msg["role"] == "tool":
            if msg["tool_call_id"] in drop_ids:
                continue
            if msgs[-1]["role"] == "assistant" and msgs[-1].get("tool_calls"):
                tcid = msgs[-1]["tool_calls"][0]["id"]
                if msg["tool_call_id"] == tcid or msgs[-1]["tool_calls"][0].get("_src") == msg["tool_call_id"]:
                    obs = cv.text(msg["content"] or "")
                    if len(obs) > OBS_LIMIT:
                        obs = obs[:OBS_LIMIT] + "\n... [output truncated]"
                    msgs.append({"role": "tool", "tool_call_id": tcid, "name": msgs[-1]["tool_calls"][0]["function"]["name"],
                                 "content": obs})
            continue
        if msg["role"] != "assistant":
            continue
        text = (msg["content"] or "").strip()
        calls = msg["tool_calls"] or []
        if text:
            pending.append(text)
        if not calls:
            continue
        tc = calls[0]
        for extra in calls[1:]:
            drop_ids.add(extra["id"])
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return None, "bad_json"
        res = cv.call(tc["function"]["name"], args, files)
        if res == "think":
            if args.get("thought"):
                pending.append(args["thought"].strip())
            drop_ids.add(tc["id"])
            continue
        if res is None:
            drop_ids.add(tc["id"])
            continue
        if res == "bad":
            return None, "test_edit_or_unknown_tool"
        if res == "finish":
            name, a = "submit_patch", {}
        else:
            name, a = res
        k += 1
        am = {"role": "assistant", "content": "",
              "tool_calls": [{"id": f"call_{k}", "type": "function", "function": {"name": name, "arguments": a}, "_src": tc["id"]}]}
        if pending:
            am["reasoning_content"] = cv.text("\n\n".join(pending))
            pending = []
        msgs.append(am)
        n_act += 1
        n_src_edit += name in ("edit_file", "write_file")
        if name == "submit_patch":
            msgs.append({"role": "tool", "tool_call_id": f"call_{k}", "name": "submit_patch",
                         "content": "Patch submitted."})
            break
    if not n_src_edit:
        return None, "no_source_edit"
    if n_act > max_turns:
        return None, "too_many_turns"
    if msgs[-1].get("name") != "submit_patch":
        return None, "no_submit"
    for mm in msgs:
        for t in mm.get("tool_calls") or []:
            t.pop("_src", None)
    return msgs, "ok"


def windows(msgs: list[dict], budget: int) -> list[tuple[int, int]]:
    """[(start, end)) slices over msgs[2:] (pairs of assistant+tool) so that base + slice <= budget tokens."""
    base = est_tokens(msgs[0]) + est_tokens(msgs[1])
    body = msgs[2:]
    out, s = [], 0
    while s < len(body):
        e, tok = s, base
        while e < len(body) and tok + est_tokens(body[e]) <= budget:
            tok += est_tokens(body[e]); e += 1
        if e < len(body) and body[e - 1]["role"] == "assistant":
            e -= 1  # never end a window on an action without its observation
        if e <= s:
            break
        out.append((s + 2, e + 2))
        if e >= len(body):
            break
        nxt = max(e - 4, s + 1)  # overlap = the last 2 action/observation pairs (event retention)
        while nxt < len(body) and body[nxt]["role"] != "assistant":
            nxt += 1
        s = nxt
    return out


def to_seg(msgs: list[dict], tools: list[dict], a: int, b: int) -> list[dict]:
    """Synthetic 'capture calls' for the window msgs[a:b], with msgs[:2] as the fixed base context."""
    base, win = msgs[:2], msgs[a:b]
    seg = []
    for i, m in enumerate(win):
        if m["role"] != "assistant":
            continue
        resp_msg = {"role": "assistant", "content": m.get("content") or "", "tool_calls": [
            {**t, "function": {"name": t["function"]["name"], "arguments": json.dumps(t["function"]["arguments"])}}
            for t in m["tool_calls"]]}
        if m.get("reasoning_content"):
            resp_msg["reasoning_content"] = m["reasoning_content"]
        hist = [dict(x, tool_calls=[{**t, "function": {"name": t["function"]["name"], "arguments": json.dumps(t["function"]["arguments"])}}
                                    for t in x["tool_calls"]]) if x.get("tool_calls") else dict(x) for x in base + win[:i]]
        seg.append({"request": {"messages": hist, "tools": tools}, "response": {"choices": [{"message": resp_msg}]}})
    return seg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="trajectories to convert (random sample of eligible)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-turns", type=int, default=90)
    ap.add_argument("--window-tokens", type=int, default=20000)
    ap.add_argument("--max-seq-tokens", type=int, default=32768)
    ap.add_argument("--out", default=str(ROOT / "data/derived/sft/e2_nebius_pilot.jsonl"))
    ap.add_argument("--dump-msgs", default=None, help="also write converted message lists (debug)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1, help="process every nshards-th eligible row (parallel SLURM tasks)")
    a = ap.parse_args()

    import pyarrow.parquet as pq
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    system, tools, suffix = deploy_template()
    proxy_repos = {json.loads(l)["repo"].lower() for l in open(ROOT / "data/derived/proxy/valid_tasks.jsonl")}
    excluded = PUBLIC_REPOS | proxy_repos
    pf = pq.ParquetFile(PARQUET)
    import zlib

    rows = []  # stream; keep only this shard's eligible rows (memory ~ 1/nshards of the dataset)
    for rg in range(pf.num_row_groups):
        meta = pf.read_row_group(rg, columns=["trajectory_id", "repo", "resolved"]).to_pylist()
        keep = [i for i, r in enumerate(meta) if r["resolved"] and r["repo"].lower() not in excluded
                and zlib.crc32(f"{a.seed}:{r['trajectory_id']}".encode()) % a.nshards == a.shard]
        if not keep:
            continue
        tb = pf.read_row_group(rg, columns=["instance_id", "repo", "trajectory", "model_patch", "resolved"]).take(keep)
        rows.extend(tb.to_pylist())
    random.Random(a.seed).shuffle(rows)
    stats, seen_inst = Counter(), Counter()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    dump = open(a.dump_msgs, "w") if a.dump_msgs else None
    with open(a.out, "w") as f:
        for r in rows:
            if stats["traj_ok"] >= a.n:
                break
            if seen_inst[r["instance_id"]] >= 2:  # cap 2 trajectories per task
                stats["cap_per_task"] += 1
                continue
            msgs, why = convert(r, system, tools, suffix, a.max_turns)
            stats[why] += 1
            if msgs is None:
                continue
            stats["traj_ok"] += 1
            seen_inst[r["instance_id"]] += 1
            if dump:
                dump.write(json.dumps({"instance_id": r["instance_id"], "repo": r["repo"], "messages": msgs}) + "\n")
            for wi, (s, e) in enumerate(windows(msgs, a.window_tokens)):
                ids, mask, info = render_segment_thinking(to_seg(msgs, tools, s, e), tok)
                stats.update({f"render_{k}": v for k, v in info.items()})
                if not ids or len(ids) > a.max_seq_tokens or sum(mask) == 0:
                    stats["window_dropped"] += 1
                    continue
                stats["windows"] += 1
                stats["tokens"] += len(ids)
                stats["trained_tokens"] += sum(mask)
                f.write(json.dumps({"instance_id": r["instance_id"], "repo": r["repo"].split("/")[-1].lower(),
                                    "source": "nebius", "window": wi, "input_ids": ids, "loss_mask": mask}) + "\n")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
