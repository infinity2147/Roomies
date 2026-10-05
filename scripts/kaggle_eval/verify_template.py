# CPU-only Kaggle kernel: verify gold vs empty patches in the SAME sandbox environment the eval
# kernels use (council review E2). No GPU, no model. Output: results/<RUN>/verify_{gold,empty}.jsonl
import asyncio
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RUN_NAME = "__RUN_NAME__"
APPLY_FIX = __APPLY_FIX__
TASKS_DATASET = "__TASKS_DATASET__"
T0 = time.time()


def find_dir(*patterns):
    for p in patterns:
        hits = sorted(glob.glob(p))
        if hits:
            return Path(hits[0])
    raise FileNotFoundError(patterns)


WHEELHOUSE = find_dir("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse",
                      "/kaggle/input/*/gemma-4-developer-agent-wheelhouse", "/kaggle/input/gemma-4-developer-agent-wheelhouse")
DATA = find_dir("/kaggle/input/competitions/gemma-4-developer-agent", "/kaggle/input/gemma-4-developer-agent")
WORK = Path("/kaggle/working")
PROXY_DIR = None
if TASKS_DATASET:
    PROXY_DIR = find_dir(f"/kaggle/input/*/{TASKS_DATASET}", f"/kaggle/input/datasets/*/{TASKS_DATASET}", f"/kaggle/input/{TASKS_DATASET}")
# install only the harness packages (no vLLM/torch needed for verification)
harness = [str(w) for w in WHEELHOUSE.glob("*.whl") if w.name.split("-")[0] in
           ("swegemma", "adk_submission", "adk_eval_core", "google_adk", "google_genai")]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--force-reinstall", *harness], check=True)
TEST_WHEELS = sorted(glob.glob("/kaggle/input/*/gemma-rl-test-wheels") + glob.glob("/kaggle/input/datasets/*/gemma-rl-test-wheels"))
if TEST_WHEELS:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-index", f"--find-links={TEST_WHEELS[0]}",
                    "inline-snapshot", "dirty-equals", "pytest-httpbin", "httpbin", "trustme", "pytest-mock"], capture_output=True)
print(f"[{time.time() - T0:.0f}s] packages installed; python {sys.version.split()[0]}", flush=True)

from swegemma.config import EvalConfig  # noqa: E402
from swegemma.deduplication import resolve_task_snapshot_paths  # noqa: E402
from swegemma.evaluate import Evaluator  # noqa: E402
from swegemma.harness.verification import verify_task  # noqa: E402
from swegemma.models import load_tasks  # noqa: E402

if APPLY_FIX:
    pass  # __SANDBOX_FIX__

out = WORK / "results" / RUN_NAME
out.mkdir(parents=True, exist_ok=True)
TASKS_PATH, SNAP_DIR = DATA / "tasks.jsonl", DATA / "snapshots"
if PROXY_DIR:
    import shutil
    _ev = WORK / "proxy_evaldata"
    (_ev / "snapshots").mkdir(parents=True, exist_ok=True)
    for _t in PROXY_DIR.glob("*.tgz"):
        if not (_ev / "snapshots" / _t.name).exists():
            os.symlink(_t, _ev / "snapshots" / _t.name)
    shutil.copy(PROXY_DIR / "tasks.jsonl", _ev / "tasks.jsonl")
    TASKS_PATH, SNAP_DIR = _ev / "tasks.jsonl", _ev / "snapshots"
cfg = EvalConfig(tasks_path=TASKS_PATH, snapshots_dir=SNAP_DIR, results_dir=out / "verify",
                 submission_dir=DATA / "sample_submission", models={}, sandbox="subprocess", wheels_dir=DATA / "wheels",
                 graph_dir=str(DATA / "graphs"), embeddings_dir=str(DATA / "embeddings"), display_mode="quiet")
ev = Evaluator(cfg)
tasks = load_tasks(TASKS_PATH)
sem = asyncio.Semaphore(max(2, os.cpu_count() or 2))


async def one(t, mode):
    async with sem:
        snap, base, pp = resolve_task_snapshot_paths(cfg.snapshots_dir, t.instance_id, t.repo)
        t1 = time.perf_counter()
        r = await verify_task(ev.docker, cfg, t, snap, base_snapshot_path=base, patch_path=pp,
                              agent_patch=t.patch if mode == "gold" else "", start_time=t1)
        rec = {"instance_id": t.instance_id, "mode": mode, "resolved": bool(r.resolved), "exit": r.test_exit_code,
               "error": (r.error or "")[:300], "tail": (r.test_output or "")[-800:], "sec": round(time.perf_counter() - t1, 1)}
        with open(out / f"verify_{mode}.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def main():
    res = await asyncio.gather(*(one(t, m) for m in ("gold", "empty") for t in tasks))
    gold = {r["instance_id"]: r["resolved"] for r in res if r["mode"] == "gold"}
    empty = {r["instance_id"]: r["resolved"] for r in res if r["mode"] == "empty"}
    valid = sorted(i for i in gold if gold[i] and not empty[i])
    summary = {"run": RUN_NAME, "fix": APPLY_FIX, "gold_pass": sum(gold.values()), "empty_pass": sum(empty.values()),
               "valid": len(valid), "valid_ids": valid, "wall_s": round(time.time() - T0)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "valid_ids"}), flush=True)


asyncio.run(main())
