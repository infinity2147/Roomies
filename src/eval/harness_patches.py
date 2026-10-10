"""Make swegemma's subprocess sandbox behave like the competition Docker sandbox.

Upstream `install_test_dependencies` is a no-op for SubprocessManager (on Kaggle the notebook
image already has everything). Locally we have no Docker, so we replicate the Docker path:
unpack the deduplicated /wheels set into the sandbox venv's site-packages, then run
sandbox/setup.py --fast-path. Import this module before constructing an Evaluator.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from swegemma.harness import agent_runner, container_setup, verification
from swegemma.sandbox.subprocess import SubprocessManager

_orig_install = container_setup.install_test_dependencies


def _venv_site_packages(docker: SubprocessManager, cid: str) -> Path:
    venv = docker.sandboxes[cid]["venv"]
    return next(venv.glob("lib/python*/site-packages"))


def install_test_dependencies(docker, container_id, repo="", *, fast_path=True, config=None):
    if not isinstance(docker, SubprocessManager):
        return _orig_install(docker, container_id, repo, fast_path=fast_path, config=config)

    # Resolve versions per task under the repo's own constraints (offline, from /wheels).
    # Installing "latest of every wheel" (the Docker base injection) shadows the workspace
    # package and breaks older commits, so we let pip pick compatible versions instead.
    sp = _venv_site_packages(docker, container_id)
    if not (sp / ".swegemma_deps_resolved").exists():
        pip = "python3 -m pip install -q --disable-pip-version-check --no-index --find-links=/wheels --no-build-isolation"
        docker.exec(container_id, f"cd /workspace && {pip} -e . 2>&1 | tail -3")
        ws = docker.sandboxes[container_id]["workspace"]
        own = repo.rsplit("/", 1)[-1].lower()
        reqs: list[str] = []
        for rf in sorted(ws.glob("requirements*.txt")):
            if "doc" in rf.name:
                continue
            for line in rf.read_text(errors="ignore").splitlines():
                line = line.split("#", 1)[0].strip()
                if line and not line.startswith("-") and not line.lower().startswith(own):
                    reqs.append(line)
        for req in reqs:
            name = re.split(r"[<>=!~\[; ]", req, maxsplit=1)[0]
            res = docker.exec(container_id, f"{pip} {shlex.quote(req)}")
            if res.exit_code != 0 and name:
                docker.exec(container_id, f"{pip} {shlex.quote(name)}")
        (sp / ".swegemma_deps_resolved").write_text("ok\n")

    script = container_setup.resolve_sandbox_setup_script(config)
    if script and script.exists():
        docker.copy_to(container_id, script, "/tmp/setup.py")
        flag = "--fast-path" if fast_path else ""
        res = docker.exec(container_id, f"python3 /tmp/setup.py {flag} {shlex.quote(repo)}")
        if res.exit_code != 0:
            container_setup.logger.warning("setup.py failed for %s: %s", repo, res.stderr[-500:])
        docker.exec(container_id, "rm -f /tmp/setup.py")


for mod in (container_setup, verification, agent_runner):
    if hasattr(mod, "install_test_dependencies"):
        mod.install_test_dependencies = install_test_dependencies

# D18b: the subprocess sandbox whitelists env vars (adk_eval_core build_sanitized_env) and sets HOME to a tmp dir, so the
# worker's GIT_* identity never reaches `git commit`. On hosts without an FQDN (DGX nodes) git cannot auto-detect an email,
# the baseline commit fails silently, and harness conftest.py/pytest.ini leak into every patch. Pass the identity through.
from adk_eval_core.sandbox import subprocess_sandbox as _ss  # noqa: E402

_ss._SAFE_ENV_KEYS = tuple(_ss._SAFE_ENV_KEYS) + (
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")
