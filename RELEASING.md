# Releasing STAMP

GitHub is the source of truth for releases. The website and every installed copy follow it.

```
development ──merge──▶ main ──tag vX.Y.Z──▶ GitHub Release ──sync──▶ mimg.io (R2 + download page + feed)
  (work)              (released code)       (signed files + feed)      ──▶ installed apps update themselves
```

## Branches
- `development`: day-to-day work. Tests must pass before merging.
- `main`: exactly what is released. Every release is a tag `vX.Y.Z` on `main`.

## Versions
Semantic `major.minor.patch` (e.g. 2.1.5): patch for fixes, minor for features, major for breaking
changes. The version is the only number users see and the only one the updater compares.

## Cutting a release (about 15 minutes)
1. Write `packaging/release_notes/STAMP-X.Y.Z.md` (shown in the update prompt).
2. Merge `development` into `main`.
3. `uv run pytest -q` (test gate).
4. `STAMP_VERSION=X.Y.Z packaging/release.sh`: builds, signs (Developer ID), notarizes and staples
   the app, zip, pkg and dmg; verifies the zip as a browser download would; adds the release to the
   signed update feed. Output: `dist/release/production/X.Y.Z/`.
5. `packaging/publish_github.sh X.Y.Z`: tags `vX.Y.Z`, pushes `main`, creates the GitHub Release with
   the zip, pkg, dmg, their `.sha256` files and `appcast.xml`.
6. The website syncs the release from GitHub: uploads the files to their fixed URL
   `https://www.mimg.io/download/stamp/X.Y.Z/`, checks every SHA-256 through the public URL, updates
   the download page, and replaces `https://www.mimg.io/download/stamp/appcast.xml` last.
7. Within 24 hours every installed STAMP offers the update (or at once via Check for Updates).

## Channels
- Production: `https://www.mimg.io/download/stamp/` (students). Built by default.
- Staging: `https://mimg-109bl-staging.gptminimal.workers.dev/download/stamp/` for testing updates
  before students see them: `STAMP_CHANNEL=staging STAMP_FEED_BASE=<staging base> STAMP_VERSION=X.Y.Z
  packaging/release.sh --dev` then `packaging/make_appcast.sh`.
- Each build only follows its own channel. To move a copy between channels, replace the app.

## Secrets (on the release Mac only, never in the repo)
- Developer ID Application and Developer ID Installer certificates (keychain)
- Notarization credentials: keychain profile `STAMP` (`xcrun notarytool store-credentials`)
- Sparkle EdDSA private key (keychain; back it up with Sparkle's `generate_keys -x`). Losing it
  means installed copies can no longer be updated.
