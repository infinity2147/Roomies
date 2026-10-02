"""E1: build SFT sequences from capture.jsonl (exact per-call prompts/responses recorded by the
capture proxy) for tasks the harness marked resolved.

Calls are grouped per task (by the harness user prompt), ordered by time, and split into
"segments": a call continues the current segment if its prompt messages == previous prompt +
previous response + tool results (i.e. no compaction happened in between). Each segment becomes ONE
training sequence = last call's prompt + its response, with the loss mask on every assistant turn
generated inside that segment (earlier, compacted-away turns are context only).

Usage: .venv-harness/bin/python -m src.sft.build_dataset --runs results/kaggle/c6a_full_r2/results/c6a_full_r2 ... \
           --scaffold c6a --out data/derived/sft/c6a_e1.jsonl [--max-tokens 32768]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
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
        m = {k: v for k, v in m.items() if k not in ("tool_call_id",)}
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


def render_segment(seg: list[dict], tokenizer) -> tuple[list[int], list[int]]:
    last = seg[-1]
    msgs = to_template_msgs(last["request"]["messages"] + [resp_to_msg(last["response"])])
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=32768)
    ap.add_argument("--tasks-file", default=str(TASKS))
    a = ap.parse_args()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
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
