#!/usr/bin/env bash
# GPU filler (cron, every 10 min): while file queues have pending items, submit ap_worker jobs sized to GPUs that are
# free RIGHT NOW (so they start immediately instead of waiting on fairshare priority), within QoS caps and a ceiling on
# our total GPUs (teammate headroom). Also: returns items orphaned by dead/timed-out workers to pending, and cancels
# its own jobs that stay pending > STALE_MIN (the hole was taken by someone else).
# Only touches jobs named ap-* (never teammates' jobs). Disable: touch ops/slurm/FILLER_STOP. Log: results/slurm/gpu_filler.log
ROOT=/home/fmr-group/24b4518/project/Gemma_RL
cd "$ROOT" || exit 1
export PATH="/opt/slurm/bin:/usr/local/bin:/usr/bin:/bin"
[[ -f ops/slurm/FILLER_STOP ]] && exit 0
exec 9>results/slurm/gpu_filler.lock; flock -n 9 || exit 0
LOG=results/slurm/gpu_filler.log
MAX_GPUS=${MAX_GPUS:-16}      # ceiling on GPUs held by all our ap-* jobs (running + pending)
STALE_MIN=${STALE_MIN:-20}
DRY=${DRY:-0}
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
declare -A QOS_JOBS=([dgx]=4 [l40]=4 [a40]=3)   # max running jobs per QoS
declare -A QOS_GPJ=([dgx]=4 [l40]=4 [a40]=2)    # max GPUs per job
PARTS=(dgx l40 a40)                              # preference order (A100 80 GB first)

SQ=$(squeue -h -u "$USER" -o "%i|%j|%T|%P|%b|%V" 2>/dev/null) || { log "squeue failed"; exit 0; }

# 1. orphans: running/<item>.<jobid>_<slot> whose job is no longer alive -> back to pending
for q in ops/queue ops/queue_*; do
  [[ -d $q/running ]] || continue
  for f in "$q"/running/*; do
    [[ -e $f ]] || continue
    b=$(basename "$f"); tag=${b##*.}; jid=${tag%_*}
    [[ $jid =~ ^[0-9]+$ ]] || continue
    grep -q "^$jid|" <<<"$SQ" && continue
    st=$(sacct -n -X -j "$jid" -o State 2>/dev/null | head -1 | tr -d ' ')
    [[ -z $st || $st == RUNNING* || $st == PENDING* ]] && continue   # unknown/alive: leave it
    [[ $DRY == 1 ]] || mv "$f" "$q/pending/${b%.*}"
    log "orphan $q/${b%.*} (job $jid $st) -> pending"
  done
done

# 2. cancel our filler jobs that did not start within STALE_MIN
now=$(date +%s)
while IFS='|' read -r jid name state part gres sub; do
  [[ $name == ap-fill-* && $state == PENDING ]] || continue
  age=$(( (now - $(date -d "$sub" +%s)) / 60 ))
  if (( age > STALE_MIN )); then [[ $DRY == 1 ]] || scancel "$jid"; log "cancel stale pending $jid $name ($age min)"; fi
done <<<"$SQ"
SQ=$(squeue -h -u "$USER" -o "%i|%j|%T|%P|%b|%V" 2>/dev/null)

gpus_of() { local g=${1##*:}; [[ $g =~ ^[0-9]+$ ]] && echo "$g" || echo 1; }
ours=0; declare -A NJOBS=([dgx]=0 [l40]=0 [a40]=0)
declare -A QSLOTS=()   # GPUs of live jobs per queue (by job name)
declare -A PEND_PART=()
while IFS='|' read -r jid name state part gres sub; do
  [[ $name == ap-* ]] || continue
  [[ $state == RUNNING || $state == PENDING ]] || continue
  g=$(gpus_of "$gres"); ours=$((ours + g))
  NJOBS[${part%\*}]=$(( ${NJOBS[${part%\*}]:-0} + 1 ))
  QSLOTS[$name]=$(( ${QSLOTS[$name]:-0} + g ))
  [[ $state == PENDING ]] && PEND_PART[${part%\*}]=1   # one waiting job per partition at a time
done <<<"$SQ"
headroom=$(( MAX_GPUS - ours ))
(( headroom > 0 )) || exit 0

# 3. free GPUs per node right now (only nodes that accept jobs)
declare -a HOLES=()   # "part node free_gpus free_cpus"
while read -r node part state gres used cpus; do
  case $state in mix*|idle*) ;; *) continue ;; esac
  grep -qx "$node" ops/slurm/bad_nodes.txt 2>/dev/null && continue   # disk-full or otherwise broken nodes
  tot=${gres##*:}; tot=${tot%%(*}; u=${used#gpu:}; u=${u%%(*}; u=${u##*:}
  [[ $tot =~ ^[0-9]+$ && $u =~ ^[0-9]+$ ]] || continue
  IFS=/ read -r _ cidle _ _ <<<"$cpus"
  free=$(( tot - u )); (( free > 0 && cidle >= 4 )) && HOLES+=("${part%\*} $node $free $cidle")
done < <(sinfo -h -N -p dgx,l40,a40 -O "nodehost:20,partition:8,statecompact:10,gres:20,gresused:40,cpusstate:24" 2>/dev/null)
(( ${#HOLES[@]} )) || exit 0

# 4. demand: each queue with pending items gets job name ap-fill-<queue>; LoRA queues need SERVE_SUB (from items)
submit() {  # $1 queue $2 part $3 node $4 ngpu $5 cpus
  local q=$1 part=$2 node=$3 n=$4 c=$5 name="ap-fill-$(basename "$1")" env="ALL,APQ=$1"
  local subs; subs=$(cat "$q"/pending/* 2>/dev/null | awk '{print $1}' | sort -u)
  local adapters=0; for s in $subs; do [[ -d $s/adapters ]] && adapters=1; done
  if (( adapters )); then
    if [[ $(wc -w <<<"$subs") -ne 1 ]]; then log "skip $q: LoRA items from several bundles ($subs)"; return 1; fi
    env="$env,SERVE_SUB=$subs"
  fi
  if [[ $DRY == 1 ]]; then log "DRY submit $name $part $node gpu:$n cpu:$c"; return 0; fi
  local out; out=$(sbatch -J "$name" -p "$part" --qos="$part" -w "$node" --gres=gpu:$n --cpus-per-task=$c \
      --mem=$((80*n))G --time=08:00:00 --export="$env" ops/slurm/ap_worker.sbatch 2>&1)
  log "submit $name $part $node gpu:$n cpu:$c -> $out"
}
for q in ops/queue ops/queue_*; do
  [[ -d $q/pending ]] || continue
  P=$(ls "$q/pending" | wc -l); (( P > 0 )) || continue
  name="ap-fill-$(basename "$q")"
  want=$(( P - ${QSLOTS[$name]:-0} ))   # pending items not yet covered by our filler jobs for this queue
  [[ $q == ops/queue ]] && want=$(( want - ${QSLOTS[ap-worker]:-0} ))
  for h in "${HOLES[@]}"; do
    (( want > 0 && headroom > 0 )) || break
    read -r part node free cidle <<<"$h"
    [[ $free -gt 0 ]] || continue
    (( free * 4 > cidle )) && free=$(( cidle / 4 ))   # need >= 4 CPUs per GPU slot
    (( free > 0 )) || continue
    (( NJOBS[$part] < QOS_JOBS[$part] )) || continue
    [[ -z ${PEND_PART[$part]:-} ]] || continue
    n=$(( free < QOS_GPJ[$part] ? free : QOS_GPJ[$part] )); (( n > want )) && n=$want; (( n > headroom )) && n=$headroom
    (( n > 0 )) || continue
    c=$(( 12 * n < cidle ? 12 * n : cidle ))
    submit "$q" "$part" "$node" "$n" "$c" || break
    NJOBS[$part]=$(( NJOBS[$part] + 1 )); PEND_PART[$part]=1; want=$((want - n)); headroom=$((headroom - n))
    HOLES=("${HOLES[@]/#$h/$part $node $((free - n)) $((cidle - c))}")
  done
done
