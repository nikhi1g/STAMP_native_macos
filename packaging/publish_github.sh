#!/usr/bin/env bash
# Publish a built production release to GitHub. GitHub is the source of truth for releases: the
# website (mimg.io) syncs from the GitHub release (see RELEASING.md).
#   packaging/publish_github.sh 2.1.5
# Needs: dist/release/production/<version>/ from `STAMP_VERSION=<version> packaging/release.sh`.
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?version, e.g. 2.1.5}
R=dist/release/production/$V
REPO=nikhi1g/STAMP_native_macos
for f in "$R"/STAMP-$V.{zip,pkg,dmg} "$R/appcast.xml"; do [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }; done
[ "$(git config user.name)" = nikhi1g ] || { echo "git user must be nikhi1g (AGENTS.md)" >&2; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "release from main (merge development first)" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean" >&2; exit 1; }
for f in "$R"/*.sha256; do sed -i '' 's#dist/##' "$f"; done	# plain file names, for shasum -c
(cd "$R" && for f in *.sha256; do shasum -a 256 -c "$f" >/dev/null; done)
git tag -a "v$V" -m "STAMP $V for macOS (Apple Silicon)"
git push -q origin main "v$V"
NOTES=$(mktemp); trap '/bin/rm -f "$NOTES"' EXIT
{ sed '1d' "packaging/release_notes/STAMP-$V.md"; echo
  echo "**Install:** download **STAMP-$V.zip**, open it, open STAMP, click **Open**, then **Move to Applications**."
  echo "Installed copies update themselves (STAMP menu > Check for Updates)."; echo
  echo "**Requirements:** Apple Silicon Mac (M1 or later), macOS 12 or later."; echo
  echo "| File | SHA-256 |"; echo "|---|---|"
  for x in zip pkg dmg; do echo "| STAMP-$V.$x | \`$(cut -d' ' -f1 "$R/STAMP-$V.$x.sha256")\` |"; done; echo
  echo "Signed with Developer ID (NIKHIL GUPTA, G7955Z5DNB) and notarized by Apple. \`appcast.xml\` is the update feed for this release."; echo
  echo "STAMP is free software under the GNU GPL v3. Original STAMP (c) 2011-2015 Donovan Parks and Robert Beiko; macOS port (c) 2026 Nikhil Gupta."
} > "$NOTES"
gh release create "v$V" --repo "$REPO" --title "STAMP $V for macOS" --notes-file "$NOTES" --latest \
  "$R"/STAMP-$V.{zip,pkg,dmg} "$R"/STAMP-$V.{zip,pkg,dmg}.sha256 "$R/appcast.xml"
echo "published: https://github.com/$REPO/releases/tag/v$V"
