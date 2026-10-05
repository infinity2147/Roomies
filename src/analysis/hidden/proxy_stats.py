"""Compare task-shape statistics: public valid set vs proxy valid sets.

Usage: .venv/bin/python -m src.analysis.hidden.proxy_stats
Writes data/derived/proxy/valid_tasks.jsonl (union of valid proxy tasks, harness schema) and prints
a per-repo table + shape comparison (source files, churn, statement length, created_at).
"""

from __future__ import annotations

import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "data" / "derived"


def load_verify(name: str) -> dict[str, bool]:
    p = ROOT / "results" / f"verify_{name}" / "verify.jsonl"
    return {json.loads(line)["instance_id"]: json.loads(line)["resolved"] for line in open(p)} if p.exists() else {}


def shape(t: dict) -> dict:
    files = re.findall(r"^\+\+\+ b/(\S+)", t["patch"], re.M)
    churn = sum(1 for ln in t["patch"].splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---"))
    return {"files": len(files), "churn": churn, "stmt": len(t["problem_statement"]), "year": t["created_at"][:4]}


def summarize(name: str, ts: list[dict]) -> str:
    sh = [shape(t) for t in ts]
    q = lambda xs: (st.median(xs), sorted(xs)[int(0.9 * (len(xs) - 1))])  # noqa: E731
    f, c, s = q([x["files"] for x in sh]), q([x["churn"] for x in sh]), q([x["stmt"] for x in sh])
    one = sum(x["files"] == 1 for x in sh) / len(sh)
    yrs = Counter(x["year"] for x in sh)
    return (f"| {name} | {len(ts)} | {one:.0%} | {f[0]:.0f} / {f[1]:.0f} | {c[0]:.0f} / {c[1]:.0f} | "
            f"{s[0]:.0f} / {s[1]:.0f} | {dict(sorted(yrs.items()))} |")


def main() -> None:
    public = [json.loads(line) for line in open(ROOT / "data" / "tasks.jsonl")]
    pub_valid = set((D / "valid_tasks.txt").read_text().split())
    rows = []
    for tasks_file, vname in [("tasks.jsonl", "proxyw2_"), ("tasks_google.jsonl", "proxyg_")]:
        p = D / "proxy" / tasks_file
        if not p.exists():
            continue
        gold, empty = load_verify(vname + "gold"), load_verify(vname + "empty")
        for line in open(p):
            t = json.loads(line)
            t["_gold"], t["_empty"] = gold.get(t["instance_id"]), empty.get(t["instance_id"])
            t["_valid"] = bool(t["_gold"]) and t["_empty"] is False
            t["_group"] = "google-cl" if vname == "proxyg_" else "github-pr"
            rows.append(t)
    print("| repo | group | candidates | gold pass | empty pass (leak) | valid |\n|---|---|---|---|---|---|")
    by = {}
    for t in rows:
        by.setdefault((t["repo"], t["_group"]), []).append(t)
    for (repo, g), ts in sorted(by.items(), key=lambda kv: -sum(t["_valid"] for t in kv[1])):
        print(f"| {repo} | {g} | {len(ts)} | {sum(bool(t['_gold']) for t in ts)} | "
              f"{sum(bool(t['_empty']) for t in ts)} | {sum(t['_valid'] for t in ts)} |")
    valid = [t for t in rows if t["_valid"]]
    print(f"\nvalid total: {len(valid)} ({Counter(t['_group'] for t in valid)})\n")
    keys = ["instance_id", "repo", "base_commit", "patch", "test_patch", "problem_statement", "hints_text", "created_at"]
    with open(D / "proxy" / "valid_tasks.jsonl", "w") as f:
        for t in valid:
            f.write(json.dumps({k: t[k] for k in keys}) + "\n")
    (D / "proxy" / "valid_tasks.txt").write_text("\n".join(t["instance_id"] for t in valid) + "\n")
    # proxy60: fast-iteration subset, <= PER_REPO random valid tasks per repo (seed 0), balanced across repos
    import random
    rng, per_repo, sub = random.Random(0), 5, []
    for repo in sorted({t["repo"] for t in valid}):
        rs = [t for t in valid if t["repo"] == repo]
        sub += rng.sample(rs, min(per_repo, len(rs)))
    with open(D / "proxy" / "proxy60_tasks.jsonl", "w") as f:
        for t in sub:
            f.write(json.dumps({k: t[k] for k in keys}) + "\n")
    print(f"proxy60 subset: {len(sub)} tasks over {len({t['repo'] for t in sub})} repos")
    print("| set | n | single-file | src files med/p90 | churn med/p90 | statement chars med/p90 | years |")
    print("|---|---|---|---|---|---|---|")
    print(summarize("public valid", [t for t in public if t["instance_id"] in pub_valid]))
    for g in ("github-pr", "google-cl"):
        sub = [t for t in valid if t["_group"] == g]
        if sub:
            print(summarize(f"proxy valid ({g})", sub))


if __name__ == "__main__":
    main()
