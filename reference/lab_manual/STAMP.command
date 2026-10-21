#!/bin/bash
# Opens STAMP (Windows build via Porting Kit / Wine, lab-manual pathway).
is_wrapper() { [ -x "$1/Contents/MacOS/wineskinlauncher" ]; }
W=""
for p in "$HOME/Applications/STAMP.app" "$HOME/Applications/Porting Kit Library/STAMP.app" \
         "/Applications/Porting Kit Library/STAMP.app" "/Applications/STAMP.app"; do
  is_wrapper "$p" && { W=$p; break; }
done
if [ -z "$W" ]; then
  while IFS= read -r p; do
    case "$p" in */T/*|*/.Trash/*) continue ;; esac
    is_wrapper "$p" && { W=$p; break; }
  done < <(mdfind 'kMDItemFSName == "STAMP.app"')
fi
[ -n "$W" ] || { echo "STAMP wrapper not found. Open Porting Kit -> Library -> STAMP." >&2; read -r -p "Press Enter to close." _; exit 1; }

if pgrep -f 'STAMP\\STAMP.exe' >/dev/null; then
  open "$W"                                  # already running: bring it forward
else
  # Leftovers from a force-quit (wineserver, winedevice) make the next launch exit silently.
  pkill -f "$W/Contents/" 2>/dev/null; sleep 1; pkill -9 -f "$W/Contents/" 2>/dev/null
  pkill -f 'C:\\windows\\system32\\winedevice.exe' 2>/dev/null
  open "$W"
  echo "Starting STAMP (Wine takes ~10-20 s)..."
  for _ in $(seq 1 40); do pgrep -f 'STAMP\\STAMP.exe' >/dev/null && break; sleep 1; done
  pgrep -f 'STAMP\\STAMP.exe' >/dev/null || { echo "STAMP did not start. Try Porting Kit -> Library -> STAMP." >&2; read -r -p "Press Enter to close." _; exit 1; }
fi
osascript -e 'tell application "Terminal" to close (every window whose name contains "STAMP.command")' >/dev/null 2>&1 &
exit 0
