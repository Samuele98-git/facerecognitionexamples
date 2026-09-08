#!/usr/bin/env bash
# One-time model fetch for OFFLINE operation (Linux/macOS).
# Downloads + extracts the buffalo_l face model into backend/models/buffalo_l so it can be
# baked into the Docker image. Run once on a machine with internet; then run air-gapped.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/backend/models"
TARGET="$DIR/buffalo_l"
URL="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"

if [ -f "$TARGET/w600k_r50.onnx" ]; then
  echo "Model already present at $TARGET — nothing to do."
  exit 0
fi

mkdir -p "$DIR"
echo "Downloading face model (~275 MB) ..."
curl -L --fail --retry 5 --retry-delay 3 -o "$DIR/buffalo_l.zip" "$URL"

rm -rf "$DIR/_extract"; mkdir -p "$DIR/_extract"
unzip -q "$DIR/buffalo_l.zip" -d "$DIR/_extract"
mkdir -p "$TARGET"
find "$DIR/_extract" -name '*.onnx' -exec mv {} "$TARGET/" \;
rm -rf "$DIR/_extract" "$DIR/buffalo_l.zip"
echo "Model ready at $TARGET"
ls -1 "$TARGET"
