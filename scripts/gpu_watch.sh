#!/usr/bin/env bash
# Poll every INTERVAL seconds; exit 0 (and print status) once ALL listed GPUs have >= MIN_FREE_MIB free.
# Usage: scripts/gpu_watch.sh   (env: GPUS="0,1" MIN_FREE_MIB=21000 INTERVAL=600)
GPUS="${GPUS:-0,1}"; MIN_FREE_MIB="${MIN_FREE_MIB:-21000}"; INTERVAL="${INTERVAL:-600}"
while true; do
  ok=1; status=""
  for g in ${GPUS//,/ }; do
    free=$(nvidia-smi -i "$g" --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' ')
    status+="gpu$g free=${free}MiB "
    (( free >= MIN_FREE_MIB )) || ok=0
  done
  echo "$(date '+%F %T') $status" >> "$(dirname "$0")/../results/gpu_watch.log"
  if (( ok )); then echo "GPUS_FREE $(date '+%F %T') $status"; exit 0; fi
  sleep "$INTERVAL"
done
