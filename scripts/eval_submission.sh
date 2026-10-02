#!/usr/bin/env bash
# Single entry point for local end-to-end evaluation of a submission directory.
# Requires a running server (scripts/start_server.sh). Mirrors the Kaggle scorer: budgets from the
# submission's eval_config.yaml (scorer defaults otherwise), events compaction, context cache.
# Usage: scripts/eval_submission.sh <submission_dir> <run_name> [task_ids_file|all] [extra swegemma args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUB="$(realpath "$1")"; NAME="$2"; SUBSET="${3:-all}"; shift $(( $# >= 3 ? 3 : $# ))
OUT="$ROOT/results/$NAME"
mkdir -p "$OUT"

TASK_ARGS=()
if [[ "$SUBSET" != "all" ]]; then
  mapfile -t ids < "$SUBSET"
  TASK_ARGS=(--task-ids "${ids[@]}")
fi

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:${PORT:-8011}/v1}" OPENAI_API_KEY=EMPTY
export LITELLM_LOCAL_MODEL_COST_MAP=True OTEL_SDK_DISABLED=true
cd "$ROOT"
find "$SUB" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
cp -r "$SUB" "$OUT/submission_snapshot" 2>/dev/null || true
exec "$ROOT/.venv-eval/bin/python" -m src.eval.run_eval \
  --submission-dir "$SUB" --results-dir "$OUT" \
  --concurrency "${CONCURRENCY:-3}" \
  "${TASK_ARGS[@]}" "$@"
