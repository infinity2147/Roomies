"""Baseline: the existing repo-locate skill (submissions/c13t_c11t_locskill) scored with the same labels/metrics.
Usage: python -m src.localize.eval_repo_locate  -> results/graph_locate/repo_locate.json"""
import json
import re
import subprocess
from multiprocessing import Pool

from src.localize.common import CACHE, ROOT, SNAP, tasks
from src.localize.learn import KS, cq, metrics, pooled

SK = ROOT / "submissions/c13t_c11t_locskill/skills/repo-locate/scripts/locate.py"
FILE = re.compile(r"^\d+\.\s+(\S+\.py)\s")
DEF = re.compile(r"^\s+L(\d+)-(\d+)\s+(\S+?):")


def run(t):
    d = SNAP / t["id"]
    import time
    t0 = time.time()
    try:
        r = subprocess.run([str(ROOT / ".venv/bin/python"), str(SK), "--issue", t["text"][:4000], "--root", str(d), "--k", "10"],
                           capture_output=True, text=True, timeout=40, cwd=str(d), env={"PATH": "/usr/bin:/bin", "PWD": str(d), "SWE_WORKSPACE": str(d)})
    except subprocess.TimeoutExpired:  # counted as a miss (no output)
        r = type("R", (), {"stdout": ""})()
    dt = time.time() - t0
    f, rank, files = None, [], []
    c = cq(t["id"])
    idx = {(n.file, n.qual): n.id for n in c.ix.nodes}
    for l in r.stdout.splitlines():
        m = FILE.match(l)
        if m:
            f = m.group(1)
            files.append(f)
            continue
        m = DEF.match(l)
        if m and f and (f, m.group(3)) in idx and idx[(f, m.group(3))] not in rank:
            rank.append(idx[(f, m.group(3))])
    c.gold_files = c.gold_files
    out = {}
    if c.gold:
        for k in KS:
            out["fn_hit@%d" % k] = float(any(n in c.gold for n in rank[:k]))
        out["fn_recall@10"] = len(c.gold & set(rank[:10])) / len(c.gold)
    if c.gold_files:
        for k in KS:
            out["file_hit@%d" % k] = float(any(x in c.gold_files for x in files[:k]))
    out["timeout"] = float(dt >= 39)
    out["secs"] = dt
    return t["id"], t["split"], t["src"], out


def agg(rows):
    acc, cnt = {}, {}
    for r in rows:
        for k, v in r.items():
            acc[k] = acc.get(k, 0) + v
            cnt[k] = cnt.get(k, 0) + 1
    d = {k: round(acc[k] / cnt[k], 4) for k in acc}
    d["n_fn"] = cnt.get("fn_hit@1", 0)
    d["n_file"] = cnt.get("file_hit@1", 0)
    return d


if __name__ == "__main__":
    T = [t for t in tasks() if (CACHE / (t["id"] + ".pkl")).exists()]
    with Pool(4) as p:
        rows = []
        for r in p.imap(run, T, chunksize=1):
            rows.append(r)
            print(len(rows), r[0], round(r[3]['secs'], 1), flush=True)
    res = {"train_pool": agg([r[3] for r in rows if r[1] == "train"]), "test_half": agg([r[3] for r in rows if r[1] == "test"]),
           "public": agg([r[3] for r in rows if r[2] == "public"])}
    json.dump(res, open(ROOT / "results/graph_locate/repo_locate.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
