"""Manual root-cause labels for every failing (task, config) run, from side-by-side trajectory reading.

Codes (primary cause = the first thing that, if it had gone right, would most plausibly have flipped the run):
  SPEC  hidden tests need a name/message/API not inferable from the issue text (or issue text empty)
  ENV   evaluation environment prevents any agent patch from passing (tests import a stale installed package)
  MALF  tool-call malformation (missing old_string via backtick, broken keys, over-escaped strings) or
        degenerate identical-call repetition loop
  TIME  correct (or near-correct) diagnosis reached but time / call budget ran out before a working edit
  UND   wrong hypothesis about semantics (incl. non-reproducing repro that convinced the agent "no bug")
  LOC   never found / never edited the right code
  API   inferable API/name mismatch or wrong Python usage (e.g. `Json in metadata`, circular import)
  FIXC  right idea, right place, but incomplete (missed sibling path / second hunk)
  HYG   test-file edit made the hidden test_patch fail to apply (source fix was otherwise correct)

Usage: .venv/bin/python -m src.analysis.forensics.labels   (prints tallies; joins with trajectory_table.csv)
"""

from __future__ import annotations

import csv
from collections import Counter

from src.analysis.forensics.extract import ROOT

L: dict[tuple[str, str], str] = {}


def _set(task: str, mapping: dict[str, str]) -> None:
    for cfgs, code in mapping.items():
        for c in cfgs.split():
            L[(task, c)] = code


# ---- stochastic tasks (43 failures) ----
_set("fastapi_13537", {"c5b": "MALF"})
_set("fastapi_14492", {"c1 c2": "HYG"})
_set("rich_2725", {"c3": "UND", "c6a": "MALF"})
_set("rich_3043", {"c1 c2": "HYG", "c5b": "MALF"})
_set("rich_4077", {"c1": "UND", "c3": "LOC", "c4 c5a": "TIME"})
_set("rich_4075", {"c1 c4 c5a": "TIME", "c2": "UND", "c5b c6a": "LOC", "c6b": "MALF"})
_set("fastapi_14419", {"c2 c4 c5b": "UND", "c6a": "TIME", "c6b": "MALF"})
_set("fastapi_14605", {"c1 c4 c6b c5b c6a": "MALF", "c5a": "API"})
_set("fastapi_14616", {"c1 c3 c5a": "API", "c6b": "TIME", "c2 c5b": "UND"})
_set("fastapi_15589", {"c4 c6b": "TIME", "c5a": "FIXC", "c2 c3 c5b c6a": "UND"})

# ---- never-solved tasks (128 failures) ----
ALL = "c1 c2 c3 c4 c5a c5b c6a c6b"
_set("fastapi_15661", {ALL: "SPEC"})
_set("rich_4076", {ALL: "SPEC"})
_set("requests_7309", {ALL: "ENV"})
_set("fastapi_14258", {"c1 c2 c3 c4 c5a c5b c6b": "SPEC", "c6a": "SPEC"})  # c6a also a 96-call MALF loop
_set("fastapi_14306", {ALL: "SPEC"})  # 2/7 hidden tests need `endpoint_ctx=` kwarg + literal text
_set("fastapi_14448", {"c2 c3 c4 c5a": "FIXC", "c1": "TIME", "c6a": "LOC", "c6b": "MALF", "c5b": "UND"})
_set("fastapi_14430", {ALL: "LOC"})
_set("fastapi_14246", {"c2 c3 c6b": "TIME", "c4 c5a c5b c6a": "UND", "c1": "MALF"})
_set("httpx_3672", {"c1 c3 c5a c5b c6a c6b": "ENV", "c2": "TIME", "c4": "FIXC"})  # 6 patches pass with PYTHONPATH=src
_set("fastapi_13713", {ALL: "SPEC"})  # needs kwarg `openapi_external_docs`; issue says `external_docs`
_set("fastapi_14953", {ALL: "SPEC"})  # hidden tests import an un-mentioned new docs_src module
_set("fastapi_15800", {ALL: "SPEC"})  # ~650-line feature, empty PR template
_set("fastapi_14371", {"c1 c5a": "FIXC", "c2 c6b": "UND", "c3 c4": "TIME", "c5b": "UND", "c6a": "MALF"})
_set("rich_3772", {"c2 c3 c5a c6b c5b c6a": "UND", "c1 c4": "TIME"})
_set("rich_3506", {"c1 c2 c3 c4 c5a c6a c6b": "TIME", "c5b": "MALF"})
_set("rich_3521", {"c1 c2 c3 c4 c5a c5b c6b": "TIME", "c6a": "FIXC"})

# Secondary contributing causes worth counting separately (run-level, from trajectory reading)
SECONDARY_MALF = {("fastapi_14258", "c6a"), ("fastapi_14306", "c3"), ("fastapi_14306", "c6b"), ("fastapi_13713", "c2"),
                  ("fastapi_13713", "c3"), ("fastapi_13713", "c4"), ("fastapi_13713", "c5a"), ("fastapi_13713", "c6a"),
                  ("fastapi_14953", "c6a"), ("httpx_3672", "c3"), ("fastapi_14605", "c5a"), ("fastapi_14419", "c6a"),
                  ("fastapi_14371", "c6a"), ("rich_2725", "c6a")}
SECONDARY_HYG = {("requests_7309", c) for c in ("c1", "c2", "c3", "c6a")} | {("fastapi_14953", "c2"), ("fastapi_14953", "c5b")}


def main() -> None:
    rows = list(csv.DictReader(open(ROOT / "reports" / "council" / "trajectory_table.csv")))
    fails = [r for r in rows if r["resolved"] == "0"]
    missing = [(r["instance_id"], r["config"]) for r in fails if (r["instance_id"], r["config"]) not in L]
    assert not missing, missing
    for name, sub in [("all failures", fails), ("stochastic", [r for r in fails if r["task_class"] == "stochastic"]),
                      ("never", [r for r in fails if r["task_class"] == "never"])]:
        c = Counter(L[(r["instance_id"], r["config"])] for r in sub)
        print(f"{name} (n={len(sub)}): " + ", ".join(f"{k}={v} ({v / len(sub):.0%})" for k, v in c.most_common()))
    print("by config:")
    for cfg in ["c1", "c2", "c3", "c4", "c5a", "c5b", "c6a", "c6b"]:
        c = Counter(L[(r["instance_id"], r["config"])] for r in fails if r["config"] == cfg)
        print(f"  {cfg}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    print(f"secondary MALF involvement: {len(SECONDARY_MALF)} runs; secondary HYG: {len(SECONDARY_HYG)} runs")


if __name__ == "__main__":
    main()
