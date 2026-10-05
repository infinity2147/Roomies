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

_orig_install = _cs.install_test_dependencies


def _install_test_dependencies(docker, container_id, repo="", *, fast_path=True, config=None):
    if not isinstance(docker, _SM):
        return _orig_install(docker, container_id, repo, fast_path=fast_path, config=config)
    paths = docker.sandboxes[container_id]
    sp = next(paths["venv"].glob("lib/python*/site-packages"))
    ws = paths["workspace"]
    # v3 (minimal): only src-layout repos get their src/ ahead of system site-packages. Non-src repos
    # (fastapi) keep the exact no-fix environment (v1/v2's editable install + backend installs changed
    # starlette resolution and broke older fastapi tasks: 62 -> 16 gold passes).
    if (ws / "src").is_dir():
        (sp / "000_workspace_src_first.pth").write_text(str(ws / "src") + "\n")
    _pdir = globals().get("PROXY_DIR")
    if _pdir:  # proxy benchmark: extra test-only wheels (attrs excluded: never shadow the attrs repo)
        _g = set((Path(_pdir) / "google_wheels.txt").read_text().split()) if (Path(_pdir) / "google_wheels.txt").exists() else set()
        _whl = [w for w in sorted(Path(_pdir).glob("*.whl")) if not w.name.startswith("attrs-")
                and (w.name not in _g or repo.startswith(("google/", "google-deepmind/")))]
        if _whl:
            docker.exec(container_id, "python3 -m pip install -q --disable-pip-version-check --no-index --no-deps "
                        + " ".join(_shlex.quote(str(w)) for w in _whl) + " 2>&1 | tail -2")
    # NOTE: do not run sandbox/setup.py --fast-path here: it puts every workspace subdirectory on
    # sys.path (e.g. fastapi/requests.py then shadows the real `requests`) - kverify-fix v1 lost all
    # 67 fastapi gold passes that way.


for _m in (_cs, _vf, _ar):
    if hasattr(_m, "install_test_dependencies"):
        _m.install_test_dependencies = _install_test_dependencies
print("sandbox fix v3 installed (src-layout precedence only)", flush=True)
# -------------------------------------------------------------------------------------------------
