"""Step 2: file- vs node-level localization and its link to end-to-end outcomes on the 30-task Kaggle pilot.

Inputs: cached BM25 per-task results (common.py), results/locate_skill_eval.jsonl (deployed locate.py skill;
c1 and c6a locate.py are byte-identical), and the 8 Kaggle runs' patches/logs.
Usage: .venv/bin/python -m src.analysis.localization.file_vs_node
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import numpy as np
from unidiff import PatchSet

from src.analysis.localization.common import CACHE, compute
from src.dataio.loaders import ROOT, load_tasks
from src.eval.triage import patch_files, tool_usage

RUNS = ["c1", "c2", "c3", "c4", "c5a", "c5b", "c6a", "c6b"]


def main() -> None:
    R = {r["iid"]: r for r in compute()}
    tasks = {t.instance_id: t for t in load_tasks()}
    skill = {r["instance_id"]: r for r in map(json.loads, open(ROOT / "results" / "locate_skill_eval.jsonl"))}
    out = ["## File vs node level\n"]

    # BM25 vs skill on the common task set (has gold node and skill eval row)
    common = [i for i in R if i in skill]
    out.append(f"### Offline: BM25 (graph nodes, issue+hints) vs deployed locate.py (issue[:1500]) on n={len(common)} common tasks\n")
    out.append("| system | file hit@1 | file hit@3 | file hit@5/6 | node hit@1 | node hit@5 |\n|---|---|---|---|---|---|")
    f = lambda k: np.mean([R[i][k] for i in common])
    out.append(f"| BM25 (node ranking -> files) | {f('bm25_file_hit@1'):.3f} | {f('bm25_file_hit@3'):.3f} | {f('bm25_file_hit@5'):.3f} | "
               f"{f('bm25_hit@1'):.3f} | {f('bm25_hit@5'):.3f} |")
    g = lambda k: np.mean([skill[i][k] for i in common])
    out.append(f"| locate.py skill | {g('file_hit1'):.3f} | {g('file_hit3'):.3f} | {g('file_hit6'):.3f} (k=6 files) | "
               f"{g('node_hit1'):.3f} | {g('node_hit5'):.3f} |")
    allsk = list(skill.values())
    out.append(f"\nSkill over all {len(allsk)} tasks with a gold file: file@1 {np.mean([r['file_hit1'] for r in allsk]):.3f}, "
               f"file@3 {np.mean([r['file_hit3'] for r in allsk]):.3f}, file@6 {np.mean([r['file_hit6'] for r in allsk]):.3f}, "
               f"node@5 {np.mean([r['node_hit5'] for r in allsk]):.3f}.")
    # node hit given file hit
    fh = [i for i in common if R[i]["bm25_file_hit@3"] == 1]
    out.append(f"\nConditional: given BM25 puts a gold file in top-3 files ({len(fh)} tasks), BM25 node hit@5 = "
               f"{np.mean([R[i]['bm25_hit@5'] for i in fh]):.3f}; # gold nodes per task median "
               f"{np.median([R[i]['n_gold'] for i in common]):.0f}, files per task median "
               f"{np.median([len(R[i]['target_modules']) for i in common]):.0f}.\n")

    # End-to-end linkage on the 30-task pilot
    per_task = defaultdict(lambda: {"res": 0, "touch": 0, "patched": 0, "n": 0, "locate_calls": 0})
    pair_rows = []
    skill_calls = Counter()
    for run in RUNS:
        rd = ROOT / "results" / "kaggle" / f"{run}_n30" / "results" / f"{run}_n30"
        for r in map(json.loads, open(rd / "task_results.jsonl")):
            iid = r["instance_id"]
            t = tasks[iid]
            gold = [x.path for x in PatchSet(t.patch) if not x.is_added_file] or patch_files(t.patch)
            pf = rd / "patches" / f"{iid}.patch"
            files = [x for x in patch_files(pf.read_text() if pf.exists() else "") if "test" not in x]
            touch = bool(set(files) & set(gold))
            u = tool_usage(rd / "traces" / f"trace_{iid}.json")
            lc = sum(v for k, v in u.items() if k.startswith("skill:locate"))
            skill_calls[run] += lc
            d = per_task[iid]
            d["n"] += 1
            d["res"] += bool(r.get("resolved"))
            d["touch"] += touch
            d["patched"] += bool(files)
            d["locate_calls"] += lc
            pair_rows.append((iid, run, bool(r.get("resolved")), touch, bool(files)))
    n_runs = len(pair_rows)
    patched = [p for p in pair_rows if p[4]]
    out.append(f"### End-to-end (8 Kaggle runs x 30 tasks = {n_runs} task-runs)\n")
    out.append(f"- task-runs with a non-test patch: {len(patched)}; of these the patch touches >=1 gold file: "
               f"{sum(p[3] for p in patched)} ({sum(p[3] for p in patched) / len(patched):.1%}).")
    out.append(f"- P(resolved | touched gold file) = {sum(p[2] for p in patched if p[3])}/{sum(p[3] for p in patched)} = "
               f"{sum(p[2] for p in patched if p[3]) / max(sum(p[3] for p in patched), 1):.3f}; "
               f"P(resolved | patched only non-gold files) = {sum(p[2] for p in patched if not p[3])}/{sum(not p[3] for p in patched)}.")
    out.append(f"- locate.py skill calls per run: {dict(skill_calls)} (total {sum(skill_calls.values())} over {n_runs} task-runs).")
    # correlation of offline localization with outcomes
    rows = []
    for iid, d in per_task.items():
        b = R.get(iid)
        s = skill.get(iid)
        rows.append({"iid": iid, "solve": d["res"] / d["n"], "touch": d["touch"] / d["n"], "patched": d["patched"] / d["n"],
                     "bm25_f1": b["bm25_file_hit@1"] if b else np.nan, "bm25_f3": b["bm25_file_hit@3"] if b else np.nan,
                     "bm25_n5": b["bm25_hit@5"] if b else np.nan, "bm25_mrr": b["bm25_mrr"] if b else np.nan,
                     "sk_f1": s["file_hit1"] if s else np.nan, "sk_f3": s["file_hit3"] if s else np.nan,
                     "sk_n5": s["node_hit5"] if s else np.nan, "n_gold_files": len(b["target_modules"]) if b else np.nan})
    out.append("\nPer-task (n=30) outcome split by offline localization quality (mean over 8 runs):\n")
    out.append("| offline signal | group | n tasks | mean solve rate | mean P(agent touches gold file) |\n|---|---|---|---|---|")
    for key, lbl in [("bm25_f1", "BM25 file hit@1"), ("bm25_f3", "BM25 file hit@3"), ("bm25_n5", "BM25 node hit@5"),
                     ("sk_f1", "skill file hit@1"), ("sk_f3", "skill file hit@3"), ("sk_n5", "skill node hit@5")]:
        for v in (1.0, 0.0):
            S = [r for r in rows if r[key] == v]
            if S:
                out.append(f"| {lbl} | {'hit' if v else 'miss'} | {len(S)} | {np.mean([r['solve'] for r in S]):.3f} | "
                           f"{np.mean([r['touch'] for r in S]):.3f} |")
    valid = [r for r in rows if not np.isnan(r["bm25_mrr"])]
    sp = lambda a, b: float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])
    out.append(f"\nSpearman (n={len(valid)}): solve-rate vs BM25 node MRR {sp([r['solve'] for r in valid], [r['bm25_mrr'] for r in valid]):.2f}; "
               f"touch-rate vs BM25 node MRR {sp([r['touch'] for r in valid], [r['bm25_mrr'] for r in valid]):.2f}; "
               f"solve vs #gold files {sp([r['solve'] for r in valid], [r['n_gold_files'] for r in valid]):.2f}.")
    always_touch = [r for r in rows if r["touch"] >= 0.75]
    out.append(f"\nTasks where the agent touches a gold file in >=6/8 runs: {len(always_touch)}/30; their mean solve rate "
               f"{np.mean([r['solve'] for r in always_touch]):.3f}. Tasks touched in <=2/8 runs: "
               f"{sum(r['touch'] <= 0.25 for r in rows)}/30 (solve rate "
               f"{np.mean([r['solve'] for r in rows if r['touch'] <= 0.25]):.3f}).")
    text = "\n".join(out) + "\n"
    (CACHE.parent / "file_vs_node.md").write_text(text)
    (CACHE.parent / "e2e_per_task.json").write_text(json.dumps(rows, indent=1, default=float))
    print(text)


if __name__ == "__main__":
    main()
