#!/usr/bin/env bash
set -euo pipefail

# Fix/check Bluetooth WiFi provisioning on delivered robots.
# Goal: never leave the robot headless-unreachable after a failed WiFi switch.

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./fix_ble_wifi_provisioning.sh" >&2
  exit 1
fi

SERVICE="lerobot-webserver.service"
RULE_FILE="/etc/polkit-1/rules.d/49-lerobot-networkmanager.rules"
LOG_FILE="/tmp/lerobot-ble-wifi-check.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BT_FILE="$SCRIPT_DIR/bluetooth_gatt_server.py"
TEMPLATE_FILE="$SCRIPT_DIR/templates/index.html"

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

if getent group netdev >/dev/null 2>&1; then
  usermod -aG netdev "$SERVICE_USER" || true
fi

# Patch the installed checkout so a failed BLE WiFi connect restores AP and exposes a visible status.
if [[ -f "$BT_FILE" ]]; then
  python3 - "$BT_FILE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "async def start_rescue_ap(self):" not in text:
    marker = "    async def scan_wifi(self):\n"
    helper = '''    async def start_rescue_ap(self):
        """Restore LeRobot-AP after a failed Bluetooth WiFi provisioning attempt."""
        import subprocess
        logger.warning("Starting rescue Access Point LeRobot-AP after WiFi provisioning failure")
        if self.char_wifi_status:
            self.char_wifi_status.update_status("ap:starting_rescue")

        commands = [
            ['nmcli', 'radio', 'wifi', 'on'],
            ['nmcli', 'device', 'set', 'wlan0', 'managed', 'yes'],
            ['nmcli', 'con', 'down', 'Hotspot'],
            ['nmcli', 'con', 'delete', 'Hotspot'],
            [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', 'wlan0',
                'con-name', 'Hotspot',
                'ssid', 'LeRobot-AP',
                'password', 'robotics123',
            ],
        ]

        last_error = ""
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode != 0 and cmd[:3] not in (['nmcli', 'con', 'down'], ['nmcli', 'con', 'delete']):
                last_error = (result.stderr or result.stdout or str(cmd)).strip()
                logger.error(f"Rescue AP command failed: {' '.join(cmd)} -> {last_error}")
                if self.char_wifi_status:
                    self.char_wifi_status.update_status(f"error:ap_failed:{last_error[:80]}")
                return False

        await asyncio.sleep(2)
        if self.char_ip:
            self.char_ip.update_ip("192.168.4.1")
        if self.char_wifi_status:
            self.char_wifi_status.update_status("ap:LeRobot-AP:http://192.168.4.1/")
        logger.warning("Rescue AP active: LeRobot-AP / robotics123 / http://192.168.4.1/")
        return True

'''
    text = text.replace(marker, helper + marker)

pattern = re.compile(r"    async def connect_wifi\(self\):\n.*?\n    async def scan_wifi\(self\):\n", re.S)
replacement = '''    async def connect_wifi(self):
        """Connect to WiFi using stored credentials via NetworkManager.

        Delivery safety rule: if provisioning fails or no usable IP is obtained,
        restore LeRobot-AP so the robot never becomes headless-unreachable.
        """
        if not self.wifi_ssid:
            logger.error("No WiFi SSID provided")
            if self.char_wifi_status:
                self.char_wifi_status.update_status("error:no_ssid")
            await self.start_rescue_ap()
            return

        logger.info(f"Attempting to connect to WiFi via BLE: {self.wifi_ssid}")
        if self.char_wifi_status:
            self.char_wifi_status.update_status("connecting")

        try:
            import subprocess

            subprocess.run(['nmcli', 'radio', 'wifi', 'on'], capture_output=True, text=True, timeout=10)
            subprocess.run(['nmcli', 'device', 'set', 'wlan0', 'managed', 'yes'], capture_output=True, text=True, timeout=10)
            subprocess.run(['nmcli', 'con', 'down', 'Hotspot'], capture_output=True, text=True, timeout=10)
            await asyncio.sleep(1)

            subprocess.run(['nmcli', 'con', 'delete', 'id', self.wifi_ssid], capture_output=True, text=True, timeout=10)

            cmd = ['nmcli', 'dev', 'wifi', 'connect', self.wifi_ssid]
            if self.wifi_password:
                cmd.extend(['password', self.wifi_password])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            output = (result.stderr or result.stdout or '').strip()

            if result.returncode != 0:
                logger.error(f"Failed to connect to WiFi '{self.wifi_ssid}': {output}")
                lower = output.lower()
                if 'secrets' in lower or 'password' in lower or 'psk' in lower:
                    status = 'error:bad_password_or_security'
                elif 'not authorized' in lower or 'permission' in lower or 'auth' in lower:
                    status = 'error:permission_denied'
                else:
                    status = 'error:' + output[:80] if output else 'error:nmcli_failed'
                if self.char_wifi_status:
                    self.char_wifi_status.update_status(status)
                await self.start_rescue_ap()
                return

            logger.info(f"NetworkManager reports connected to {self.wifi_ssid}")
            if self.char_wifi_status:
                self.char_wifi_status.update_status(f"connected:{self.wifi_ssid}:waiting_for_ip")

            new_ip = "No IP"
            for _ in range(20):
                await asyncio.sleep(1)
                new_ip = self.get_local_ip()
                if new_ip != "No IP" and not new_ip.startswith("169.254."):
                    break

            if new_ip != "No IP" and not new_ip.startswith("169.254."):
                if self.char_ip:
                    self.char_ip.update_ip(new_ip)
                if self.char_wifi_status:
                    self.char_wifi_status.update_status(f"connected:{self.wifi_ssid}:ip:{new_ip}")
                logger.info(f"New IP after WiFi connect: {new_ip}")
                return

            logger.error("WiFi connected but no usable DHCP IP was assigned")
            if self.char_wifi_status:
                self.char_wifi_status.update_status("error:no_new_ip")
            await self.start_rescue_ap()

        except subprocess.TimeoutExpired:
            logger.error("WiFi connection timeout")
            if self.char_wifi_status:
                self.char_wifi_status.update_status("error:timeout")
            await self.start_rescue_ap()
        except Exception as e:
            logger.error(f"WiFi connection error: {e}")
            if self.char_wifi_status:
                self.char_wifi_status.update_status(f"error:{str(e)[:80]}")
            await self.start_rescue_ap()

    async def scan_wifi(self):
'''
new_text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit("Could not patch connect_wifi block in bluetooth_gatt_server.py")

if new_text != path.read_text(encoding="utf-8"):
    backup = path.with_suffix(path.suffix + ".bak.ble-wifi")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")
    print(f"Patched {path}; backup: {backup}")
else:
    print(f"{path} already patched")
PY
fi

# Add a password visibility checkbox to the local Network tab as well.
if [[ -f "$TEMPLATE_FILE" ]]; then
  python3 - "$TEMPLATE_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if "toggle-main-wifi-password" not in text:
    text = text.replace(
        '<input type="password" id="wifi-password" data-i18n="[placeholder]network.password" placeholder="Password">',
        '<input type="password" id="wifi-password" data-i18n="[placeholder]network.password" placeholder="Password">\n                    <label style="display:flex;gap:8px;align-items:center;margin-top:6px;font-size:0.9em;">\n                        <input type="checkbox" id="toggle-main-wifi-password" style="width:auto;">\n                        <span>Toon WiFi-wachtwoord</span>\n                    </label>'
    )
    insert = """
<script>
document.addEventListener('DOMContentLoaded', function () {
  const toggle = document.getElementById('toggle-main-wifi-password');
  const input = document.getElementById('wifi-password');
  if (toggle && input) {
    toggle.addEventListener('change', function () {
      input.type = toggle.checked ? 'text' : 'password';
    });
  }
});
</script>
"""
    text = text.replace("</body>", insert + "\n</body>")
    backup = path.with_suffix(path.suffix + ".bak.password-toggle")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    print(f"Patched {path}; backup: {backup}")
else:
    print(f"{path} already has password toggle")
PY
fi

systemctl restart polkit 2>/dev/null || systemctl restart policykit 2>/dev/null || true

if systemctl is-enabled "$SERVICE" >/dev/null 2>&1 || systemctl is-active "$SERVICE" >/dev/null 2>&1; then
  systemctl daemon-reload || true
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
  journalctl -u "$SERVICE" -b -n 160 --no-pager || true
} | tee "$LOG_FILE"

echo ""
echo "Done. Diagnostic log saved to: $LOG_FILE"
echo ""
echo "Retest flow:"
echo "  1. Open https://koenvanwijk.github.io/teleop_lerobot/ on Android/Chrome/Edge."
echo "  2. Scan/select the robot."
echo "  3. Scan WiFi or type SSID manually. Use 'Toon WiFi-wachtwoord' while typing."
echo "  4. Press connect and watch the visible status."
echo "  5. If no new IP arrives, connect to LeRobot-AP / robotics123 / http://192.168.4.1/ ."
echo ""
echo "If it still fails, send the contents of: $LOG_FILE"
