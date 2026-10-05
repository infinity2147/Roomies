"""End-to-end agent eval on the proxy benchmark (same scorer mirror as src.eval.run_eval).

Applies the proxy sandbox provisioning from src.analysis.hidden.verify_proxy (extra test-dep wheels,
src-layout precedence) and points run_eval at data/derived/proxy/evaldata/:
  tasks.jsonl -> proxy valid tasks (or a subset: --set proxy60), snapshots -> ../snapshots,
  wheels -> data/wheels, graphs/ embeddings/ empty (no code graphs for proxy repos; graph tools
  are auto-disabled, like any repo without graph files).

Usage: .venv-eval/bin/python -m src.analysis.hidden.run_proxy_eval [--set valid|proxy60] \
          --submission-dir submissions/X --results-dir results/proxy/X [--concurrency 3]
"""

import sys
from pathlib import Path

import src.analysis.hidden.verify_proxy  # noqa: F401  (patches install_test_dependencies)
import src.eval.run_eval as re_

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "data" / "derived" / "proxy"

if __name__ == "__main__":
    which = "valid"
    if "--set" in sys.argv:
        i = sys.argv.index("--set")
        which = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    ev = P / f"evaldata_{which}"
    ev.mkdir(exist_ok=True)
    for name, target in [("snapshots", P / "snapshots"), ("wheels", ROOT / "data" / "wheels")]:
        if not (ev / name).exists():
            (ev / name).symlink_to(target)
    for name in ("graphs", "embeddings"):
        (ev / name).mkdir(exist_ok=True)
    (ev / "tasks.jsonl").write_text((P / f"{which}_tasks.jsonl").read_text())
    re_.DATA = ev
    re_.main()
