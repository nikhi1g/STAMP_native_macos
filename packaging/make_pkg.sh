#!/usr/bin/env bash
# Build dist/STAMP-<version>.pkg from the signed, notarized, stapled dist/STAMP.app:
# installs STAMP.app into /Applications. Signs with Developer ID Installer, notarizes, staples.
#   packaging/make_pkg.sh            full run (run packaging/sign_notarize.sh first)
#   SKIP_NOTARIZE=1 packaging/make_pkg.sh
set -euo pipefail
cd "$(dirname "$0")/.."
INST_ID=${INSTALLER_ID:-"Developer ID Installer: NIKHIL GUPTA (G7955Z5DNB)"}
PROFILE=${NOTARY_PROFILE:-STAMP}
APP=dist/STAMP.app
LOGDIR=build/signing; mkdir -p "$LOGDIR"
/usr/bin/security find-identity -v | grep -qF "$INST_ID" || { echo "installer identity not found: $INST_ID" >&2; exit 1; }
xcrun stapler validate "$APP" >/dev/null || { echo "$APP is not stapled; run packaging/sign_notarize.sh" >&2; exit 1; }
VERSION=$(defaults read "$PWD/$APP/Contents/Info" CFBundleShortVersionString)
ID=$(defaults read "$PWD/$APP/Contents/Info" CFBundleIdentifier)
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/stamp-pkg.XXXXXX"); trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/root/Applications"
ditto "$APP" "$STAGE/root/Applications/STAMP.app"
# component plist: install exactly where we say (no relocation to an older copy elsewhere)
pkgbuild --analyze --root "$STAGE/root" "$STAGE/comp.plist" >/dev/null
plutil -replace 0.BundleIsRelocatable -bool NO "$STAGE/comp.plist"
pkgbuild --root "$STAGE/root" --component-plist "$STAGE/comp.plist" --identifier "$ID.pkg" \
  --version "$VERSION" --install-location / "$STAGE/STAMP-component.pkg"
cat > "$STAGE/distribution.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>STAMP $VERSION</title>
  <options customize="never" require-scripts="false" hostArchitectures="arm64"/>
  <domains enable_localSystem="true"/>
  <volume-check><allowed-os-versions><os-version min="12.0"/></allowed-os-versions></volume-check>
  <choices-outline><line choice="default"><line choice="$ID.pkg"/></line></choices-outline>
  <choice id="default"/>
  <choice id="$ID.pkg" visible="false"><pkg-ref id="$ID.pkg"/></choice>
  <pkg-ref id="$ID.pkg" version="$VERSION" onConclusion="none">STAMP-component.pkg</pkg-ref>
</installer-gui-script>
XML
PKG=dist/STAMP-$VERSION.pkg
productbuild --distribution "$STAGE/distribution.xml" --package-path "$STAGE" --sign "$INST_ID" --timestamp "$PKG"
pkgutil --check-signature "$PKG"
if [ -z "${SKIP_NOTARIZE:-}" ]; then
  out=$(xcrun notarytool submit "$PKG" --keychain-profile "$PROFILE" --wait --output-format json)
  echo "$out" > "$LOGDIR/$(basename "$PKG").submit.json"
  sid=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' <<<"$out")
  st=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])' <<<"$out")
  xcrun notarytool log "$sid" --keychain-profile "$PROFILE" "$LOGDIR/$(basename "$PKG").notary-log.json" >/dev/null
  echo "notarization of $(basename "$PKG"): $st (id $sid)"; [ "$st" = Accepted ] || exit 1
  xcrun stapler staple "$PKG"; xcrun stapler validate "$PKG"
  spctl -a -t install -vv "$PKG"
fi
shasum -a 256 "$PKG" | tee "$PKG.sha256"
echo "done: $PWD/$PKG"
