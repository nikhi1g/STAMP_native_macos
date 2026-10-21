#!/usr/bin/env bash
# Build dist/STAMP-<version>-<build>.dmg from the signed, stapled dist/STAMP.app; sign, notarize, staple.
set -euo pipefail
cd "$(dirname "$0")/.."
SIGN_ID=${SIGN_ID:-"Developer ID Application: NIKHIL GUPTA (G7955Z5DNB)"}
PROFILE=${NOTARY_PROFILE:-STAMP}
APP=dist/STAMP.app; LOGDIR=build/signing; mkdir -p "$LOGDIR"
NAME=STAMP-$(defaults read "$PWD/$APP/Contents/Info" CFBundleShortVersionString)-$(defaults read "$PWD/$APP/Contents/Info" CFBundleVersion)${STAMP_NAME_SUFFIX:-}
packaging/make_dmg.sh
DMG=dist/$NAME.dmg
mv -f dist/STAMP.dmg "$DMG"
codesign --force --timestamp --sign "$SIGN_ID" "$DMG"
if [ -z "${SKIP_NOTARIZE:-}" ]; then
  out=$(xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait --output-format json)
  echo "$out" > "$LOGDIR/$(basename "$DMG").submit.json"
  st=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])' <<<"$out")
  echo "notarization of $(basename "$DMG"): $st"; [ "$st" = Accepted ] || exit 1
  xcrun stapler staple "$DMG"; xcrun stapler validate "$DMG"
  spctl -a -t open --context context:primary-signature -vv "$DMG"
fi
shasum -a 256 "$DMG" | tee "$DMG.sha256"
