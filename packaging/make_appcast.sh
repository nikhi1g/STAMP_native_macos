#!/usr/bin/env bash
# Add dist/STAMP-<version>-<build>.zip to the Sparkle feed. Keeps every earlier item: the committed
# packaging/appcast/appcast.xml is the source of truth; the result is written back there and to dist/.
# Signs with the EdDSA key in the login keychain (created once with Sparkle's generate_keys).
# Release notes: packaging/release_notes/STAMP-<version>-<build>.md (required).
# Upload order for the release owner: the zip to https://www.mimg.io/download/stamp/updates/<zip name>
# (immutable), verify its SHA-256, then replace https://www.mimg.io/download/stamp/appcast.xml last.
set -euo pipefail
cd "$(dirname "$0")/.."
APP=dist/STAMP.app
VERSION=$(defaults read "$PWD/$APP/Contents/Info" CFBundleShortVersionString)
BUILD=$(defaults read "$PWD/$APP/Contents/Info" CFBundleVersion)
NAME=STAMP-$VERSION-$BUILD
[ -f "dist/$NAME.zip" ] || { echo "dist/$NAME.zip missing; run packaging/sign_notarize.sh" >&2; exit 1; }
NOTES=packaging/release_notes/$NAME.md
[ -f "$NOTES" ] || { echo "write $NOTES first" >&2; exit 1; }
SPARKLE=$(packaging/fetch_sparkle.sh)
STAGE=build/appcast; /bin/rm -rf "$STAGE"; mkdir -p "$STAGE"
[ -f packaging/appcast/appcast.xml ] && cp packaging/appcast/appcast.xml "$STAGE/"
cp "dist/$NAME.zip" "$STAGE/"; cp "$NOTES" "$STAGE/$NAME.md"
"$SPARKLE/bin/generate_appcast" --download-url-prefix "https://www.mimg.io/download/stamp/updates/" \
  --embed-release-notes --maximum-deltas 0 "$STAGE"
cp "$STAGE/appcast.xml" packaging/appcast/appcast.xml
cp "$STAGE/appcast.xml" dist/appcast.xml
grep -q "sparkle:edSignature" dist/appcast.xml || { echo "appcast has no EdDSA signature" >&2; exit 1; }
echo "appcast: $PWD/dist/appcast.xml (item for $NAME added)"
