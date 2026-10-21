#!/bin/bash
# STAMP launcher (Windows build via Porting Kit / Wine, lab-manual pathway).
# Opens STAMP, then stays open as a small control panel: Enter or Q quits STAMP and closes this window.
is_wrapper() { [ -x "$1/Contents/MacOS/wineskinlauncher" ]; }
running() { pgrep -f 'STAMP\\STAMP.exe' >/dev/null; }
close_window() {   # close this Terminal window after the script exits (avoids the "terminate?" prompt)
  ( sleep 0.5; osascript -e 'tell application "Terminal" to close (every window whose name contains "STAMP.command")' ) >/dev/null 2>&1 &
  disown; exit "${1:-0}"
}
fail() { echo "$1" >&2; read -r -p "Press Enter to close." _; close_window 1; }

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
[ -n "$W" ] || fail "STAMP wrapper not found. Open Porting Kit -> Library -> STAMP."

end_wine() {   # end this wrapper's Wine session (wineserver, winedevice, launcher)
  pkill -TERM -f "$W/Contents/" 2>/dev/null; pkill -TERM -f 'C:\\windows\\system32\\winedevice.exe' 2>/dev/null
  sleep 1; pkill -9 -f "$W/Contents/" 2>/dev/null; pkill -9 -f 'STAMP\\STAMP.exe' 2>/dev/null
  pkill -9 -f 'C:\\windows\\system32\\winedevice.exe' 2>/dev/null   # these ignore TERM
}

stop_stamp() {
  echo "Quitting STAMP..."
  pkill -TERM -f 'STAMP\\STAMP.exe' 2>/dev/null
  for _ in $(seq 1 10); do running || break; sleep 0.5; done
  end_wine
  echo "STAMP closed."
}

if running; then
  open "$W"                                    # already running: bring it forward
else
  # Leftovers from a force-quit (wineserver, winedevice) make the next launch exit silently.
  pkill -f "$W/Contents/" 2>/dev/null; sleep 1; pkill -9 -f "$W/Contents/" 2>/dev/null
  pkill -9 -f 'C:\\windows\\system32\\winedevice.exe' 2>/dev/null
  open "$W"
  printf "Starting STAMP (Wine takes ~10-20 s)"
  for _ in $(seq 1 40); do running && break; printf "."; sleep 1; done; echo
  running || fail "STAMP did not start. Try Porting Kit -> Library -> STAMP."
fi

clear
cat <<'TXT'
  ┌──────────────────────────────────────────┐
  │  STAMP is running                        │
  │                                          │
  │  [Enter] or [Q]  quit STAMP and close    │
  │  closing STAMP's window also closes this │
  └──────────────────────────────────────────┘
TXT
trap 'stop_stamp; close_window 0' INT TERM HUP
while running; do
  if read -r -s -n 1 -t 1 key; then
    case "$key" in ""|q|Q) stop_stamp; close_window 0 ;; esac
  fi
done
echo "STAMP was closed."
end_wine
close_window 0
