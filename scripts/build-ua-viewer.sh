#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
BUILD_DIR=$(mktemp -d)
STAGING_DIR="$ROOT_DIR/web/ua-viewer-dist.next"
TARGET_DIR="$ROOT_DIR/web/ua-viewer-dist"
BACKUP_DIR="$ROOT_DIR/web/ua-viewer-dist.previous"
UA_COMMIT=5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc
NODE_BIN=${COINTENT_NODE_BIN:-node}
COREPACK_JS=$(readlink -f "$(command -v corepack)")
BRIDGE_PATCH_SHA=$(sha256sum "$ROOT_DIR/scripts/patch-ua-viewer.mjs" | cut -d' ' -f1)

NODE_MAJOR=$($NODE_BIN -p 'process.versions.node.split(".")[0]')
if (( NODE_MAJOR < 22 )); then
  echo "Understand Anything 2.9.6 requires Node.js 22+; set COINTENT_NODE_BIN to a compatible binary." >&2
  exit 2
fi

cleanup() {
  rm -rf "$BUILD_DIR"
}
trap cleanup EXIT

git clone --quiet https://github.com/Egonex-AI/Understand-Anything.git "$BUILD_DIR/ua"
git -C "$BUILD_DIR/ua" checkout --quiet "$UA_COMMIT"
"$NODE_BIN" "$ROOT_DIR/scripts/patch-ua-viewer.mjs" "$BUILD_DIR/ua"
mkdir -p "$BUILD_DIR/bin"
"$NODE_BIN" "$COREPACK_JS" enable --install-directory "$BUILD_DIR/bin"
(
  cd "$BUILD_DIR/ua"
  export PATH="$BUILD_DIR/bin:$(dirname "$NODE_BIN"):$PATH"
  "$NODE_BIN" "$COREPACK_JS" pnpm install --frozen-lockfile
  "$NODE_BIN" "$COREPACK_JS" pnpm --filter understand-anything-viewer build
)

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$BUILD_DIR/ua/understand-anything-plugin/packages/viewer/dist/." "$STAGING_DIR/"
cp "$BUILD_DIR/ua/LICENSE" "$STAGING_DIR/UNDERSTAND-ANYTHING-LICENSE.txt"
printf '%s\n' \
  'Understand Anything 2.9.6' \
  "upstream_commit=$UA_COMMIT" \
  "bridge_patch_sha256=$BRIDGE_PATCH_SHA" \
  'integration_protocol=1' > "$STAGING_DIR/COINTENT-INTEGRATION.txt"

rm -rf "$BACKUP_DIR"
if [[ -d "$TARGET_DIR" ]]; then mv "$TARGET_DIR" "$BACKUP_DIR"; fi
mv "$STAGING_DIR" "$TARGET_DIR"
rm -rf "$BACKUP_DIR"
echo "Built pinned UA Dashboard at $TARGET_DIR"
