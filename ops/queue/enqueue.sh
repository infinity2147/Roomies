#!/usr/bin/env bash
# Enqueue a candidate × seed over all shards of a task set.
# Usage: ops/queue/enqueue.sh <priority 00-99> <submission_dir> <run_name> <proxy|public>
# Items are named <prio>_<shard>_<run> so that, within a priority, shard k of every run is done before shard k+1
# (paired comparisons accumulate evenly).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
prio=$1 sub=$2 run=$3 mode=$4
mkdir -p ops/queue/pending
for f in ops/queue/shards/$mode/*.txt; do
  s=$(basename "$f" .txt)
  echo "$sub $run $f $mode" > "ops/queue/pending/${prio}_${s}_${run}"
done
ls ops/queue/pending | wc -l
