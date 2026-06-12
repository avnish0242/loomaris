#!/usr/bin/env bash
# Bootstrap Let's Encrypt certificates for loomaris.xyz.
# Run once on a fresh server BEFORE starting the full prod stack.
#
# Usage:  bash infrastructure/certbot/init-letsencrypt.sh [--staging]
#
# --staging  Uses Let's Encrypt staging CA (unlimited retries, good for testing).
#            Remove the flag when you're ready for real certs.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAINS=(app.loomaris.xyz api.loomaris.xyz)
EMAIL="avnish.dbg@gmail.com"     # Cert expiry notifications
DOMAIN="app.loomaris.xyz"        # Primary domain (cert is issued for this; www/apex are on Netlify)
DATA_PATH="./infrastructure/certbot"
STAGING=0

for arg in "$@"; do
  [[ "$arg" == "--staging" ]] && STAGING=1
done

# ─── 1. Check Docker is running ───────────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
  echo "✗  Docker is not running."
  exit 1
fi

# ─── 2. Download recommended TLS parameters ───────────────────────────────────
if [ ! -e "$DATA_PATH/conf/options-ssl-nginx.conf" ] || \
   [ ! -e "$DATA_PATH/conf/ssl-dhparams.pem" ]; then
  echo "▶ Downloading recommended TLS parameters…"
  mkdir -p "$DATA_PATH/conf"
  curl -sSo "$DATA_PATH/conf/options-ssl-nginx.conf" \
    "https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf"
  curl -sSo "$DATA_PATH/conf/ssl-dhparams.pem" \
    "https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem"
fi

# ─── 3. Create dummy certificate so nginx can start ───────────────────────────
CERT_PATH="/etc/letsencrypt/live/$DOMAIN"
DUMMY_CERT_PATH="$DATA_PATH/conf/live/$DOMAIN"

if [ ! -e "$DUMMY_CERT_PATH/fullchain.pem" ]; then
  echo "▶ Creating dummy certificate for $DOMAIN…"
  mkdir -p "$DUMMY_CERT_PATH"
  docker run --rm \
    -v "$(pwd)/$DATA_PATH/conf:/etc/letsencrypt" \
    certbot/certbot \
    certonly --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --cert-name "$DOMAIN" \
    --register-unsafely-without-email 2>/dev/null || true

  # Fallback: generate self-signed cert locally
  if [ ! -e "$DUMMY_CERT_PATH/fullchain.pem" ]; then
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout "$DUMMY_CERT_PATH/privkey.pem" \
      -out    "$DUMMY_CERT_PATH/fullchain.pem" \
      -subj "/CN=localhost" 2>/dev/null
    cp "$DUMMY_CERT_PATH/fullchain.pem" "$DUMMY_CERT_PATH/chain.pem"
  fi
fi

# ─── 4. Start nginx with dummy cert ───────────────────────────────────────────
echo "▶ Starting nginx (HTTP only for ACME challenge)…"
docker compose -f docker-compose.prod.yml up -d nginx

echo "  Waiting for nginx to be ready…"
sleep 3

# ─── 5. Delete dummy cert and request real cert ───────────────────────────────
echo "▶ Requesting certificate from Let's Encrypt…"
rm -rf "$DUMMY_CERT_PATH"

DOMAIN_ARGS=""
for d in "${DOMAINS[@]}"; do DOMAIN_ARGS="$DOMAIN_ARGS -d $d"; done

STAGING_FLAG=""
[[ "$STAGING" -eq 1 ]] && STAGING_FLAG="--staging"

docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot \
  --webroot-path /var/www/certbot \
  $STAGING_FLAG \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  --force-renewal \
  $DOMAIN_ARGS

# ─── 6. Reload nginx with real cert ───────────────────────────────────────────
echo "▶ Reloading nginx with real certificate…"
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ SSL certificate issued for: ${DOMAINS[*]}"
echo ""
if [[ "$STAGING" -eq 1 ]]; then
  echo "  ⚠  Staging cert — browsers will show a warning."
  echo "     Re-run without --staging to get a trusted cert."
else
  echo "  ✓ https://app.loomaris.xyz  →  Next.js frontend"
  echo "  ✓ https://api.loomaris.xyz  →  FastAPI backend"
fi
echo ""
echo "  Auto-renewal: certbot container renews every 12 hours (cron via entrypoint)."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
