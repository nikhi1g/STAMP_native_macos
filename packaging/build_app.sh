#!/usr/bin/env bash
# Build dist/STAMP.app with PyInstaller (Apple Silicon only). Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
uv run pyinstaller packaging/STAMP.spec --noconfirm --clean --distpath dist --workpath build
# Sparkle 2 for in-app updates. STAMP is not sandboxed, so Sparkle's XPC services are not needed
SPARKLE=$(packaging/fetch_sparkle.sh)
ditto "$SPARKLE/Sparkle.framework" dist/STAMP.app/Contents/Frameworks/Sparkle.framework
/bin/rm -rf dist/STAMP.app/Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices dist/STAMP.app/Contents/Frameworks/Sparkle.framework/XPCServices
echo "built: $PWD/dist/STAMP.app"
