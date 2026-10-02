#!/usr/bin/env bash
# Push Kaggle eval kernels one by one as GPU session slots free up (max 2 concurrent), then fetch all.
# Usage: scripts/kaggle_eval/queue.sh "submissions/c6a:c6a_full_r2" "data/sample_submission:b0_full_r1" ...
#        (optional third field = --n subset size)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
runs=()
for item in "$@"; do
  IFS=: read -r sub run n <<< "$item"
  extra=(); [[ -n "$n" ]] && extra=(--n "$n")
  .venv/bin/python scripts/kaggle_eval/make_kernel.py --submission "$sub" --run "$run" --concurrency 4 "${extra[@]}" >/dev/null
  slug="gemma-rl-eval-$(echo "$run" | tr '_' '-' | tr 'A-Z' 'a-z')"
  until out=$(.venv/bin/kaggle kernels push -p "results/kaggle_kernels/$slug" 2>&1) && echo "$out" | grep -q "successfully pushed"; do
    echo "$(date +%T) waiting for slot ($run): $(echo "$out" | tail -1 | cut -c1-80)" >> results/kaggle_queue.log
    sleep 300
  done
  echo "$(date +%T) pushed $run" | tee -a results/kaggle_queue.log
  runs+=("$run")
done
scripts/kaggle_eval/wait_fetch.sh "${runs[@]}"
