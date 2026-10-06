#!/usr/bin/env bash
# Cron watchdog (every 10 min + @reboot): (re)starts the autopilot daemon if it is not running on this host.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
L=results/autopilot; mkdir -p "$L"
[[ -f ops/autopilot/STOP ]] && exit 0
if [[ -f "$L/daemon.pid" ]]; then
  read -r host pid < "$L/daemon.pid"
  if [[ "$host" != "$(hostname -s)" ]]; then exit 0; fi   # owned by the other login node
  if kill -0 "$pid" 2>/dev/null && grep -q "autopilot/daemon.sh" "/proc/$pid/cmdline" 2>/dev/null; then exit 0; fi
fi
echo "$(date '+%F %T') watchdog: starting daemon on $(hostname -s)" >> "$L/daemon.log"
setsid nohup bash "$ROOT/ops/autopilot/daemon.sh" >> "$L/daemon.out" 2>&1 < /dev/null &
