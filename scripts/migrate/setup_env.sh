#!/usr/bin/env bash
# Rebuild the three Python environments on a new machine (run from the project root, login node is fine:
# needs internet for PyPI; GPUs not needed to build).
#   .venv          (3.13)  research code: numpy, lightgbm, unidiff, matplotlib, kaggle CLI, ...
#   external/python (3.13 standalone) = clean "sandbox base image" interpreter + test-only plugins
#   .venv-eval     (3.13 on that base) harness (swegemma, adk) WITHOUT torch -> evaluation runner
#   .venv-harness  (3.12) vLLM 0.19.1 (Kaggle wheelhouse build, LoRA-capable for Gemma-4) + torch -> model server
# Requires: external/wheelhouse/ (copied, or: kaggle datasets download metric/gemma-4-developer-agent-wheelhouse)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
W=external/wheelhouse

# 0) uv (single static binary)
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
export UV_PYTHON_INSTALL_DIR="$ROOT/external/python"
# uv's cache locks are unreliable on Lustre and must not be shared by concurrent runs: use node-local disk.
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/$USER/uv-cache}" UV_LINK_MODE=copy UV_LOCK_TIMEOUT=1200
mkdir -p "$UV_CACHE_DIR"
ok() { "$1" -c "$2" >/dev/null 2>&1; }   # resumable: skip an env that already works

# 1) research env
if ! ok .venv/bin/python "import numpy, lightgbm, kaggle"; then
uv venv --clear -p 3.13 .venv
uv pip install --python .venv/bin/python numpy scipy scikit-learn lightgbm networkx unidiff rank-bm25 pyyaml \
    pytest pandas matplotlib pymupdf kaggle
fi

# 2) clean 3.13 base interpreter mirroring the scorer sandbox image (Dockerfile.sandbox + test plugins)
uv python install 3.13
PY=$(ls -d "$UV_PYTHON_INSTALL_DIR"/cpython-3.13*/bin/python3.13 | head -1)
uv pip install --python "$PY" --break-system-packages pytest "pytest-timeout==2.1.0" typer pdm-backend setuptools \
    wheel poetry-core hatchling flit-core editables pytest-httpbin "httpbin~=0.10.0" trustme pytest-mock \
    inline-snapshot dirty-equals
SP=$("$PY" -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
cp data/docker/imp.py data/docker/telnetlib.py "$SP/"

# 3) eval env (harness, no torch) on the clean base
if ! ok .venv-eval/bin/python "import swegemma.evaluate"; then
uv venv --clear -p "$PY" .venv-eval
uv pip install --python .venv-eval/bin/python --no-deps $W/swegemma-*.whl $W/adk_submission-*.whl $W/adk_eval_core-*.whl
uv pip install --python .venv-eval/bin/python "google-adk==1.36.1" "google-genai==2.11.0" litellm pandas networkx \
    docker "numpy>=2" pyyaml rich "transformers==5.13.1" tokenizers safetensors cachetools python-dotenv requests unidiff
fi

# 4) model-server env (3.12): PyPI vLLM for deps, then the Kaggle wheelhouse vLLM build on top (Gemma-4 LoRA support)
uv python install 3.12
if ! ok .venv-harness/bin/python "import vllm, torch, peft"; then
uv venv --clear -p 3.12 .venv-harness
uv pip install --python .venv-harness/bin/python "vllm==0.19.1" $W/swegemma-*.whl $W/adk_submission-*.whl \
    $W/adk_eval_core-*.whl "google-adk==1.36.1" "transformers==5.13.1" compressed-tensors litellm pandas networkx \
    docker torchvision accelerate pytest pytest-timeout peft
uv pip install --python .venv-harness/bin/python --no-deps --reinstall $W/vllm-0.19.1-*.whl
uv pip install --python .venv-harness/bin/python "fastapi<0.130"
fi
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py   # local patches (harmless in TP mode)

echo "--- sanity ---"
.venv/bin/python -c "import numpy, lightgbm, kaggle; print('research env ok')"
.venv-eval/bin/python -c "import swegemma.evaluate; print('eval env ok')"
.venv-harness/bin/python -c "import vllm, torch; print('server env ok; torch', torch.__version__, 'cuda', torch.version.cuda)"
