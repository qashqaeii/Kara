#!/usr/bin/env bash
# One-time server bootstrap (run as root on Ubuntu 24.04).
# Creates the kara user, runtime directories, and optional passwordless deploy sudo.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kara}"
KARA_USER="${KARA_USER:-kara}"

echo "==> Create system user ${KARA_USER}"
if ! id "${KARA_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${KARA_USER}"
fi

echo "==> Create runtime directories"
install -d -o "${KARA_USER}" -g "${KARA_USER}" -m 0750 \
  "${APP_DIR}" \
  /var/lib/kara/staticfiles \
  /var/lib/kara/media \
  /var/lib/kara/cache \
  /var/log/kara \
  /var/www/certbot

echo "==> Ownership"
chown -R "${KARA_USER}:${KARA_USER}" "${APP_DIR}" /var/lib/kara /var/log/kara

echo "==> Optional: allow ${KARA_USER} to restart Kara services without a password"
SUDOERS_FILE="/etc/sudoers.d/kara-deploy"
cat >"${SUDOERS_FILE}" <<EOF
# Kara deploy — restart services only (managed by setup-server.sh)
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl restart kara-web
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl restart kara-scheduler
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl restart kara-bot
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl reload nginx
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl is-enabled kara-scheduler
${KARA_USER} ALL=(root) NOPASSWD: /bin/systemctl is-enabled kara-bot
EOF
chmod 0440 "${SUDOERS_FILE}"
visudo -cf "${SUDOERS_FILE}"

echo "Server setup complete."
echo "Next: clone repo to ${APP_DIR} as ${KARA_USER}, configure .env, run deploy/deploy.sh"
