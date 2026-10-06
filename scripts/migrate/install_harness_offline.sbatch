#!/bin/bash
# DGX NODE (no internet): build .venv-harness offline from external/wheels_harness/ (see stage_harness_wheels.sh).
#SBATCH -p dgx
#SBATCH --qos=dgx
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH -o results/slurm/install_harness_%j.out
set -euo pipefail
cd ~/project/Gemma_RL
export PATH="$HOME/.local/bin:$PATH" UV_PYTHON_INSTALL_DIR="$PWD/external/python" UV_NO_PROGRESS=1 \
       UV_CACHE_DIR=/tmp/$USER/uv-cache UV_LINK_MODE=copy UV_OFFLINE=1
H=external/wheels_harness; W=external/wheelhouse
uv venv --clear -p 3.12 .venv-harness
uv pip install --python .venv-harness/bin/python --no-index --find-links "$H" "vllm==0.19.1" \
   $W/swegemma-*.whl $W/adk_submission-*.whl $W/adk_eval_core-*.whl "google-adk==1.36.1" "transformers==5.13.1" \
   compressed-tensors litellm pandas networkx docker torchvision accelerate pytest pytest-timeout peft \
   "google-genai==2.11.0" cachetools python-dotenv
uv pip install --python .venv-harness/bin/python --no-index --no-deps --reinstall $W/vllm-0.19.1-*.whl
uv pip install --python .venv-harness/bin/python --no-index --find-links "$H" "fastapi<0.130"
.venv-harness/bin/python scripts/patch_vllm_gemma4_pp.py
.venv-harness/bin/python -c "import vllm, torch, peft; print('server env ok; torch', torch.__version__, 'cuda', torch.version.cuda, 'gpu', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
.venv-harness/bin/python -c "import vllm.model_executor.models.gemma4_mm as g; print('lora-capable:', 'SupportsLoRA' in open(g.__file__).read())"
echo INSTALL_DONE
