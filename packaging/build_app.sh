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
# update prompt: just "A new version of STAMP is available!" and the release notes; drop Sparkle's
# "<app> <new> is now available—you have <old>. Would you like to download it now?" line
python3 - dist/STAMP.app/Contents/Frameworks/Sparkle.framework/Versions/B/Resources/Base.lproj/Sparkle.strings <<'PY'
import plistlib, sys
p = sys.argv[1]
with open(p, 'rb') as f:
    strings = plistlib.load(f)
keys = [k for k in strings if 'is now available—you have' in k]
assert len(keys) >= 2, keys
for k in keys:
    strings[k] = ''
with open(p, 'wb') as f:
    plistlib.dump(strings, f, fmt=plistlib.FMT_BINARY)
PY
echo "built: $PWD/dist/STAMP.app"
