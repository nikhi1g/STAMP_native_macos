#!/usr/bin/env bash
# Launch dist/STAMP.app for a few seconds and report what it logged.
# Exit 0 if the app stayed alive and logged no unhandled exception.
#   packaging/smoke_app.sh [seconds]   (default 12)
# Logs: stderr -> build/app_smoke.log; the app itself -> ~/Library/Logs/STAMP/STAMP.log
set -uo pipefail
cd "$(dirname "$0")/.."
SECS=${1:-12}
APP=dist/STAMP.app/Contents/MacOS/STAMP
LOG=$HOME/Library/Logs/STAMP/STAMP.log
[ -x "$APP" ] || { echo "missing $APP; run packaging/build_app.sh" >&2; exit 2; }
mkdir -p build; : > build/app_smoke.log
START=$(date +%s)
"$APP" > build/app_smoke.log 2>&1 &
PID=$!
sleep "$SECS"
if kill -0 "$PID" 2>/dev/null; then ALIVE=1; kill "$PID"; else ALIVE=0; fi
echo "--- app stderr (build/app_smoke.log, Qt size-hint noise removed)"
grep -v "propagateSizeHints\|QtWarningMsg" build/app_smoke.log
echo "--- $LOG (this run)"
[ -f "$LOG" ] && awk -v s="$(date -r "$START" '+%Y-%m-%d %H:%M')" '$0 >= s' "$LOG"
if [ "$ALIVE" = 1 ] && ! grep -q "Unhandled exception" build/app_smoke.log; then
  echo "OK: alive after ${SECS}s, no unhandled exception"; exit 0
fi
echo "FAIL: alive=$ALIVE (see logs above)"; exit 1
