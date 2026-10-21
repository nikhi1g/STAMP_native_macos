#!/bin/bash
# Opens STAMP (Windows build via Porting Kit / Wine, lab-manual pathway).
# Finds the Porting Kit wrapper (an app containing wineskinlauncher), wherever it was installed.
is_wrapper() { [ -x "$1/Contents/MacOS/wineskinlauncher" ]; }
for p in "$HOME/Applications/Porting Kit Library/STAMP.app" "/Applications/Porting Kit Library/STAMP.app" \
         "$HOME/Applications/STAMP.app" "/Applications/STAMP.app"; do
  is_wrapper "$p" && { open "$p"; exit 0; }
done
while IFS= read -r p; do
  case "$p" in */T/*|*/.Trash/*) continue ;; esac
  is_wrapper "$p" && { open "$p"; exit 0; }
done < <(mdfind 'kMDItemFSName == "STAMP.app"')
echo "STAMP wrapper not found. Open Porting Kit -> Library -> STAMP." >&2; read -r -p "Press Enter to close." _; exit 1
