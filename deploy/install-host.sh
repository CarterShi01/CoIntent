#!/usr/bin/env bash
# One-time root-only host setup after DNS points at the Beijing machine.
set -euo pipefail

[ "$(id -u)" = 0 ] || { printf 'run this script as root\n' >&2; exit 1; }

APP_DIR="${COINTENT_APP_DIR:-/home/deploy/cointent}"
DOMAIN="cointent.enjoyapier.cloud"
WEB_USER="${COINTENT_WEB_USER:-carter}"
STAGED_AUTH_FILE="$APP_DIR/runtime/cointent.htpasswd"

command -v openssl >/dev/null 2>&1 || { printf 'missing openssl\n' >&2; exit 1; }
command -v certbot >/dev/null 2>&1 || { printf 'missing certbot\n' >&2; exit 1; }
[ -n "${CERTBOT_EMAIL:-}" ] || read -r -p "Let's Encrypt notification email: " CERTBOT_EMAIL
[ -n "$CERTBOT_EMAIL" ] || { printf 'email cannot be empty\n' >&2; exit 1; }

if [ -s "$STAGED_AUTH_FILE" ]; then
  grep -q "^${WEB_USER}:" "$STAGED_AUTH_FILE" || {
    printf 'staged password file does not contain user %s\n' "$WEB_USER" >&2
    exit 1
  }
  install -o root -g www-data -m 0640 "$STAGED_AUTH_FILE" /etc/nginx/.htpasswd-cointent
  rm -f "$STAGED_AUTH_FILE"
else
  if [ -z "${COINTENT_WEB_PASSWORD:-}" ]; then
    read -r -s -p "CoIntent password for ${WEB_USER}: " COINTENT_WEB_PASSWORD
    printf '\n'
    read -r -s -p "Repeat password: " confirmation
    printf '\n'
    [ "$COINTENT_WEB_PASSWORD" = "$confirmation" ] || { printf 'passwords do not match\n' >&2; exit 1; }
  fi
  [ "${#COINTENT_WEB_PASSWORD}" -ge 20 ] || { printf 'password must contain at least 20 characters\n' >&2; exit 1; }
  password_hash="$(printf '%s' "$COINTENT_WEB_PASSWORD" | openssl passwd -apr1 -stdin)"
  printf '%s:%s\n' "$WEB_USER" "$password_hash" > /etc/nginx/.htpasswd-cointent
  chown root:www-data /etc/nginx/.htpasswd-cointent
  chmod 0640 /etc/nginx/.htpasswd-cointent
  unset COINTENT_WEB_PASSWORD confirmation password_hash
fi

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
