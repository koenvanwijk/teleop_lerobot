#!/usr/bin/env bash
set -euo pipefail

# Fix/check Bluetooth WiFi provisioning on delivered robots.
# Symptom: Bluetooth works and shows the old IP, but changing WiFi via BLE gives
# no visible new IP because NetworkManager rejected the WiFi change or because
# the phone/browser did not show the BLE status characteristic clearly.

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./fix_ble_wifi_provisioning.sh" >&2
  exit 1
fi

SERVICE="lerobot-webserver.service"
RULE_FILE="/etc/polkit-1/rules.d/49-lerobot-networkmanager.rules"
LOG_FILE="/tmp/lerobot-ble-wifi-check.txt"

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

{
  echo "=== LeRobot BLE WiFi provisioning check ==="
  date -Is
  echo "Service user: $SERVICE_USER"
  echo ""
  echo "--- systemd service ---"
  systemctl status "$SERVICE" --no-pager || true
  echo ""
  echo "--- NetworkManager permissions as $SERVICE_USER ---"
  su -s /bin/bash -c 'nmcli general permissions || true' "$SERVICE_USER"
  echo ""
  echo "--- Active NetworkManager connections ---"
  nmcli -t -f NAME,TYPE,DEVICE con show --active || true
  echo ""
  echo "--- WiFi device status ---"
  nmcli device status || true
  echo ""
  echo "--- Current IP addresses ---"
  hostname -I || true
  ip -br addr || true
  echo ""
  echo "--- Recent LeRobot logs ---"
  journalctl -u "$SERVICE" -b -n 120 --no-pager || true
} | tee "$LOG_FILE"

echo ""
echo "Done. Diagnostic log saved to: $LOG_FILE"
echo ""
echo "Retest flow:"
echo "  1. Open https://koenvanwijk.github.io/teleop_lerobot/ on Android/Chrome/Edge."
echo "  2. Scan/select the robot."
echo "  3. Scan WiFi, select SSID, enter password, press connect."
echo "  4. Watch the status line. It should move through connecting -> connected:<ssid>."
echo "  5. Read IP again; the link should become http://<new-ip>/ ."
echo ""
echo "If there is still no new IP, send the contents of: $LOG_FILE"
echo "Also useful live commands:"
echo "  journalctl -u lerobot-webserver.service -f"
echo "  nmcli general permissions"
echo "  nmcli device status"
