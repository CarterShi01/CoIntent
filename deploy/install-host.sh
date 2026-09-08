#!/usr/bin/env bash
# One-time root-only host setup after DNS points at the Beijing machine.
set -euo pipefail

[ "$(id -u)" = 0 ] || { printf 'run this script as root\n' >&2; exit 1; }

APP_DIR="${COINTENT_APP_DIR:-/home/deploy/cointent}"
DOMAIN="cointent.enjoyapier.cloud"

command -v certbot >/dev/null 2>&1 || { printf 'missing certbot\n' >&2; exit 1; }
[ -n "${CERTBOT_EMAIL:-}" ] || read -r -p "Let's Encrypt notification email: " CERTBOT_EMAIL
[ -n "$CERTBOT_EMAIL" ] || { printf 'email cannot be empty\n' >&2; exit 1; }

mkdir -p /var/www/cointent
cp "$APP_DIR/deploy/nginx/cointent.bootstrap.conf" /etc/nginx/sites-available/cointent
ln -sfn /etc/nginx/sites-available/cointent /etc/nginx/sites-enabled/cointent
nginx -t
systemctl reload nginx

certbot certonly --webroot -w /var/www/cointent \
  --non-interactive --agree-tos --email "$CERTBOT_EMAIL" -d "$DOMAIN"
cp "$APP_DIR/deploy/nginx/cointent.conf" /etc/nginx/sites-available/cointent
nginx -t
systemctl reload nginx
printf 'CoIntent host installed at https://%s\n' "$DOMAIN"
