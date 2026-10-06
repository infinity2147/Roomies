#!/usr/bin/env bash
# Stop our vLLM server and its renamed worker processes (VLLM::Worker_*, VLLM::EngineCore), own user only.
u=$(id -u)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pids=$(pgrep -u "$u" -f "^$ROOT/.venv-harness/bin/python"; pgrep -u "$u" -f "^VLLM::")
[[ -n "$pids" ]] && kill $pids 2>/dev/null
sleep 8
pids=$(pgrep -u "$u" -f "^$ROOT/.venv-harness/bin/python"; pgrep -u "$u" -f "^VLLM::")
[[ -n "$pids" ]] && kill -9 $pids 2>/dev/null
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader
