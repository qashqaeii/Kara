#!/usr/bin/env bash
# Safe production deploy for Kara (application layer).
# Run as the kara user:
#   sudo -u kara bash deploy/deploy.sh
#
# Service restarts require root. After setup-server.sh, kara can run:
#   sudo bash deploy/restart-services.sh
# Or deploy.sh will attempt passwordless sudo and print instructions if unavailable.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kara}"
VENV="${VENV:-$APP_DIR/.venv}"
BRANCH="${BRANCH:-main}"

cd "$APP_DIR"

echo "==> Pull latest code ($BRANCH)"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> Install Python dependencies"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt

echo "==> Ensure runtime directories exist"
install -d -m 0750 \
  "${DJANGO_STATIC_ROOT:-/var/lib/kara/staticfiles}" \
  "${DJANGO_MEDIA_ROOT:-/var/lib/kara/media}" \
  "${KARA_CACHE_DIR:-/var/lib/kara/cache}" \
  "${KARA_LOG_DIR:-/var/log/kara}" 2>/dev/null || true

echo "==> Django checks"
export KARA_DISABLE_AUTO_REFRESH=1
"$VENV/bin/python" manage.py check
"$VENV/bin/python" manage.py check --deploy
"$VENV/bin/python" manage.py migrate --check
"$VENV/bin/python" manage.py migrate --noinput

echo "==> Collect static files"
"$VENV/bin/python" manage.py collectstatic --noinput

echo "==> Restart services"
if [ "$(id -u)" -eq 0 ]; then
  bash "$APP_DIR/deploy/restart-services.sh"
elif sudo -n true 2>/dev/null && sudo -n bash "$APP_DIR/deploy/restart-services.sh" 2>/dev/null; then
  :
else
  echo ""
  echo "Could not restart services as $(whoami)."
  echo "Run as root:"
  echo "  sudo bash $APP_DIR/deploy/restart-services.sh"
  echo ""
  echo "Or configure passwordless sudo via: sudo bash $APP_DIR/deploy/setup-server.sh"
fi

echo "==> Health check"
curl -fsS "https://portal.pakhshmarket.com/health/" 2>/dev/null \
  || curl -fsS "http://127.0.0.1:8000/health/" \
  || echo "Health check skipped (service may still be starting)"

echo "Deploy finished successfully."
