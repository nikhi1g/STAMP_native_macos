#!/usr/bin/env bash
# Check a release zip the way a Chrome/Firefox user gets it: quarantined download, extracted by
# macOS's Archive Utility (not ditto), then Gatekeeper + stapler on the extracted app.
#   packaging/verify_zip.sh dist/STAMP-<version>-<build>.zip
set -euo pipefail
ZIP=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
T=$(mktemp -d "${TMPDIR:-/tmp}/stamp-zipcheck.XXXXXX"); trap '/bin/rm -rf "$T"' EXIT
cp "$ZIP" "$T/"; Z="$T/$(basename "$ZIP")"
xattr -w com.apple.quarantine "0081;$(printf %x "$(date +%s)");Google Chrome;$(uuidgen)" "$Z"
open -W -g -a "/System/Library/CoreServices/Applications/Archive Utility.app" "$Z"
A="$T/STAMP.app"; [ -d "$A" ] || { echo "Archive Utility produced no STAMP.app" >&2; ls "$T" >&2; exit 1; }
xattr -p com.apple.quarantine "$A" >/dev/null && echo "quarantine propagated: yes"
find "$A" -name '._*' | head -3 | grep . && { echo "AppleDouble files in extracted app" >&2; exit 1; }
codesign --verify --strict --deep "$A"
xcrun stapler validate "$A" | tail -1
spctl -a -t exec -vv "$A"
echo "OK: Archive Utility extraction is notarized and intact"
