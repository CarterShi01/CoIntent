#!/usr/bin/env bash
# Run as the unprivileged deploy user on the Beijing host after a release sync.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_ID="${1:-manual}"
WEB_ROOT="${COINTENT_WEB_ROOT:-/var/www/cointent}"
ALPINE_IMAGE="${COINTENT_DEPLOY_ALPINE_IMAGE:-alpine:3.22}"

log() { printf '\n== %s ==\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

need docker
need curl
need sha256sum
cd "$APP_DIR"

mkdir -p runtime seed web-dist
if [ ! -f .env ]; then
  token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  umask 077
  {
    printf 'COINTENT_PUBLIC_ORIGIN=https://cointent.enjoyapier.cloud\n'
    printf 'COINTENT_MCP_TOKEN=%s\n' "$token"
    printf 'COINTENT_PORT=8811\n'
  } > .env
  printf 'created %s/.env with a private MCP bearer token\n' "$APP_DIR"
fi
export COINTENT_RELEASE="$RELEASE_ID"

log "build backend and web images"
docker compose build backend
docker compose --profile build build web

log "import the portable Idea Factory experiment"
[ -f seed/snapshot.json ] || die "missing seed/snapshot.json"
[ -f seed/model.json ] || die "missing seed/model.json"
docker compose run --rm --no-deps backend \
  --database /data/cointent.db import-fixture \
  --snapshot /seed/snapshot.json --model /seed/model.json >/dev/null

log "build and publish static UI"
docker run --rm -v "$APP_DIR/web-dist:/target" "$ALPINE_IMAGE" sh -lc \
  'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
docker compose --profile build run --rm web
[ -f web-dist/index.html ] || die "web build did not produce web-dist/index.html"
docker run --rm \
  -v "$APP_DIR/web-dist:/src:ro" -v "$WEB_ROOT:/dst" "$ALPINE_IMAGE" sh -lc '
    set -eu
    rm -rf /dst/* /dst/.[!.]* /dst/..?* 2>/dev/null || true
    cp -a /src/. /dst/
    chown -R 0:0 /dst
    find /dst -type d -exec chmod 755 {} +
    find /dst -type f -exec chmod 644 {} +
  '
source_hash="$(sha256sum web-dist/index.html | cut -c1-12)"
published_hash="$(docker run --rm -v "$WEB_ROOT:/dst:ro" "$ALPINE_IMAGE" sh -lc 'sha256sum /dst/index.html | cut -c1-12')"
[ "$source_hash" = "$published_hash" ] || die "static publish mismatch: $source_hash != $published_hash"
printf 'static index sha=%s\n' "$source_hash"

log "start backend"
docker compose up -d backend
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8811/api/health >/dev/null 2>&1; then
    break
  fi
  [ "$attempt" -lt 30 ] || { docker compose logs --tail=100 backend; die "backend did not become healthy"; }
  sleep 1
done
docker compose ps

log "local smoke"
curl -fsS http://127.0.0.1:8811/api/health
printf '\n'
overview="$(curl -fsS 'http://127.0.0.1:8811/api/v1/overview?project_id=idea-factory')"
printf '%s' "$overview" | grep -q '"roles":8' || die "Idea Factory baseline is not available"
mcp_code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8811/mcp)"
[ "$mcp_code" = "401" ] || die "unauthenticated MCP returned $mcp_code, expected 401"
printf 'MCP unauthenticated -> 401\n'
printf 'released CoIntent %s\n' "$RELEASE_ID"
