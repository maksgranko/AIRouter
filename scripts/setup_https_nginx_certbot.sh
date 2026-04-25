#!/usr/bin/env bash

set -euo pipefail

DOMAIN=""
EMAIL=""
UPSTREAM_HOST="127.0.0.1"
UPSTREAM_PORT="8000"
APP_NAME="airouter"

print_usage() {
  cat <<EOF
Usage:
  sudo bash scripts/setup_https_nginx_certbot.sh \\
    --domain api.example.com \\
    --email admin@example.com \\
    [--upstream-host 127.0.0.1] \\
    [--upstream-port 8000] \\
    [--app-name airouter]

Description:
  Installs and configures Nginx as reverse proxy for AIRouter,
  obtains Let's Encrypt certificate via certbot, and enables HTTPS redirect.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="$2"
      shift 2
      ;;
    --email)
      EMAIL="$2"
      shift 2
      ;;
    --upstream-host)
      UPSTREAM_HOST="$2"
      shift 2
      ;;
    --upstream-port)
      UPSTREAM_PORT="$2"
      shift 2
      ;;
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Error: --domain and --email are required."
  print_usage
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Error: run as root (sudo)."
  exit 1
fi

echo "[1/7] Installing Nginx and certbot..."
apt-get update -y
apt-get install -y nginx certbot python3-certbot-nginx

echo "[2/7] Checking port 80 availability..."
if ss -lntp | grep -q ':80 '; then
  echo "Warning: port 80 is already in use."
  echo "Make sure Nginx can bind to :80 for ACME challenge."
fi

NGINX_SITE_AVAIL="/etc/nginx/sites-available/${APP_NAME}.conf"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/${APP_NAME}.conf"

echo "[3/7] Writing Nginx site config: ${NGINX_SITE_AVAIL}"
cat > "$NGINX_SITE_AVAIL" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 50m;

    location / {
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;

        proxy_pass http://${UPSTREAM_HOST}:${UPSTREAM_PORT};
    }
}
EOF

echo "[4/7] Enabling Nginx site..."
ln -sfn "$NGINX_SITE_AVAIL" "$NGINX_SITE_ENABLED"
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

echo "[5/7] Testing and reloading Nginx..."
nginx -t
systemctl enable nginx
systemctl restart nginx

echo "[6/7] Obtaining Let's Encrypt certificate with redirect..."
certbot --nginx -d "$DOMAIN" --agree-tos -m "$EMAIL" --non-interactive --redirect

echo "[7/7] Verifying auto-renew timer..."
systemctl enable certbot.timer >/dev/null 2>&1 || true
systemctl start certbot.timer >/dev/null 2>&1 || true

echo "Done. HTTPS should now be available at: https://${DOMAIN}"
echo "Check renewal dry-run with: certbot renew --dry-run"
