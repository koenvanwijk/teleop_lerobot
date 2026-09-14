#!/bin/bash
# First-boot provisioner: runs the repo's tested install.sh once, as the
# normal user (install.sh uses sudo internally, which is passwordless for the
# pi-gen first user). Retries on next boot if it fails; self-disables on success.
set -uo pipefail

USER_NAME="__FIRST_USER__"
REPO="/home/${USER_NAME}/teleop_lerobot"
LOG="/var/log/lerobot-firstboot.log"
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -Is)] LeRobot first-boot provisioning start (user=${USER_NAME})"

# Optional onboarding values: LEROBOT_ROBOT_NAME, TAILSCALE_AUTH_KEY
if [ -f /etc/lerobot/firstboot.env ]; then
	# shellcheck disable=SC1091
	. /etc/lerobot/firstboot.env
fi

if [ ! -d "$REPO" ]; then
	echo "[$(date -Is)] ERROR: repo not found at $REPO"
	exit 1
fi

# The Pi has no battery-backed clock. On first boot the clock can be behind
# real time, which makes apt reject repo metadata as "not valid yet" and
# install.sh fails at `apt-get update`. Wait (best-effort) for a synced clock.
echo "[$(date -Is)] waiting for clock sync (no RTC on the Pi)..."
timedatectl set-ntp true 2>/dev/null || true
for _ in $(seq 1 60); do
	if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = "yes" ]; then
		break
	fi
	sleep 2
done
if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = "yes" ]; then
	echo "[$(date -Is)] clock synchronized"
else
	echo "[$(date -Is)] WARNING: clock not confirmed synced after 120s; continuing anyway"
fi

# BLE WiFi-onboarding is meant for a Pi with no WiFi configured yet, but
# Bookworm keeps the WLAN radio blocked until a regulatory country is set --
# which makes the onboarding WiFi scan return nothing on a fresh flash. Set a
# country (default NL, override via LEROBOT_WIFI_COUNTRY) and enable the radio.
WIFI_COUNTRY="${LEROBOT_WIFI_COUNTRY:-NL}"
echo "[$(date -Is)] setting WiFi country=${WIFI_COUNTRY} and enabling radio"
raspi-config nonint do_wifi_country "$WIFI_COUNTRY" 2>/dev/null || true
rfkill unblock wifi 2>/dev/null || true
nmcli radio wifi on 2>/dev/null || true

INSTALL_ARGS=()
[ -n "${LEROBOT_ROBOT_NAME:-}" ] && INSTALL_ARGS+=(--robot-name "${LEROBOT_ROBOT_NAME}")
[ -n "${TAILSCALE_AUTH_KEY:-}" ] && INSTALL_ARGS+=(--tailscale)

cd "$REPO" || exit 1

# Run install.sh as the user. The Tailscale key is passed via env (never argv)
# so it does not show up in the process list.
if sudo -u "$USER_NAME" -H \
	env TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}" \
	bash ./install.sh ${INSTALL_ARGS[@]+"${INSTALL_ARGS[@]}"}; then
	echo "[$(date -Is)] install.sh completed OK; disabling first-boot service"
	systemctl disable lerobot-firstboot.service || true
	# Wipe any onboarding secret now that it has been consumed.
	[ -f /etc/lerobot/firstboot.env ] && shred -u /etc/lerobot/firstboot.env 2>/dev/null || true
	echo "[$(date -Is)] done"
else
	rc=$?
	echo "[$(date -Is)] install.sh FAILED (rc=$rc); will retry on next boot"
	exit "$rc"
fi
