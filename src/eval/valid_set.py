"""Local valid-task set = gold patch resolves AND empty patch fails (standard SWE-bench validation).

Usage: .venv/bin/python -m src.eval.valid_set  -> data/derived/valid_tasks.txt + per-repo table
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(mode: str, name: str = "") -> dict[str, bool]:
    out = {}
    for line in open(ROOT / "results" / f"verify_{name}{mode}" / "verify.jsonl"):
        r = json.loads(line)
        out[r["instance_id"]] = r["resolved"]
    return out


def main() -> None:
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    gold, empty = load("gold", name), load("empty", name)
    valid = sorted(i for i in gold if gold[i] and not empty.get(i, True))
    leak = sorted(i for i in empty if empty[i])
    (ROOT / "data" / "derived").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "derived" / f"{name}valid_tasks.txt").write_text("\n".join(valid) + "\n")
    repo = lambda i: i.split("_")[1] if i.startswith("mined_") else i.rsplit("_", 1)[0]  # noqa: E731
    tot, ok = Counter(map(repo, gold)), Counter(map(repo, valid))
    print(f"valid: {len(valid)}/{len(gold)}  (empty-patch passes: {leak})")
    for r in sorted(tot, key=lambda r: -tot[r]):
        print(f"  {r:10} {ok[r]:3d}/{tot[r]}")


if __name__ == "__main__":
    main()
