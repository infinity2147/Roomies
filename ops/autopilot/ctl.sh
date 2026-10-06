#!/usr/bin/env bash
# Autopilot control. Usage: ops/autopilot/ctl.sh {install|status|pause|resume|stop|now|lb <zip> <score>|tail}
#   install : add the cron watchdog (every 10 min + @reboot) and start the daemon
#   pause   : finish the current cycle, then idle (use before working interactively with `claude`)
#   resume  : undo pause
#   stop    : stop the daemon (and keep the watchdog from restarting it); `install` to start again
#   now     : kill the inter-cycle sleep so the next cycle starts immediately
#   lb      : record a public LB score you got, e.g.  ctl.sh lb submission_2026-10-08.zip 0.15
#   tail    : follow the current cycle's tool calls
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
A=ops/autopilot; L=results/autopilot
case "$1" in
  install)
    rm -f "$A/STOP"
    line="*/10 * * * * $ROOT/$A/watchdog.sh"; boot="@reboot $ROOT/$A/watchdog.sh"
    (crontab -l 2>/dev/null | grep -v "autopilot/watchdog.sh"; echo "$line"; echo "$boot") | crontab -
    "$A/watchdog.sh"; sleep 2; "$0" status ;;
  status)
    echo "host: $(hostname -s)   cron: $(crontab -l 2>/dev/null | grep -c autopilot/watchdog.sh) entries"
    [[ -f "$L/daemon.pid" ]] && { read -r h p < "$L/daemon.pid"; echo "daemon: $h pid $p $( [[ $h == $(hostname -s) ]] && (kill -0 "$p" 2>/dev/null && echo RUNNING || echo DEAD) || echo '(other login node)')"; } || echo "daemon: not running"
    for f in STOP PAUSE; do [[ -f "$A/$f" ]] && echo "flag: $f"; done
    echo "--- last cycles (ts kind rc seconds)"; tail -5 "$L/cycles.tsv" 2>/dev/null
    echo "--- daemon log"; tail -3 "$L/daemon.log" 2>/dev/null
    echo "--- latest release"; ls -1d submissions/daily/20* 2>/dev/null | tail -1 | xargs -r -I{} sh -c 'ls {}; head -15 {}/RELEASE.md'
    echo "--- autopilot SLURM jobs"; squeue -u "$USER" -h -o "%i %j %T %M %R" 2>/dev/null ;;
  pause)  touch "$A/PAUSE"; echo "paused (current cycle finishes first)" ;;
  resume) rm -f "$A/PAUSE"; echo resumed ;;
  stop)   touch "$A/STOP"; [[ -f "$L/daemon.pid" ]] && { read -r h p < "$L/daemon.pid"; pkill -TERM -P "$p" -x sleep 2>/dev/null; }; echo "stop requested (daemon exits after the current cycle)" ;;
  now)    [[ -f "$L/daemon.pid" ]] && { read -r h p < "$L/daemon.pid"; pkill -TERM -P "$p" -x sleep && echo "woken" || echo "daemon is mid-cycle"; } ;;
  lb)     printf '%s\t%s\t%s\n' "$(date +%F)" "$2" "$3" >> "$A/lb_scores.tsv"; echo "recorded"; cat "$A/lb_scores.tsv" ;;
  tail)   f=$(ls -t "$L"/logs/*.jsonl | head -1); echo "$f"; tail -f "$f" | python3 -u -c '
import json,sys
for l in sys.stdin:
    try: e=json.loads(l)
    except Exception: continue
    for c in (e.get("message") or {}).get("content") or []:
        if isinstance(c,dict) and c.get("type")=="tool_use": print("TOOL", c["name"], json.dumps(c["input"])[:160])
        elif isinstance(c,dict) and c.get("type")=="text": print("SAY ", c["text"][:300])' ;;
  *) sed -n '2,10p' "$0" ;;
esac
