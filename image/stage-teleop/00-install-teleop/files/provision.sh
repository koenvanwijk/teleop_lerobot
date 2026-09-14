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
