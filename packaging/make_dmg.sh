#!/usr/bin/env bash
# Package dist/STAMP.app (+ upstream examples and the user's guide) into dist/STAMP.dmg.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d dist/STAMP.app ] || { echo "dist/STAMP.app missing; run packaging/build_app.sh first" >&2; exit 1; }
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/stamp-dmg.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
cp -R dist/STAMP.app "$STAGE/STAMP.app"
cp -R stamp/examples "$STAGE/examples"
cp stamp/manual/STAMP_Users_Guide.pdf "$STAGE/STAMP_Users_Guide.pdf"
cp stamp/LICENSE.txt "$STAGE/LICENSE.txt"
ln -s /Applications "$STAGE/Applications"
rm -f dist/STAMP.dmg
hdiutil create -volname "STAMP 2.1.3" -srcfolder "$STAGE" -ov -format UDZO dist/STAMP.dmg >/dev/null
echo "built: $PWD/dist/STAMP.dmg"
