"""Build (and optionally push) a private Kaggle kernel that evaluates a submission on real scorer hardware.

Usage:
  .venv/bin/python scripts/kaggle_eval/make_kernel.py --submission submissions/c1 --run c1_v1 \
      [--ids data/derived/valid_tasks.txt | --n 30] [--concurrency 4] [--push]
  .venv/bin/kaggle kernels status <user>/<slug>      # check
  .venv/bin/kaggle kernels output <user>/<slug> -p results/kaggle/<run>   # fetch results
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import random
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER = "vedantmoghe"


def zip_submission(sub: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(sub.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, p.relative_to(sub).as_posix())
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--ids", default=str(ROOT / "data" / "derived" / "valid_tasks.txt"))
    ap.add_argument("--n", type=int, default=0, help="random stratified subset size (0 = all ids)")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    ids = [l.strip() for l in open(a.ids) if l.strip()]
    if a.n:
        random.Random(a.seed).shuffle(ids)
        ids = sorted(ids[: a.n])
    slug = re.sub(r"[^a-z0-9-]", "-", f"gemma-rl-eval-{a.run}".lower())
    kdir = ROOT / "results" / "kaggle_kernels" / slug
    kdir.mkdir(parents=True, exist_ok=True)
    code = (ROOT / "scripts" / "kaggle_eval" / "kernel_template.py").read_text()
    code = (code.replace("__RUN_NAME__", a.run).replace("__TASK_IDS__", json.dumps(ids))
                .replace("__CONCURRENCY__", str(a.concurrency))
                .replace("__SUBMISSION_B64__", base64.b64encode(zip_submission(Path(a.submission))).decode()))
    (kdir / "kernel.py").write_text(code)
    meta = {
        "id": f"{USER}/{slug}", "title": slug, "code_file": "kernel.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_tpu": False,
        "enable_internet": False, "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse", f"{USER}/gemma-rl-test-wheels"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [],
        "model_sources": ["google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2"], "machine_shape": "NvidiaL4",
    }
    (kdir / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
    print(f"kernel dir: {kdir}  tasks={len(ids)}  size={len(code) / 1024:.0f} KiB")
    if a.push:
        subprocess.run([str(ROOT / ".venv" / "bin" / "kaggle"), "kernels", "push", "-p", str(kdir)], check=True)


if __name__ == "__main__":
    main()
