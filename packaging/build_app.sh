#!/usr/bin/env bash
# Build dist/STAMP.app with PyInstaller (Apple Silicon only). Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
uv run pyinstaller packaging/STAMP.spec --noconfirm --clean --distpath dist --workpath build
echo "built: $PWD/dist/STAMP.app"
