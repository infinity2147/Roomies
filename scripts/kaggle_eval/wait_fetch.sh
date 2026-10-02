#!/usr/bin/env bash
# Wait for one or more Kaggle eval kernels to finish, download their outputs, print summaries.
# Usage: scripts/kaggle_eval/wait_fetch.sh <run_name> [<run_name> ...]   (slug = gemma-rl-eval-<run>)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
K="$ROOT/.venv/bin/kaggle"
for run in "$@"; do
  slug="vedantmoghe/gemma-rl-eval-$(echo "$run" | tr '_' '-')"
  while true; do
    s=$("$K" kernels status "$slug" 2>&1 | tail -1)
    case "$s" in *COMPLETE*|*ERROR*|*CANCEL*) break;; esac
    sleep 120
  done
  echo "$run: $s"
  out="$ROOT/results/kaggle/$run"; mkdir -p "$out"
  "$K" kernels output "$slug" -p "$out" >/dev/null 2>&1
  cat "$out"/results/"$run"/kernel_summary.json 2>/dev/null || { echo "no summary; log tail:"; tail -15 "$out"/*.log 2>/dev/null | cut -c1-200; }
done
