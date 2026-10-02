"""Local valid-task set = gold patch resolves AND empty patch fails (standard SWE-bench validation).

Usage: .venv/bin/python -m src.eval.valid_set  -> data/derived/valid_tasks.txt + per-repo table
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(mode: str) -> dict[str, bool]:
    out = {}
    for line in open(ROOT / "results" / f"verify_{mode}" / "verify.jsonl"):
        r = json.loads(line)
        out[r["instance_id"]] = r["resolved"]
    return out


def main() -> None:
    gold, empty = load("gold"), load("empty")
    valid = sorted(i for i in gold if gold[i] and not empty.get(i, True))
    leak = sorted(i for i in empty if empty[i])
    (ROOT / "data" / "derived").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "derived" / "valid_tasks.txt").write_text("\n".join(valid) + "\n")
    repo = lambda i: i.rsplit("_", 1)[0]  # noqa: E731
    tot, ok = Counter(map(repo, gold)), Counter(map(repo, valid))
    print(f"valid: {len(valid)}/{len(gold)}  (empty-patch passes: {leak})")
    for r in sorted(tot, key=lambda r: -tot[r]):
        print(f"  {r:10} {ok[r]:3d}/{tot[r]}")


if __name__ == "__main__":
    main()
