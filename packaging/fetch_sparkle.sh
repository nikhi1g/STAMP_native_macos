#!/usr/bin/env bash
# Fetch the pinned Sparkle 2 release into build/vendor/sparkle (framework + signing tools). Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
VER=2.10.0
SHA=c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c
DIR=build/vendor; TAR=$DIR/Sparkle-$VER.tar.xz
mkdir -p "$DIR"
[ -f "$TAR" ] || curl -sSL -o "$TAR" "https://github.com/sparkle-project/Sparkle/releases/download/$VER/Sparkle-$VER.tar.xz"
echo "$SHA  $TAR" | shasum -a 256 -c - >/dev/null || { echo "Sparkle archive checksum mismatch" >&2; exit 1; }
[ -d "$DIR/sparkle/Sparkle.framework" ] || { mkdir -p "$DIR/sparkle" && tar -xf "$TAR" -C "$DIR/sparkle"; }
echo "$PWD/$DIR/sparkle"
