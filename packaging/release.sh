#!/usr/bin/env bash
# One command for builds. Run the test gate separately first:  uv run pytest -q
#   packaging/release.sh          release: app + zip (notarized) -> DMG and pkg in parallel -> zip check -> appcast
#   packaging/release.sh --dev    development: notarized app + zip only (fastest realistic test build)
# Staging test builds: STAMP_CHANNEL=staging STAMP_FEED_BASE=https://<staging>/stamp STAMP_BUILD=4 packaging/release.sh
# Logs: build/signing/{app,dmg,pkg}.log
set -euo pipefail
cd "$(dirname "$0")/.."
L=build/signing; mkdir -p "$L"
START=$(date +%s)
NO_DMG=1 packaging/sign_notarize.sh > "$L/app.log" 2>&1 || { tail -20 "$L/app.log"; exit 1; }
NAME=STAMP-$(defaults read "$PWD/dist/STAMP.app/Contents/Info" CFBundleShortVersionString)-$(defaults read "$PWD/dist/STAMP.app/Contents/Info" CFBundleVersion)
grep -E "notarization of|^[0-9a-f]{64}" "$L/app.log"
[ -n "${SKIP_NOTARIZE:-}" ] || packaging/verify_zip.sh "dist/$NAME.zip" | tail -1
if [ "${1:-}" != "--dev" ]; then
  packaging/make_release_dmg.sh > "$L/dmg.log" 2>&1 & D=$!
  packaging/make_pkg.sh > "$L/pkg.log" 2>&1 & P=$!
  wait $D || { tail -20 "$L/dmg.log"; exit 1; }
  wait $P || { tail -20 "$L/pkg.log"; exit 1; }
  grep -hE "notarization of|^[0-9a-f]{64}" "$L/dmg.log" "$L/pkg.log"
  packaging/make_appcast.sh | tail -1
  # final artifacts, kept apart from later development builds that reuse the dist/ names
  OUT=dist/release/${STAMP_CHANNEL:-production}/${NAME#STAMP-}; mkdir -p "$OUT"
  cp -p "dist/$NAME".{zip,dmg,pkg} "dist/$NAME".{zip,dmg,pkg}.sha256 dist/appcast.xml "$OUT/"
  echo "release files: $PWD/$OUT"
fi
echo "done in $(( ($(date +%s) - START) / 60 )) min $(( ($(date +%s) - START) % 60 )) s"
