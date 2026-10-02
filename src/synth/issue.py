"""B5 step 2: have Gemma write a user-facing issue for each injected bug (resumable).

The model sees the original and mutated internal function but is asked to write the issue as a
library user would: public-API repro, expected vs actual, ~40% with a traceback, never naming the
internal function/file. A later filter calibrates name-mention rate against real tasks.
Usage: .venv/bin/python -m src.synth.issue [--api http://127.0.0.1:8011/v1] [--limit N] [--workers 1]
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.dataio.loaders import DATA

IN = DATA / "derived" / "synth_mutations.jsonl"
OUT = DATA / "derived" / "synth_issues.jsonl"
PROMPT = """You are a developer who uses the Python library `{pkg}`. After upgrading, you hit a bug. For context only, here is the library-internal function before and after the faulty change (as a user you never read this code):

--- before ---
{orig}
--- after ---
{new}

Write a GitHub issue (a one-line title, then a body of 80-200 words) describing what you observed while using the library's public API:
- a minimal reproduction snippet that uses only public, documented API of `{pkg}` (not the internal function),
- the expected behaviour and the actual behaviour.
{tb}
Strict rules: do not mention the internal function name `{short}`, its class, or any file path; do not describe or guess the code change; no "Fix:" section. Output only the issue in Markdown."""
TB_YES = "If the bug would plausibly make your code raise an exception, include a short traceback (last 3-6 lines)."
TB_NO = "Describe the behaviour only; do not include a traceback."


def ask(api: str, prompt: str) -> str:
    body = {"model": "gemma-4-31b-it-qat-w4a16-ct", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 450, "temperature": 0.7, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(api + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"] or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8011/v1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(IN)]
    done = {json.loads(l)["instance_id"] for l in open(OUT)} if OUT.exists() else set()
    todo = [r for r in rows if r["instance_id"] not in done]
    random.Random(0).shuffle(todo)  # interleave packages so partial runs stay diverse
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(done)} done, {len(todo)} to go", flush=True)

    def work(r):
        rng = random.Random(r["instance_id"])
        with_tb = rng.random() < 0.4
        short = r["target_nodes"][0].rsplit(".", 1)[-1]
        text = ask(a.api, PROMPT.format(pkg=r["package"], orig=r["original"][:4000], new=r["mutated"][:4000],
                                        tb=TB_YES if with_tb else TB_NO, short=short))
        return {**r, "issue": text.strip(), "with_traceback_requested": with_tb}

    with ThreadPoolExecutor(a.workers) as ex, open(OUT, "a") as f:
        for i, res in enumerate(ex.map(work, todo)):
            f.write(json.dumps(res) + "\n")
            f.flush()
            if i % 25 == 0:
                print(f"{i + 1}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
