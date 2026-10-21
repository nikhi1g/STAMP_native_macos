#!/usr/bin/env bash
# Launch dist/STAMP.app and wait until it logs "Main window shown" (plugins loaded,
# window up) or an unhandled exception, then report what it logged.
# Exit 0 only when the ready line appeared and no "Unhandled exception" was logged.
#   packaging/smoke_app.sh [max seconds]   (default 60; the first launch builds the
#   matplotlib font cache, ~5-10 s)
# Logs: stderr -> build/app_smoke.log; the app itself -> ~/Library/Logs/STAMP/STAMP.log
set -uo pipefail
cd "$(dirname "$0")/.."
MAX=${1:-60}
APP=dist/STAMP.app/Contents/MacOS/STAMP
LOG=$HOME/Library/Logs/STAMP/STAMP.log
[ -x "$APP" ] || { echo "missing $APP; run packaging/build_app.sh" >&2; exit 2; }
mkdir -p build; : > build/app_smoke.log
START=$(date +%s)
"$APP" > build/app_smoke.log 2>&1 &
PID=$!
STATUS=timeout
for _ in $(seq "$MAX"); do
  sleep 1
  if grep -q "Unhandled exception" build/app_smoke.log; then STATUS=exception; break; fi
  if grep -q "Main window shown" build/app_smoke.log; then STATUS=ready; break; fi
  if ! kill -0 "$PID" 2>/dev/null; then STATUS=exited; break; fi
done
ELAPSED=$(( $(date +%s) - START ))
kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
echo "--- app stderr (build/app_smoke.log, Qt size-hint noise removed)"
grep -v "propagateSizeHints\|QtWarningMsg" build/app_smoke.log
echo "--- log file: $LOG"
if [ "$STATUS" = ready ]; then
  echo "OK: main window shown after ${ELAPSED}s, no unhandled exception"; exit 0
fi
echo "FAIL: $STATUS after ${ELAPSED}s (see logs above)"; exit 1
