#!/usr/bin/env bash
# Restart Kara systemd units and reload Nginx (requires root or passwordless sudo).
set -euo pipefail

restart_unit() {
  local unit="$1"
  if systemctl is-enabled "${unit}" >/dev/null 2>&1; then
    systemctl restart "${unit}"
    echo "Restarted ${unit}"
  fi
}

restart_unit kara-web
restart_unit kara-scheduler
restart_unit kara-bot
systemctl reload nginx
echo "Services reloaded."
