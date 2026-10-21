#!/usr/bin/env bash
# Build, sign (Developer ID, hardened runtime, secure timestamp), notarize and staple STAMP,
# then package dist/STAMP-<version>.dmg (signed, notarized, stapled) + its SHA-256.
#   packaging/sign_notarize.sh            full run
#   SKIP_NOTARIZE=1 packaging/sign_notarize.sh   sign + local checks only (no upload)
# Env: SIGN_ID (default: the team's Developer ID Application cert), NOTARY_PROFILE (default STAMP,
# created once with `xcrun notarytool store-credentials STAMP ...`), ENTITLEMENTS (optional plist).
set -euo pipefail
cd "$(dirname "$0")/.."
SIGN_ID=${SIGN_ID:-"Developer ID Application: NIKHIL GUPTA (G7955Z5DNB)"}
PROFILE=${NOTARY_PROFILE:-STAMP}
APP=dist/STAMP.app
LOGDIR=build/signing; mkdir -p "$LOGDIR"
ENT_ARGS=(); [ -n "${ENTITLEMENTS:-}" ] && ENT_ARGS=(--entitlements "$ENTITLEMENTS")
sign() { codesign --force --options runtime --timestamp --sign "$SIGN_ID" "$@"; }
notarize() {   # $1 = file to submit; logs result JSON + Apple's log
  local out; out=$(xcrun notarytool submit "$1" --keychain-profile "$PROFILE" --wait --output-format json)
  echo "$out" > "$LOGDIR/$(basename "$1").submit.json"
  local id status; id=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' <<<"$out")
  status=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])' <<<"$out")
  xcrun notarytool log "$id" --keychain-profile "$PROFILE" "$LOGDIR/$(basename "$1").notary-log.json" >/dev/null
  echo "notarization of $(basename "$1"): $status (id $id)"
  [ "$status" = Accepted ] || { echo "see $LOGDIR/$(basename "$1").notary-log.json" >&2; exit 1; }
}

/usr/bin/security find-identity -v -p codesigning | grep -qF "$SIGN_ID" || { echo "signing identity not found: $SIGN_ID" >&2; exit 1; }
[ -n "${SKIP_NOTARIZE:-}" ] || xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null \
  || { echo "notary profile '$PROFILE' missing; run xcrun notarytool store-credentials" >&2; exit 1; }

packaging/build_app.sh
VERSION=$(defaults read "$PWD/$APP/Contents/Info" CFBundleShortVersionString)
BUILD=$(defaults read "$PWD/$APP/Contents/Info" CFBundleVersion)
NAME=STAMP-$VERSION-$BUILD${STAMP_NAME_SUFFIX:-}

echo "signing nested code (inside-out)..."
# every Mach-O file except the main executable: independent of each other, so 8 at a time
# (each signature waits on Apple's timestamp server)
python3 - "$APP" <<'PY' | xargs -0 -n 4 -P 8 codesign --force --options runtime --timestamp --sign "$SIGN_ID" 2>&1 | grep -v "replacing existing signature" || true
import os, sys
app = sys.argv[1]; main = os.path.join(app, 'Contents', 'MacOS', 'STAMP')
MAGIC = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
for root, dirs, files in os.walk(os.path.join(app, 'Contents')):
    for f in files:
        p = os.path.join(root, f)
        if p == main or os.path.islink(p):
            continue
        with open(p, 'rb') as fh:
            if fh.read(4) in MAGIC:
                sys.stdout.write(p + '\0')
PY
# framework / nested bundles, deepest first
while IFS= read -r b; do sign "$b" >/dev/null; done \
  < <(find "$APP/Contents" -type d \( -name "*.framework" -o -name "*.app" \) | awk '{print gsub("/","/"), $0}' | sort -rn | cut -d' ' -f2-)
sign ${ENT_ARGS[@]+"${ENT_ARGS[@]}"} "$APP"
codesign --verify --strict --deep --verbose=2 "$APP"
packaging/smoke_app.sh 90

if [ -z "${SKIP_NOTARIZE:-}" ]; then
  ditto -c -k --keepParent "$APP" "$LOGDIR/STAMP.zip"
  notarize "$LOGDIR/STAMP.zip"
  xcrun stapler staple "$APP"
  spctl -a -t exec -vv "$APP"
fi

# main download: zip of the stapled app (Safari unzips it; the app offers to move itself to Applications)
# no AppleDouble (._*) entries: Archive Utility would write them into framework roots and break the seal
xattr -cr "$APP"
ditto -c -k --norsrc --noextattr --noacl --keepParent "$APP" "dist/$NAME.zip"
unzip -l "dist/$NAME.zip" | grep -q '/\._' && { echo "zip contains AppleDouble entries" >&2; exit 1; }
shasum -a 256 "dist/$NAME.zip" | tee "dist/$NAME.zip.sha256"

# DMG (secondary download): skipped with NO_DMG=1 (packaging/release.sh builds it in parallel with the pkg)
[ -n "${NO_DMG:-}" ] || packaging/make_release_dmg.sh
echo "done: $PWD/dist/$NAME.zip"
