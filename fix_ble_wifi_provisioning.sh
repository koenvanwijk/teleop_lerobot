#!/usr/bin/env bash
set -euo pipefail

# Fix Bluetooth WiFi provisioning on delivered robots.
# Symptom: Bluetooth works and shows the old IP, but changing WiFi via BLE fails
# because the service user is not allowed to modify NetworkManager connections.

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./fix_ble_wifi_provisioning.sh" >&2
  exit 1
fi

SERVICE="lerobot-webserver.service"
RULE_FILE="/etc/polkit-1/rules.d/49-lerobot-networkmanager.rules"

# Prefer the actual systemd service user. Fall back to the invoking user.
SERVICE_USER=""
if systemctl cat "$SERVICE" >/dev/null 2>&1; then
  SERVICE_USER="$(systemctl cat "$SERVICE" | awk -F= '/^User=/{print $2; exit}' || true)"
fi

if [[ -z "$SERVICE_USER" ]]; then
  SERVICE_USER="${SUDO_USER:-}"
fi

if [[ -z "$SERVICE_USER" || "$SERVICE_USER" == "root" ]]; then
  SERVICE_USER="$(logname 2>/dev/null || echo lerobot)"
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "User '$SERVICE_USER' does not exist. Set SERVICE_USER manually and rerun." >&2
  exit 1
fi

echo "Configuring NetworkManager WiFi provisioning rights for user: $SERVICE_USER"

install -d -m 0755 /etc/polkit-1/rules.d
cat > "$RULE_FILE" <<EOF_RULE
// Allow the LeRobot web/BLE service user to provision WiFi without interactive sudo.
// Scope is limited to NetworkManager actions for this dedicated robot user.
polkit.addRule(function(action, subject) {
    if (subject.user == "$SERVICE_USER" &&
        action.id.indexOf("org.freedesktop.NetworkManager.") == 0) {
        return polkit.Result.YES;
    }
});
EOF_RULE
chmod 0644 "$RULE_FILE"

echo "Installed: $RULE_FILE"

# netdev is used by several desktop/server NetworkManager policy defaults.
# The polkit rule above is the hard requirement; netdev is a useful fallback.
if getent group netdev >/dev/null 2>&1; then
  usermod -aG netdev "$SERVICE_USER" || true
fi

# Reload policykit where possible.
systemctl restart polkit 2>/dev/null || systemctl restart policykit 2>/dev/null || true

# Restart the LeRobot service so Bluetooth provisioning runs with the fresh policy.
if systemctl is-enabled "$SERVICE" >/dev/null 2>&1 || systemctl is-active "$SERVICE" >/dev/null 2>&1; then
  systemctl restart "$SERVICE"
fi

echo ""
echo "NetworkManager permissions for $SERVICE_USER:"
su -s /bin/bash -c 'nmcli general permissions || true' "$SERVICE_USER"

echo ""
echo "Done. Test from Bluetooth again: scan/select WiFi, enter password, connect, then read IP again."
echo "If it still fails, collect logs with: journalctl -u lerobot-webserver.service -b -n 200 --no-pager"
