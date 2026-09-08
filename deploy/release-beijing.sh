#!/usr/bin/env bash
# Build evidence locally, sync the release, and ask the Beijing host to activate it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BEIJING_HOST="${COINTENT_SSH_HOST:-beijing-idea-factory}"
REMOTE_APP_DIR="${COINTENT_REMOTE_APP_DIR:-/home/deploy/cointent}"
EXPERIMENT_REPOSITORY="${COINTENT_EXPERIMENT_REPOSITORY:-/home/claude-user/oc-hands-workspace/idea-factory}"
PUBLIC_ORIGIN="${COINTENT_PUBLIC_ORIGIN:-https://cointent.enjoyapier.cloud}"
SKIP_PUBLIC=0
[ "${1:-}" = "--skip-public" ] && SKIP_PUBLIC=1

log() { printf '\n== %s ==\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

need git
need uv
need npm
need ssh
need rsync
need curl
cd "$ROOT"
[ -d "$EXPERIMENT_REPOSITORY/.git" ] || die "Idea Factory checkout not found: $EXPERIMENT_REPOSITORY"

log "local quality gates"
uv run --extra dev pytest
npm --prefix web run build

fixture_dir="$(mktemp -d)"
trap 'rm -rf "$fixture_dir"' EXIT
log "capture read-only Idea Factory evidence"
uv run cointent --database "$fixture_dir/cointent.db" scan "$EXPERIMENT_REPOSITORY" \
  --project-id idea-factory --name "Idea Factory" --seed-idea-factory \
  --export "$fixture_dir/snapshot.json"
uv run cointent --database "$fixture_dir/cointent.db" export-model \
  --project-id idea-factory --output "$fixture_dir/model.json"

release_id="$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%d%H%M%S)"
log "sync release $release_id"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$BEIJING_HOST" "mkdir -p '$REMOTE_APP_DIR/seed'"
rsync -az --delete \
  -e "ssh -o BatchMode=yes -o ConnectTimeout=8" \
  --exclude '.git/' --exclude '.env' --exclude '.venv/' \
  --exclude '.pytest_cache/' --exclude '.playwright-cli/' --exclude 'output/' \
  --exclude 'runtime/' --exclude 'seed/' --exclude 'web/node_modules/' \
  --exclude 'web/dist/' --exclude 'web-dist/' \
  "$ROOT/" "$BEIJING_HOST:$REMOTE_APP_DIR/"
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=8" \
  "$fixture_dir/snapshot.json" "$fixture_dir/model.json" "$BEIJING_HOST:$REMOTE_APP_DIR/seed/"

log "activate on Beijing"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$BEIJING_HOST" \
  "cd '$REMOTE_APP_DIR' && bash deploy/release-remote.sh '$release_id'"

if [ "$SKIP_PUBLIC" = 1 ]; then
  printf '\npublic smoke skipped; server-side release is complete\n'
  exit 0
fi
log "public smoke"
curl -fsS "$PUBLIC_ORIGIN/" | grep -q '<title>CoIntent'
curl -fsS "$PUBLIC_ORIGIN/api/health" | grep -q '"ok":true'
api_code="$(curl -sS -o /dev/null -w '%{http_code}' "$PUBLIC_ORIGIN/api/v1/overview?project_id=idea-factory")"
[ "$api_code" = "401" ] || die "public browser API returned $api_code without a session, expected 401"
mcp_code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$PUBLIC_ORIGIN/mcp")"
[ "$mcp_code" = "401" ] || die "public MCP returned $mcp_code, expected 401"
printf 'public CoIntent release is healthy\n'
