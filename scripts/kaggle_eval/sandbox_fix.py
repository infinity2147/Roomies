# --- Sandbox environment fix for Kaggle (inserted into kernel templates) -------------------------
# Problem (council review E1): on Kaggle the subprocess sandbox inherits the notebook image's
# site-packages and the harness skips dependency installation; src-layout repos (requests, httpx)
# are not importable from /workspace, so tests import the image's preinstalled copy instead of the
# agent's patched code. Fix: per sandbox, try an editable install of /workspace (build backends from
# the competition wheels) and always add a .pth that puts /workspace/src and /workspace AHEAD of the
# system dist-packages (venv site-packages .pth entries are processed before system site dirs).
import shlex as _shlex

from swegemma.harness import agent_runner as _ar, container_setup as _cs, verification as _vf
from swegemma.sandbox.subprocess import SubprocessManager as _SM

_COMP_WHEELS = DATA / "wheels"
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-index", f"--find-links={_COMP_WHEELS}",
                "hatchling", "pdm-backend", "flit-core", "poetry-core", "editables", "setuptools", "wheel"],
               capture_output=True)
_orig_install = _cs.install_test_dependencies


def _install_test_dependencies(docker, container_id, repo="", *, fast_path=True, config=None):
    if not isinstance(docker, _SM):
        return _orig_install(docker, container_id, repo, fast_path=fast_path, config=config)
    paths = docker.sandboxes[container_id]
    sp = next(paths["venv"].glob("lib/python*/site-packages"))
    ws = paths["workspace"]
    docker.exec(container_id, "cd /workspace && python3 -m pip install -q --disable-pip-version-check --no-index "
                              "--find-links=/wheels --no-build-isolation --no-deps -e . 2>&1 | tail -2")
    entries = [str(ws / "src")] if (ws / "src").is_dir() else []
    entries.append(str(ws))
    (sp / "000_workspace_first.pth").write_text("\n".join(entries) + "\n")
    # NOTE: do not run sandbox/setup.py --fast-path here: it puts every workspace subdirectory on
    # sys.path (e.g. fastapi/requests.py then shadows the real `requests`) - kverify-fix v1 lost all
    # 67 fastapi gold passes that way.


for _m in (_cs, _vf, _ar):
    if hasattr(_m, "install_test_dependencies"):
        _m.install_test_dependencies = _install_test_dependencies
print("sandbox fix installed (workspace-first .pth + editable install)", flush=True)
# -------------------------------------------------------------------------------------------------
