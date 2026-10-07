#!/usr/bin/env bash
# Autopilot daemon: runs headless Claude Code cycles forever on the Prajna login node (which has internet;
# GPU work is delegated to SLURM jobs). Once per day (after RELEASE_HOUR, local time) the cycle is a
# "release" cycle that builds submissions/daily/<date>/submission.zip; every other cycle is a "work" cycle.
# Started/restarted by ops/autopilot/watchdog.sh (cron). Control files: ops/autopilot/{STOP,PAUSE}.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
export PATH="$HOME/.local/bin:/opt/slurm/bin:/usr/local/bin:/usr/bin:/bin" HOME="${HOME:-/home/fmr-group/24b4518}"
A=ops/autopilot; L=results/autopilot
CYCLE_GAP_MIN="${CYCLE_GAP_MIN:-120}"     # minimum minutes between cycle starts (budget: ≤10-20% of each 5 h usage window)
CYCLE_TIMEOUT="${CYCLE_TIMEOUT:-30m}"     # hard cap per cycle
RELEASE_HOUR="${RELEASE_HOUR:-9}"         # release cycle once per day after this hour (IST)
mkdir -p "$L/logs" submissions/daily
echo "$(hostname -s) $$" > "$L/daemon.pid"
log() { echo "$(date '+%F %T') $*" >> "$L/daemon.log"; }
log "daemon start pid $$"

while true; do
  date +%s > "$L/heartbeat"
  if [[ -f "$A/STOP" ]]; then log "STOP file found, exiting"; rm -f "$L/daemon.pid"; exit 0; fi
  if [[ -f "$A/PAUSE" ]]; then sleep 300; continue; fi

  today=$(date +%F)
  if (( 10#$(date +%H) >= RELEASE_HOUR )) && [[ ! -f "submissions/daily/$today/RELEASE.md" ]]; then kind=release; else kind=work; fi
  ts=$(date +%Y%m%d-%H%M%S); out="$L/logs/$ts-$kind"
  prompt="$(cat "$A/CHARTER.md" "$A/prompts/$kind.md")
(Cycle $ts, kind=$kind, now $(date '+%F %T %Z'). Today's release dir: submissions/daily/$today/)"
  log "cycle $ts $kind start"
  t0=$(date +%s)
  timeout --kill-after=120 "$CYCLE_TIMEOUT" claude -p "$prompt" --model "${AP_MODEL:-claude-sonnet-5-5}" ${AP_CLAUDE_FLAGS:---dangerously-skip-permissions} \
      --output-format stream-json --verbose > "$out.jsonl" 2> "$out.err" < /dev/null
  rc=$?; dt=$(( $(date +%s) - t0 ))
  # final assistant summary -> .txt (last "result" event of the stream)
  python3 - "$out.jsonl" > "$out.txt" 2>/dev/null <<'PY'
import json, sys
res = None
for line in open(sys.argv[1]):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "result": res = e
if res: print(res.get("result") or res.get("subtype"), f"\n[cost_usd={res.get('total_cost_usd')} turns={res.get('num_turns')}]")
PY
  printf '%s\t%s\t%s\t%s\n' "$ts" "$kind" "$rc" "$dt" >> "$L/cycles.tsv"
  log "cycle $ts $kind end rc=$rc ${dt}s"

  # quick failure (usage limit / auth / network) -> back off; otherwise keep the cycle cadence
  if (( rc != 0 && dt < 300 )); then sleep 1800
  else rest=$(( CYCLE_GAP_MIN * 60 - dt )); (( rest > 0 )) && sleep "$rest"; fi
done
