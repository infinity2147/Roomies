"""Build/push the CPU-only Kaggle verification kernel (gold vs empty patches in the eval environment).

Usage: .venv/bin/python scripts/kaggle_eval/make_verify_kernel.py --run kverify_fix [--no-fix] [--push]
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER = "vedantmoghe"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--tasks-dataset", default="")
    a = ap.parse_args()
    code = (ROOT / "scripts" / "kaggle_eval" / "verify_template.py").read_text()
    fix = (ROOT / "scripts" / "kaggle_eval" / "sandbox_fix.py").read_text()
    indented = "\n".join(("    " + l) if l.strip() else l for l in fix.splitlines())
    code = (code.replace("__RUN_NAME__", a.run).replace("__APPLY_FIX__", str(not a.no_fix)).replace("__TASKS_DATASET__", a.tasks_dataset)
                .replace("    pass  # __SANDBOX_FIX__", indented))
    slug = re.sub(r"[^a-z0-9-]", "-", f"gemma-rl-{a.run}".lower())
    kdir = ROOT / "results" / "kaggle_kernels" / slug
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "kernel.py").write_text(code)
    (kdir / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{USER}/{slug}", "title": slug, "code_file": "kernel.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse", f"{USER}/gemma-rl-test-wheels",
                            *([f"{USER}/{a.tasks_dataset}"] if a.tasks_dataset else [])],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": []}, indent=1))
    print("kernel dir", kdir)
    if a.push:
        subprocess.run([str(ROOT / ".venv" / "bin" / "kaggle"), "kernels", "push", "-p", str(kdir)], check=True)


if __name__ == "__main__":
    main()
