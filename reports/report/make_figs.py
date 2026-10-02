"""Generate figures + a facts.json of numbers for the technical report (reports/report/)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "report" / "figs"
OUT.mkdir(parents=True, exist_ok=True)
facts: dict = {}
plt.rcParams.update({"font.size": 9, "figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False})


def save(name):
    plt.tight_layout()
    plt.savefig(OUT / f"{name}.pdf")
    plt.close()


# ---------------- data audit ----------------
audit = json.load(open(ROOT / "reports" / "data_audit.json"))
by_repo = defaultdict(list)
for r in audit:
    by_repo[r["repo"]].append(r)
facts["audit"] = {k: {"n": len(v), "median_nodes": float(np.median([x.get("nodes", 0) for x in v])),
                      "median_files": float(np.median([x["patch"]["files"] for x in v])),
                      "median_hunks": float(np.median([x["patch"]["hunks"] for x in v])),
                      "median_added": float(np.median([x["patch"]["lines_added"] for x in v])),
                      "median_removed": float(np.median([x["patch"]["lines_removed"] for x in v]))} for k, v in by_repo.items()}
fig, ax = plt.subplots(1, 2, figsize=(7, 2.4))
repos = sorted(by_repo, key=lambda k: -len(by_repo[k]))
ax[0].bar(repos, [len(by_repo[r]) for r in repos], color="#4C72B0")
ax[0].set_title("Tasks per repository")
lines = [x["patch"]["lines_added"] + x["patch"]["lines_removed"] for x in audit]
ax[1].hist(np.log10(np.array(lines) + 1), bins=25, color="#55A868")
ax[1].set_xlabel("log10(changed lines in gold patch + 1)")
ax[1].set_title("Gold patch size")
save("audit")

# ---------------- B1 targets ----------------
tg = [json.loads(l) for l in open(ROOT / "data" / "derived" / "targets.jsonl")]
nt = Counter(min(len(r["target_nodes"]), 6) for r in tg)
facts["b1"] = {"n": len(tg), "ge1": sum(bool(r["target_nodes"]) for r in tg),
               "full": sum(bool(r["target_nodes"]) and not r["unmapped"] for r in tg),
               "dist": {str(k): nt[k] for k in sorted(nt)},
               "unmapped_reasons": dict(Counter(u["reason"] for r in tg for u in r["unmapped"]))}
fig, ax = plt.subplots(figsize=(3.4, 2.3))
ks = sorted(nt)
ax.bar([str(k) if k < 6 else "6+" for k in ks], [nt[k] for k in ks], color="#4C72B0")
ax.set_xlabel("# gold target nodes per task")
ax.set_ylabel("tasks")
save("b1_targets")

# ---------------- seed -> target graph distance ----------------
try:
    from src.retrieval.context import bfs_dist, build_contexts
    from src.retrieval.features import anchor_matches

    dists = []
    for c in build_contexts():
        if not len(c.targets):
            continue
        am = anchor_matches(c)
        if len(am["seeds"]) == 0:
            dists.append(-1)
            continue
        d = bfs_dist(c.gi, list(am["seeds"]), max_hops=5)
        dists.append(int(min(d[c.targets])))
    dc = Counter(dists)
    facts["seed_dist"] = {str(k): dc[k] for k in sorted(dc)}
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    labels = ["no seed"] + [str(k) for k in range(0, 6)] + [">5"]
    vals = [dc[-1]] + [dc[k] for k in range(0, 6)] + [dc[6]]
    ax.bar(labels, vals, color="#C44E52")
    ax.set_xlabel("hops from nearest anchor seed to a gold node")
    ax.set_ylabel("tasks")
    save("seed_dist")
except Exception as e:  # noqa: BLE001
    facts["seed_dist_error"] = str(e)

# ---------------- B2 baselines ----------------
b2 = json.load(open(sorted((ROOT / "experiments").glob("*_b2_baselines/metrics.json"))[-1]))
facts["b2"] = b2["results"]
facts["b2_importance"] = dict(list(b2["feature_importance"].items())[:12])
systems = ["R1_bm25", "R2_embed", "R3_ranker", "R3+G"]
folds = ["ALL", "fastapi", "rich", "requests"]
fig, ax = plt.subplots(figsize=(6.5, 2.4))
w = 0.2
for i, s in enumerate(systems):
    mu = [b2["results"][s]["mean"][f]["mrr"] for f in folds]
    sd = [b2["results"][s]["std"][f]["mrr"] if b2["results"][s]["std"] else 0 for f in folds]
    ax.bar(np.arange(len(folds)) + (i - 1.5) * w, mu, w, yerr=sd, label=s, capsize=2)
ax.set_xticks(range(len(folds)), folds)
ax.set_ylabel("node MRR")
ax.legend(ncol=4, fontsize=7, frameon=False, loc="upper left")
save("b2_mrr")
imp = list(b2["feature_importance"].items())[:12]
fig, ax = plt.subplots(figsize=(3.6, 2.8))
ax.barh([k for k, _ in imp][::-1], [v for _, v in imp][::-1], color="#8172B2")
ax.set_xlabel("share of total gain")
save("b2_importance")

# ---------------- locate skill sweep ----------------
facts["locate"] = {"w0": {"file_hit1": 0.438, "file_hit3": 0.641, "file_hit6": 0.781, "node_hit5": 0.453},
                   "w0.2": {"file_hit1": 0.453, "file_hit3": 0.672, "file_hit6": 0.789, "node_hit5": 0.461},
                   "w0.3": {"file_hit1": 0.461, "file_hit3": 0.672, "file_hit6": 0.766, "node_hit5": 0.461},
                   "w0.5": {"file_hit1": 0.492, "file_hit3": 0.688, "file_hit6": 0.773, "node_hit5": 0.453},
                   "w0.7": {"file_hit1": 0.484, "file_hit3": 0.664, "file_hit6": 0.781, "node_hit5": 0.438}}
fig, ax = plt.subplots(figsize=(3.4, 2.3))
ws = [0, 0.2, 0.3, 0.5, 0.7]
for key, lab in (("file_hit1", "file hit@1"), ("file_hit3", "file hit@3"), ("node_hit5", "node hit@5")):
    ax.plot(ws, [facts["locate"][f"w{w_ if w_ else 0}"][key] for w_ in ws], marker="o", label=lab)
ax.set_xlabel("path-bonus weight $\\lambda_{path}$")
ax.legend(fontsize=7, frameon=False)
save("locate_sweep")

# ---------------- C-series ----------------
runs = ["c1_n30", "c2_n30", "c3_n30", "c4_n30", "c5a_n30", "c5b_n30", "c6a_n30", "c6b_n30"]
cs = {}
solved = Counter()
for r in runs:
    d = ROOT / "results" / "kaggle" / r / "results" / r
    rows = [json.loads(l) for l in open(d / "task_results.jsonl")]
    errs = Counter()
    for x in rows:
        e = x.get("error") or ""
        errs["timeout" if "timeout" in e else "test_patch" if "test_patch" in e else "turns" if "turns" in e else "other" if e else "none"] += 1
        if x["resolved"]:
            solved[x["instance_id"]] += 1
    tri = (ROOT / "reports" / f"triage_{r}.md").read_text()
    m = re.search(r"Buckets: (.*)", tri)
    cs[r] = {"resolved": sum(x["resolved"] for x in rows), "n": len(rows),
             "mean_time": float(np.mean([x["duration_seconds"] for x in rows])),
             "errors": dict(errs), "buckets": m.group(1) if m else ""}
facts["cseries"] = cs
facts["union"] = {"solved_any": len(solved), "counts": dict(solved)}
fig, ax = plt.subplots(1, 2, figsize=(7, 2.5))
names = [r.split("_")[0].upper() for r in runs]
ax[0].bar(names, [cs[r]["resolved"] for r in runs], color="#4C72B0")
ax[0].set_ylabel("resolved / 30")
ax[0].set_ylim(0, 12)
ax[1].bar(names, [cs[r]["mean_time"] for r in runs], color="#DD8452")
ax[1].set_ylabel("mean seconds / task")
for a_ in ax:
    a_.tick_params(axis="x", rotation=45)
save("cseries")
# pass@k curve (unbiased estimator over the 8 configurations treated as samples)
from math import comb  # noqa: E402

n = len(runs)
ids = set()
for r in runs:
    for l in open(ROOT / "results" / "kaggle" / r / "results" / r / "task_results.jsonl"):
        ids.add(json.loads(l)["instance_id"])
pk = []
for k in range(1, n + 1):
    v = np.mean([1 - comb(n - solved[i], k) / comb(n, k) for i in ids])
    pk.append(v)
facts["passk_curve"] = pk
fig, ax = plt.subplots(figsize=(3.4, 2.3))
ax.plot(range(1, n + 1), pk, marker="o")
ax.set_xlabel("k (runs)")
ax.set_ylabel("pass@k on 30 tasks")
ax.set_ylim(0, 0.55)
save("passk")
fig, ax = plt.subplots(figsize=(3.4, 2.3))
hist = Counter(solved[i] for i in ids)
ax.bar(range(0, n + 1), [hist[k] for k in range(0, n + 1)], color="#55A868")
ax.set_xlabel("# of the 8 runs that solved the task")
ax.set_ylabel("tasks")
save("solve_freq")

# ---------------- thinking volume vs time (C4) ----------------
d = ROOT / "results" / "kaggle" / "c4_n30" / "results" / "c4_n30"
res = {json.loads(l)["instance_id"]: json.loads(l) for l in open(d / "task_results.jsonl")}
pts = []
for f in (d / "logs").glob("*.log"):
    t = re.sub(r"\x1b\[[0-9;]*m", "", f.read_text(errors="ignore"))
    th = sum(int(x) for x in re.findall(r"💭 \((\d+) chars\)", t))
    r = res[f.stem]
    pts.append((th / 4, r["duration_seconds"], bool(r.get("error") and "timeout" in r["error"]), r["resolved"]))
fig, ax = plt.subplots(figsize=(3.4, 2.4))
for th, dur, to, ok in pts:
    ax.scatter(th, dur, c="#C44E52" if to else ("#55A868" if ok else "#4C72B0"), s=14)
ax.set_xlabel("thinking tokens per task (≈chars/4)")
ax.set_ylabel("task duration (s)")
ax.scatter([], [], c="#C44E52", s=14, label="timeout")
ax.scatter([], [], c="#55A868", s=14, label="resolved")
ax.scatter([], [], c="#4C72B0", s=14, label="other")
ax.legend(fontsize=7, frameon=False)
save("thinking_time")
facts["thinking_corr"] = float(np.corrcoef([p[0] for p in pts], [p[1] for p in pts])[0, 1])

# ---------------- trajectory lengths vs compaction ----------------
lens = [8318, 8463, 9807, 10188, 10460, 11218, 12017, 12105, 12134, 14039, 14251, 14453, 14538, 14594, 14890, 15606, 15777,
        15908, 15929, 16715, 16905, 17035, 17346, 17356, 17742, 18210, 18325, 20144, 20257, 21047, 21494, 21701, 21860,
        22074, 22896, 23322, 24229, 25103, 25447, 26598, 28527, 28546, 29095, 29282, 32321, 37235]
fig, ax = plt.subplots(figsize=(3.4, 2.3))
ax.hist(np.array(lens) / 1000, bins=15, color="#8172B2")
ax.axvline(14.336, color="k", ls="--", lw=1)
ax.text(14.6, ax.get_ylim()[1] * 0.85, "compaction\nthreshold", fontsize=7)
ax.set_xlabel("passing trajectory length (k tokens, full history)")
ax.set_ylabel("trajectories")
save("traj_len")

# ---------------- B4 / B5 ----------------
facts["b4"] = {"rich": [2902, 260, 62], "fastapi": [5881, 55, 4], "requests": [4654, 280, 0]}
mut = [json.loads(l) for l in open(ROOT / "data" / "derived" / "synth_mutations.jsonl")]
mk = Counter(m["mutation"] for m in mut)
facts["b5"] = {"n": len(mut), "packages": len({m["package"] for m in mut}), "kinds": dict(mk)}
fig, ax = plt.subplots(figsize=(3.6, 2.6))
items = mk.most_common()
ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color="#DD8452")
ax.set_xlabel("injected bugs")
save("b5_kinds")
issues_path = ROOT / "data" / "derived" / "synth_issues.jsonl"
facts["b5_issues_so_far"] = sum(1 for _ in open(issues_path)) if issues_path.exists() else 0

(ROOT / "reports" / "report" / "facts.json").write_text(json.dumps(facts, indent=1, default=str))
print(json.dumps({k: v for k, v in facts.items() if k not in ("union", "b2")}, indent=1, default=str)[:4000])
