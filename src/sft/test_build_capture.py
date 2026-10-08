"""Synthetic test of build_dataset --capture (assignment by slot/interval, root vs analyzer sessions, D5
filters, thinking-on rendering). Uses a stub tokenizer that mimics the Gemma-4 template structure, so it
runs in .venv (no transformers):  .venv/bin/python -m pytest -q src/sft/test_build_capture.py"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from src.sft import build_dataset as bd

SPECIAL = re.compile(r"<\|[a-z_]+\|?>|<[a-z_]+\|>")


class StubTok:
    """Gemma-4-shaped chat template (system <|think|>, thought channel only on tool-call turns, tool
    responses rendered inside the model turn, no <|turn>model after a tool response) + char tokenizer."""

    def __init__(self):
        self.vocab: dict[str, int] = {}

    def apply_chat_template(self, msgs, add_generation_prompt=False, tokenize=False, tools=None, enable_thinking=False):
        out = "<bos><|turn>system\n" + ("<|think|>\n" if enable_thinking else "") + msgs[0]["content"] + "<turn|>\n"
        prev, last_type = None, None
        rest = msgs[1:]
        for i, m in enumerate(rest):
            if m["role"] == "tool":
                continue
            role = "model" if m["role"] == "assistant" else m["role"]
            if not (role == "model" and prev == "assistant"):
                out += f"<|turn>{role}\n"
            prev = m["role"]
            if m["role"] == "assistant":
                if m.get("reasoning_content") and m.get("tool_calls"):
                    out += "<|channel>thought\n" + m["reasoning_content"] + "\n<channel|>"
                for tc in m.get("tool_calls") or []:
                    out += "<|tool_call>call:" + tc["function"]["name"] + json.dumps(tc["function"]["arguments"], sort_keys=True) + "<tool_call|>"
                follows = [x for x in rest[i + 1:] if x["role"] == "tool"] if m.get("tool_calls") else []
                follows = follows[: len(m.get("tool_calls") or [])]
                for t in follows:
                    out += "<|tool_response>response:x{" + t["content"] + "}<tool_response|>"
                if m.get("content"):
                    out += m["content"]
                if m.get("tool_calls") and not follows:
                    out += "<|tool_response>"
                    last_type = "tool_call"
                elif follows and not m.get("content"):
                    last_type = "tool_response"
                else:
                    out += "<turn|>\n"
                    last_type = None
            else:
                out += m["content"] + "<turn|>\n"
                last_type = None
        if add_generation_prompt and last_type is None:
            out += "<|turn>model\n" + ("" if enable_thinking else "<|channel>thought\n<channel|>")
        return out

    def __call__(self, text, add_special_tokens=False):
        pieces, i = [], 0
        for mt in SPECIAL.finditer(text):
            pieces += list(text[i:mt.start()]) + [mt.group()]
            i = mt.end()
        pieces += list(text[i:])
        return {"input_ids": [self.vocab.setdefault(p, len(self.vocab)) for p in pieces]}

    def decode(self, ids):
        inv = {v: k for k, v in self.vocab.items()}
        return "".join(inv[i] for i in ids)


ROOT_SYS = "You are an autonomous senior Python engineer working inside a sandboxed checkout."
ANA_SYS = "You are `code_analyzer`, a read-only code navigation specialist."
PS_A = "Add `ne` validator to attrs. " * 20
PS_B = "Fix jinja whitespace bug. " * 20


def call(t, sys_txt, msgs, reasoning, tool_calls=None, content=None, finish="tool_calls"):
    m = {"role": "assistant", "content": content, "reasoning": reasoning,
         "tool_calls": [{"id": f"call_{k}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for k, (n, a) in enumerate(tool_calls or [])]}
    return {"t": t, "dt": 1.0, "status": 200,
            "request": {"model": "g", "messages": [{"role": "system", "content": sys_txt}] + msgs, "tools": [], "chat_template_kwargs": {"enable_thinking": True}},
            "response": {"choices": [{"index": 0, "message": m, "finish_reason": finish}]}}


def user(ps, repo):
    return {"role": "user", "content": f"You are evaluating a software engineering task for repository {repo}.\n\nProblem Statement:\n{ps}\n"}


@pytest.fixture
def world(tmp_path: Path):
    cap = tmp_path / "capture"
    cap.mkdir()
    (tmp_path / "shards").mkdir()
    (tmp_path / "shards" / "s0.txt").write_text("attrs_1\njinja_2\n")
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps({"instance_id": "attrs_1", "repo": "python-attrs/attrs", "problem_statement": PS_A}) + "\n"
                     + json.dumps({"instance_id": "jinja_2", "repo": "pallets/jinja", "problem_statement": PS_B}) + "\n")
    rd = tmp_path / "px" / "px_test_s1" / "s0"
    (rd / "patches").mkdir(parents=True)
    (rd / "task_results.jsonl").write_text(json.dumps({"instance_id": "attrs_1", "resolved": True}) + "\n"
                                           + json.dumps({"instance_id": "jinja_2", "resolved": False}) + "\n")
    (rd / "patches" / "attrs_1.patch").write_text("--- a/src/attr/validators.py\n+++ b/src/attr/validators.py\n@@ -1 +1 @@\n-x\n+y\n")
    (cap / "100_0.items.jsonl").write_text(json.dumps({"t": 1000, "item": "01_s0_px_test_s1", "run": "px_test_s1"}) + "\n")
    tc1 = [("code_analyzer", {"request": "find where ne goes"})]
    hist = [user(PS_A, "python-attrs/attrs"),
            {"role": "assistant", "content": None, "reasoning_content": "root thought 1",
             "tool_calls": [{"id": "call_0", "type": "function", "function": {"name": "code_analyzer", "arguments": json.dumps(tc1[0][1])}}]},
            {"role": "tool", "tool_call_id": "call_0", "content": "validators.py:493"}]
    lines = [
        call(1001.0, ROOT_SYS, [user(PS_A, "python-attrs/attrs")], "root thought 1", tc1),
        call(1002.0, ANA_SYS, [{"role": "user", "content": "find where ne goes"}], "ana thought", [("read_file", {"filepath": "src/attr/validators.py"})]),
        call(1003.0, ROOT_SYS, hist, "root thought 2", [("submit_patch", {})]),
        call(1004.0, ROOT_SYS, [user(PS_B, "pallets/jinja")], "jinja thought", [("submit_patch", {})]),
    ]
    (cap / "100_0.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines))
    args = argparse.Namespace(capture=str(cap), out=str(tmp_path / "out.jsonl"), max_tokens=32768, tasks_files=[str(tasks)],
                              shards_dir=str(tmp_path / "shards"), results_px=str(tmp_path / "px"), analyzer_marker="code_analyzer",
                              loop_policy="drop", max_per_task=2, no_inject_reasoning=False, strict=True, stats_json=None)
    return args, cap


def test_capture_pipeline(world):
    args, cap = world
    stats = bd.build_capture(args, StubTok())
    assert stats["root_traj_total"] == 2 and stats["root_traj_kept"] == 1 and stats["drop_unresolved"] == 1
    assert stats["analyzer_traj_kept"] == 1 and stats["sequences"] == 2 and stats.get("token_prefix_break", 0) == 0 and stats.get("render_prefix_fail", 0) == 0
    recs = [json.loads(l) for l in open(args.out)]
    tok = StubTok()
    bd.build_capture(args, tok)  # re-run with the tokenizer we decode with
    recs = [json.loads(l) for l in open(args.out)]
    root = next(r for r in recs if r["agent"] == "root")
    ana = next(r for r in recs if r["agent"] == "analyzer")
    for r in recs:
        assert set(r) >= {"run", "instance_id", "segment", "input_ids", "loss_mask"} and len(r["input_ids"]) == len(r["loss_mask"])
        assert r["instance_id"] == "attrs_1" and r["repo"] == "attrs" and r["fold"] == "F4"
    text = tok.decode(root["input_ids"])
    trained = tok.decode([i for i, m in zip(root["input_ids"], root["loss_mask"]) if m])
    assert text.startswith("<bos><|turn>system\n<|think|>\n")
    assert "<|channel>thought\nroot thought 1\n<channel|><|tool_call>call:code_analyzer" in trained
    assert "<|channel>thought\nroot thought 2\n<channel|><|tool_call>call:submit_patch{}<tool_call|><|tool_response>" in trained
    assert "Problem Statement" not in trained and "validators.py:493" not in trained  # user + tool results never trained
    assert root["n_calls"] == 2 and root["segment"] == 0
    assert "<|channel>thought\nana thought\n<channel|><|tool_call>call:read_file" in tok.decode([i for i, m in zip(ana["input_ids"], ana["loss_mask"]) if m])


def test_strict_validation_fails_on_unassignable_call(world):
    args, cap = world
    stray = call(1005.0, ROOT_SYS, [user("Totally different statement " * 20, "x/y")], "t", [("submit_patch", {})])
    with open(cap / "100_0.jsonl", "a") as f:
        f.write(json.dumps(stray) + "\n")
    with pytest.raises(SystemExit):
        bd.build_capture(args, StubTok())
    args.strict = False
    assert bd.build_capture(args, StubTok())["sequences"] == 2


def test_d5_helpers():
    assert bd.repo_of_iid("ml_collections_12") == "ml_collections" and bd.repo_of_iid("requests_oauthlib_1") == "requests_oauthlib"
    assert bd.TEST_CFG_RE.search("tests/test_x.py") and bd.TEST_CFG_RE.search("conftest.py") and not bd.TEST_CFG_RE.search("src/attr/validators.py")
    c = lambda n, a: call(0, ROOT_SYS, [], "r", [(n, a)])  # noqa: E731
    assert bd.loop_turns([c("edit_file", {"a": 1})] * 4 + [c("read_file", {})]) == {1, 2, 3}
    assert bd.loop_turns([c("edit_file", {"a": 1})] * 3) == set()
    assert bd.malformed(call(0, ROOT_SYS, [], "r", None, content="call:edit_file{...", finish="stop"))
    assert bd.malformed(call(0, ROOT_SYS, [], "r", [("x", {})], finish="length"))
