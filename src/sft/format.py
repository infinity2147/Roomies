"""E0: render harness trajectories (ATIF traces) into SFT examples in the exact request format.

The wire format (learned from src/sft/capture_proxy.py captures of the frozen scaffold):
  system, user (harness prompt), then per LLM call: assistant {tool_calls[{id, type, function{name,
  arguments: JSON string}}]} followed by one `tool` message per call {tool_call_id, content: JSON str}.
Tools schema = the captured `tools` list for the scaffold (stored in src/sft/tools_<scaffold>.json).

Rendering uses the model's own chat template (tokenizer.apply_chat_template with tools), and the
loss mask covers exactly the assistant segments (tool calls + any text), never system/user/tool.

Usage:
  .venv-harness/bin/python -m src.sft.format --save-tools results/capture.jsonl --scaffold c6a
  .venv-harness/bin/python -m src.sft.format --roundtrip results/capture.jsonl \
        --trace results/capture_run/traces/trace_requests_7433.json --scaffold c6a
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "external" / "models" / "gemma-4-31b-it-qat-w4a16-ct"


def trace_to_messages(trace: dict) -> list[dict]:
    """ATIF trace -> OpenAI chat messages in the harness wire format."""
    msgs: list[dict] = []
    n = 0
    for s in trace["steps"]:
        src = s.get("source")
        if src == "system":
            msgs.append({"role": "system", "content": s["message"]})
        elif src == "user":
            msgs.append({"role": "user", "content": s["message"]})
        elif src == "agent":
            calls = s.get("tool_calls") or []
            text = s.get("message")
            if not calls:
                if text:
                    msgs.append({"role": "assistant", "content": text})
                continue
            tcs = []
            for c in calls:
                n += 1
                tcs.append({"type": "function", "id": f"call_{n}",
                            "function": {"name": c["function_name"], "arguments": json.dumps(c.get("arguments") or {})}})
            m = {"role": "assistant", "tool_calls": tcs}
            if text:
                m["content"] = text
            msgs.append(m)
            obs = s.get("observation") or {}
            results = obs.get("results") if isinstance(obs, dict) and "results" in obs else [obs]
            for tc, res in zip(tcs, results):
                content = res.get("content") if isinstance(res, dict) else res
                msgs.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": content if isinstance(content, str) else json.dumps(content)})
    return msgs


def normalize(msgs: list[dict]) -> list[dict]:
    """Strip call ids so two message lists can be compared structurally."""
    out = []
    for m in msgs:
        m = {k: v for k, v in m.items() if k != "tool_call_id"}
        if "tool_calls" in m:
            m["tool_calls"] = [{"name": t["function"]["name"], "arguments": json.loads(t["function"]["arguments"])}
                               for t in m["tool_calls"]]
        if m.get("content") in (None, ""):
            m.pop("content", None)
        out.append(m)
    return out


def to_template_msgs(msgs: list[dict], system: str | None = None) -> list[dict]:
    """vLLM's _postprocess_messages: tool-call arguments become dicts before templating.
    Optionally replace the system prompt with the scaffold's full captured one (ADK appends
    agent identity + skill instructions to our instruction)."""
    out = []
    for m in msgs:
        m = json.loads(json.dumps(m))
        if m["role"] == "system" and system and system.startswith(m["content"]):
            m["content"] = system
        for tc in m.get("tool_calls") or []:
            a = tc["function"].get("arguments")
            tc["function"]["arguments"] = json.loads(a) if isinstance(a, str) and a else (a or {})
        out.append(m)
    return out


EMPTY_THOUGHT = "<|channel>thought\n<channel|>"
MODEL_OPEN = "<|turn>model\n"


def render(msgs: list[dict], tools: list[dict], tokenizer, system: str | None = None) -> tuple[list[int], list[int]]:
    """One training sequence per trajectory: full history render (as vLLM renders it), with the empty
    thought channel inserted where each model turn opens (that is what the model saw when generating
    with thinking off), loss mask = 1 on tool-call spans + the stop token after them
    (<|tool_response>) and on final text + <turn|>."""
    tm = to_template_msgs(msgs, system)
    text = tokenizer.apply_chat_template(tm, tokenize=False, tools=tools, enable_thinking=False)
    # History rendering (what vLLM feeds the model from turn 2 on) has no empty thought channel; only
    # the very first generation of a model turn sees `<|turn>model\n<|channel>thought\n<channel|>`.
    # We keep the history format so every continuation turn is an exact prefix.
    spans = []
    i = 0
    while True:
        a = text.find("<|tool_call>", i)
        if a < 0:
            break
        b = text.find("<tool_call|>", a) + len("<tool_call|>")
        if text.startswith("<|tool_response>", b):
            b += len("<|tool_response>")
        spans.append((a, b))
        i = b
    # final assistant text answers: from after the empty thought to <turn|>, when no tool call inside
    j = 0
    while True:
        a = text.find(MODEL_OPEN, j)
        if a < 0:
            break
        a += len(MODEL_OPEN)
        if text.startswith(EMPTY_THOUGHT, a):
            a += len(EMPTY_THOUGHT)
        b = text.find("<turn|>", a)
        if b > a and "<|tool_call>" not in text[a:b] and "<|tool_response>" not in text[a:b]:
            spans.append((a, b + len("<turn|>")))
        j = a
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = enc["input_ids"]
    mask = [int(any(s <= st < e for s, e in spans)) for st, _ in enc["offset_mapping"]]
    return ids, mask


def turn_prompts(msgs: list[dict], tools: list[dict], tokenizer, system: str | None = None) -> list[list[int]]:
    """What vLLM would feed the model at each assistant turn (generation prompt included)."""
    tm = to_template_msgs(msgs, system)
    out = []
    for i, m in enumerate(tm):
        if m["role"] == "assistant":
            p = tokenizer.apply_chat_template(tm[:i], add_generation_prompt=True, tokenize=False, tools=tools, enable_thinking=False)
            out.append(tokenizer(p, add_special_tokens=False)["input_ids"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-tools")
    ap.add_argument("--roundtrip")
    ap.add_argument("--trace")
    ap.add_argument("--scaffold", default="c6a")
    a = ap.parse_args()
    tools_path = ROOT / "src" / "sft" / f"tools_{a.scaffold}.json"
    if a.save_tools:
        recs = [json.loads(l) for l in open(a.save_tools)]
        tools = recs[-1]["request"]["tools"]
        assert all(r["request"]["tools"] == tools for r in recs), "tools differ across requests"
        tools_path.write_text(json.dumps(tools, indent=1))
        sys_prompt = recs[-1]["request"]["messages"][0]["content"]
        (ROOT / "src" / "sft" / f"system_{a.scaffold}.md").write_text(sys_prompt)
        print("saved", tools_path, len(tools), "tools; params:", {k: v for k, v in recs[-1]["request"].items() if k not in ("messages", "tools")})
    if a.roundtrip:
        recs = [json.loads(l) for l in open(a.roundtrip)]
        last = max(recs, key=lambda r: len(r["request"]["messages"]))
        req_msgs = last["request"]["messages"]
        resp = last["response"]["choices"][0]["message"]
        resp_msg = {"role": "assistant", "tool_calls": resp.get("tool_calls")} if resp.get("tool_calls") else {"role": "assistant", "content": resp.get("content")}
        captured = normalize(req_msgs + [resp_msg])
        mine = normalize(trace_to_messages(json.load(open(a.trace))))
        # 1) structural equality of our trace conversion vs. what the harness actually sent
        n = min(len(captured), len(mine))
        diffs = [i for i in range(n) if captured[i] != mine[i]]
        print(f"messages captured={len(captured)} converted={len(mine)} first_diffs={diffs[:5]}")
        for i in diffs[:2]:
            print("  CAPTURED:", json.dumps(captured[i])[:300]); print("  MINE    :", json.dumps(mine[i])[:300])
        # 2) render + loss mask; every assistant turn's vLLM prompt must be an exact token prefix
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL)
        tools = json.loads(tools_path.read_text())
        system = (ROOT / "src" / "sft" / f"system_{a.scaffold}.md").read_text()
        msgs = trace_to_messages(json.load(open(a.trace)))
        ids, mask = render(msgs, tools, tok, system)
        prompts = turn_prompts(msgs, tools, tok, system)
        exact = sum(ids[: len(p)] == p for p in prompts)
        # the first masked token after each prompt must be where generation starts
        starts_ok = sum(len(p) < len(ids) and mask[len(p)] == 1 for p in prompts)
        print(f"rendered tokens={len(ids)} trainable={sum(mask)} ({sum(mask) / len(ids):.1%})")
        print(f"vLLM prompt is exact prefix at {exact}/{len(prompts)} assistant turns; generation starts on a trained token at {starts_ok}/{len(prompts)}")
        from vllm.tool_parsers.gemma4_tool_parser import Gemma4ToolParser
        parser = Gemma4ToolParser(tok)
        want = [m for m in msgs if m["role"] == "assistant"]
        ok = 0
        for p, w in zip(prompts, want):
            k = len(p)
            while k < len(mask) and mask[k]:
                k += 1
            text = tok.decode(ids[len(p):k], skip_special_tokens=False)
            info = parser.extract_tool_calls(text, request=None)
            got = [{"name": c.function.name, "arguments": json.loads(c.function.arguments)} for c in info.tool_calls]
            exp = [{"name": c["function"]["name"], "arguments": json.loads(c["function"]["arguments"])} for c in w.get("tool_calls", [])]
            ok += got == exp
        print(f"tool-call round trip via vLLM gemma4 parser: {ok}/{len(want)} assistant turns match")


if __name__ == "__main__":
    main()
