"""Build compact per-task caches (index + static features + gold labels). Usage: python -m src.localize.prep [--procs 4]"""
import argparse
import pickle
import sys
from multiprocessing import Pool

from src.localize.common import CACHE, SNAP, compact, load_gl, tasks


def work(t):
    gl = load_gl()
    try:
        d = compact(gl, t)
    except Exception as e:  # noqa
        return t["id"], repr(e)
    pickle.dump(d, open(CACHE / (t["id"] + ".pkl"), "wb"))
    return t["id"], len(d["gold_funcs"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    T = [t for t in tasks() if (SNAP / t["id"]).is_dir()]
    print(len(T), "tasks")
    with Pool(a.procs) as p:
        for tid, r in p.imap_unordered(work, T):
            print(tid, r, flush=True)
