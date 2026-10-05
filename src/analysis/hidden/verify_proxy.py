"""Run src.eval.verify_gold against the proxy benchmark with the proxy wheel set.

The proxy wheel set = data/wheels (public cache) + data/derived/proxy/wheels_extra (test-only deps
of the proxy repos: hypothesis, simplejson, typeguard, tornado, trio, oauthlib, requests-mock,
ephemeral-port-reserve, blockbuster, httpx2/httpcore2, coverage, ...). The hidden-set scorer
ships its own private wheel cache for the hidden repos, so provisioning test deps is the faithful
analogue; tasks that still fail with gold are dropped exactly like the organizers drop them.

Usage (3.13 eval env):
  .venv-eval/bin/python -m src.analysis.hidden.verify_proxy --mode gold --concurrency 6 --name proxyw_
"""

from pathlib import Path

import src.eval.verify_gold as vg  # noqa: E402  (imports src.eval.harness_patches)
from src.eval import harness_patches as hp
from swegemma.harness import agent_runner, container_setup, verification

ROOT = Path(__file__).resolve().parents[3]
SHIM = ROOT / "data" / "derived" / "proxy" / "shim"  # wheels/ + symlinks to sample_submission, graphs, embeddings

EXTRA = sorted(p.name for p in (ROOT / "data/derived/proxy/wheels_extra").glob("*.whl")
               if not p.name.startswith("attrs-"))  # attrs: host env already has it; never shadow the attrs repo


def install_test_dependencies(docker, container_id, repo="", *, fast_path=True, config=None):
    hp.install_test_dependencies(docker, container_id, repo, fast_path=fast_path, config=config)
    if not hasattr(docker, "sandboxes"):
        return
    # The subprocess sandbox rewrites `/wheels` to ./data/wheels (public cache), so use absolute host paths.
    files = " ".join(str(ROOT / "data/derived/proxy/wheels_extra" / n) for n in EXTRA)
    if repo.startswith(("google/", "google-deepmind/")):  # absl-py, libcst, termcolor, pytest-asyncio, ...
        files += " " + " ".join(str(p) for p in sorted((ROOT / "data/derived/proxy/wheels_extra_google").glob("*.whl")))
    res = docker.exec(container_id, "python3 -m pip install -q --disable-pip-version-check --no-index --no-deps "
                              f"{files} 2>&1 | tail -2")
    # src-layout repos: if the editable install failed, workspace_paths.pth is processed after
    # _host_env.pth and an installed copy of the same package (click/flask/werkzeug/jinja2/attrs/google-adk
    # live in the host env) silently shadows the workspace -> gold "fails" and empty "passes".
    # A .pth that sorts first puts /workspace/src ahead of the host site-packages.
    src = docker.sandboxes[container_id]["workspace"] / "src"
    if src.is_dir():
        (hp._venv_site_packages(docker, container_id) / "00_proxy_workspace_src.pth").write_text(f"{src}\n")
    if (res.stdout or "").strip():
        print(f"extra-deps: {(res.stdout or '').strip()[-300:]}", flush=True)


for _mod in (container_setup, verification, agent_runner):
    if hasattr(_mod, "install_test_dependencies"):
        _mod.install_test_dependencies = install_test_dependencies

if __name__ == "__main__":
    import sys
    vg.DATA = SHIM
    if "--tasks" not in sys.argv:
        sys.argv += ["--tasks", str(ROOT / "data/derived/proxy/tasks.jsonl")]
    if "--snapshots-dir" not in sys.argv:
        sys.argv += ["--snapshots-dir", str(ROOT / "data/derived/proxy/snapshots")]
    vg.main()
