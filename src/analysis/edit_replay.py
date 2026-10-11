"""Edit-call replay micro-benchmark (Step 1/2 of the 2026-10-11 program).

Replays the exact LLM requests where the thinking-off root agent was about to emit `edit_file` (captured on the Kaggle L4
scorer stack), under prompt/sampling variants, and measures how often the edit call comes out malformed (old_string
swallowed: the model writes escaped "\\n" and closes the string with a backtick, ADK rejects the call).

  build:  .venv/bin/python -m src.analysis.edit_replay build --out results/edit_replay/set.jsonl
  run:    .venv/bin/python -m src.analysis.edit_replay run --set results/edit_replay/set.jsonl --api http://127.0.0.1:8100/v1 \
              --variant v0 --system submissions/c9e_analyzercap/prompts/system.md --n 2 --out results/edit_replay/v0.jsonl
  report: .venv/bin/python -m src.analysis.edit_replay report results/edit_replay/*.jsonl
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import json
import random
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ["results/kaggle/c9ae-t30s/results/c9ae-t30s/capture.jsonl"]
ROOT_MARK = "You are an autonomous senior Python engineer"
REJECT_MARK = "mandatory input parameters are not present"


def edit_calls(resp: dict) -> list[dict]:
    out = []
    for ch in (resp.get("choices") or [])[:1]:
        for tc in (ch.get("message") or {}).get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name") == "edit_file":
                try:
                    out.append(json.loads(fn.get("arguments") or "{}"))
                except json.JSONDecodeError:
                    out.append({"__unparsed__": fn.get("arguments")})
    return out


def classify(resp: dict) -> str:
    ch = (resp.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    tcs = msg.get("tool_calls") or []
    if not tcs:
        return "text"
    eds = edit_calls(resp)
    if not eds:
        return "other_tool:" + ((tcs[0].get("function") or {}).get("name") or "?")
    a = eds[0]
    if "__unparsed__" in a:
        return "edit_unparsed"
    if "old_string" not in a or "new_string" not in a:
        return "edit_BAD"
    return "edit_ok_escaped" if "\\n" in a["new_string"] and "\n" not in a["new_string"] else "edit_ok"


def build(a) -> None:
    rows = []
    for cap in CAPTURES:
        for line in open(ROOT / cap):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            req, resp = e.get("request") or {}, e.get("response") or {}
            msgs = req.get("messages") or []
            if not msgs or ROOT_MARK not in str(msgs[0].get("content", ""))[:200]:
                continue
            if not edit_calls(resp):
                continue
            recent = json.dumps(msgs[-4:])
            rows.append({"after_reject": REJECT_MARK in recent, "orig": classify(resp), "request": req})
    rng = random.Random(0)
    first = [r for r in rows if not r["after_reject"]]
    after = [r for r in rows if r["after_reject"]]
    rng.shuffle(first)
    rng.shuffle(after)
    sel = first[: a.n_first] + after[: a.n_after]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w") as f:
        for i, r in enumerate(sel):
            r["id"] = i
            f.write(json.dumps(r) + "\n")
    print(json.dumps({"candidates": len(rows), "first": len(first), "after_reject": len(after), "selected": len(sel),
                      "orig_first": Counter(r["orig"] for r in first), "orig_after": Counter(r["orig"] for r in after)}, indent=1))


def call(api: str, body: dict) -> dict:
    req = urllib.request.Request(api.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def run(a) -> None:
    system = Path(a.system).read_text() if a.system else None
    append = Path(a.append).read_text() if a.append else ""
    rows = [json.loads(l) for l in open(a.set)]
    jobs = []
    for r in rows:
        body = json.loads(json.dumps(r["request"]))
        body.pop("stream", None)
        if system is not None:
            body["messages"][0]["content"] = system
        if append:
            body["messages"][0]["content"] = body["messages"][0]["content"].rstrip() + "\n\n" + append
        if a.temperature is not None:
            body["temperature"] = a.temperature
        body["model"] = a.model or body.get("model")
        for k in range(a.n):
            jobs.append((r, k, body))
    out = open(a.out, "w")

    def one(job):
        r, k, body = job
        try:
            resp = call(a.api, body)
            return {"id": r["id"], "k": k, "after_reject": r["after_reject"], "orig": r["orig"], "variant": a.variant,
                    "cls": classify(resp), "completion_tokens": (resp.get("usage") or {}).get("completion_tokens")}
        except Exception as e:  # noqa: BLE001
            return {"id": r["id"], "k": k, "variant": a.variant, "cls": "error", "err": str(e)[:200],
                    "after_reject": r["after_reject"], "orig": r["orig"]}

    with cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(one, jobs):
            out.write(json.dumps(res) + "\n")
            out.flush()
    out.close()
    report(argparse.Namespace(files=[a.out]))


def report(a) -> None:
    by = {}
    for f in a.files:
        for l in open(f):
            r = json.loads(l)
            by.setdefault(r["variant"], []).append(r)
    print(f"{'variant':16s} {'subset':12s} {'n':>4s} {'BAD%':>6s} {'ok%':>6s} {'esc_ok%':>8s} {'other%':>7s} {'text%':>6s} {'tok':>5s}")
    for v, rs in sorted(by.items()):
        for name, sub in (("first", [r for r in rs if not r["after_reject"]]), ("after_reject", [r for r in rs if r["after_reject"]])):
            if not sub:
                continue
            c = Counter(r["cls"] if not r["cls"].startswith("other_tool") else "other" for r in sub)
            n = len(sub)
            toks = [r["completion_tokens"] for r in sub if r.get("completion_tokens")]
            bad = c["edit_BAD"] + c["edit_unparsed"]
            print(f"{v:16s} {name:12s} {n:4d} {100*bad/n:6.1f} {100*c['edit_ok']/n:6.1f} {100*c['edit_ok_escaped']/n:8.1f} "
                  f"{100*c['other']/n:7.1f} {100*c['text']/n:6.1f} {sum(toks)/max(len(toks),1):5.0f}" + (f"  errors={c['error']}" if c["error"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--out", default="results/edit_replay/set.jsonl")
    b.add_argument("--n-first", type=int, default=120)
    b.add_argument("--n-after", type=int, default=60)
    r = sp.add_parser("run")
    r.add_argument("--set", required=True)
    r.add_argument("--api", required=True)
    r.add_argument("--variant", required=True)
    r.add_argument("--system", default=None, help="replace the root system prompt with this file")
    r.add_argument("--append", default=None, help="append this file to the system prompt")
    r.add_argument("--temperature", type=float, default=None)
    r.add_argument("--model", default=None)
    r.add_argument("--n", type=int, default=2)
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--out", required=True)
    rp = sp.add_parser("report")
    rp.add_argument("files", nargs="+")
    a = ap.parse_args()
    {"build": build, "run": run, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
