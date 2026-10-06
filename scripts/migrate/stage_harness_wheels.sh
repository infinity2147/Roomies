#!/usr/bin/env bash
# LOGIN NODE (has internet): download every wheel .venv-harness needs, for the compute nodes' platform
# (Ubuntu 22.04 / glibc 2.35, CPython 3.12), into external/wheels_harness/ on the shared filesystem.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH" UV_PYTHON_INSTALL_DIR="$ROOT/external/python" UV_NO_PROGRESS=1
W=external/wheelhouse; OUT=external/wheels_harness; mkdir -p "$OUT"
uv python install 3.12
rm -rf /tmp/$USER/dlvenv && uv venv --seed -p 3.12 /tmp/$USER/dlvenv
P=/tmp/$USER/dlvenv/bin/python
REQS=("vllm==0.19.1" "google-adk==1.36.1" "transformers==5.13.1" compressed-tensors litellm pandas networkx docker
      torchvision accelerate pytest pytest-timeout peft "fastapi<0.130" "google-genai==2.11.0" cachetools python-dotenv)
PLATS=(); for v in $(seq 35 -1 17); do PLATS+=(--platform "manylinux_2_${v}_x86_64"); done; PLATS+=(--platform manylinux2014_x86_64 --platform linux_x86_64)
$P -m pip download -d "$OUT" --only-binary=:all: --python-version 3.12 --implementation cp "${PLATS[@]}" \
   "${REQS[@]}" $W/swegemma-*.whl $W/adk_submission-*.whl $W/adk_eval_core-*.whl
cp $W/vllm-0.19.1-*.whl "$OUT/" 2>/dev/null || true
echo "STAGED $(ls $OUT | wc -l) wheels, $(du -sh $OUT | cut -f1)"
