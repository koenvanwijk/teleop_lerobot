#!/usr/bin/env bash
#
# Build the teleop_lerobot Raspberry Pi image with pi-gen (Dockerized).
#
# Requirements on the build host: git + Docker. Nothing else — pi-gen runs
# entirely inside a container, so the host does not need to be Debian.
#
# Required:
#   FIRST_USER_PASS   Login password for the first user (default user: pi)
#
# Optional (override as env vars):
#   FIRST_USER_NAME       default: pi
#   TARGET_HOSTNAME       default: lerobot
#   TELEOP_REPO_URL       default: https://github.com/koenvanwijk/teleop_lerobot.git
#   TELEOP_REPO_REF       default: main   (branch, tag or commit)
#   WPA_ESSID / WPA_PASSWORD / WPA_COUNTRY   pre-seed WiFi (country default NL)
#   LEROBOT_ROBOT_NAME    bake a robot name/hostname for first boot
#   TAILSCALE_AUTH_KEY    bake a Tailscale auth key for first boot (consumed & wiped)
#   PIGEN_REF             pi-gen git tag to pin (default below)
#
# Example:
#   FIRST_USER_PASS='changeme123' TELEOP_REPO_REF=main ./build.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIGEN_DIR="${PIGEN_DIR:-$HERE/.pi-gen}"
PIGEN_REF="${PIGEN_REF:-2025-11-24-raspios-bookworm-arm64}"

: "${FIRST_USER_PASS:?Set FIRST_USER_PASS (login password for the first user)}"
FIRST_USER_NAME="${FIRST_USER_NAME:-pi}"
TARGET_HOSTNAME="${TARGET_HOSTNAME:-lerobot}"

# 1) Fetch/pin pi-gen.
if [ ! -d "$PIGEN_DIR/.git" ]; then
	git clone https://github.com/RPi-Distro/pi-gen.git "$PIGEN_DIR"
fi
git -C "$PIGEN_DIR" fetch --tags --quiet
git -C "$PIGEN_DIR" checkout --quiet "$PIGEN_REF"

# 2) Wire config into pi-gen. (The stage dir is COPIED in step 5, not symlinked:
#    pi-gen runs inside Docker with only /pi-gen mounted, so a symlink to a host
#    path would dangle in the container.)
cp "$HERE/config" "$PIGEN_DIR/config"

# Base stages must not export their own image; only our teleop stage exports.
# stage2 (Lite) and stage4 (desktop) both ship an EXPORT_IMAGE marker.
for s in stage2 stage4; do
	[ -d "$PIGEN_DIR/$s" ] && touch "$PIGEN_DIR/$s/SKIP_IMAGES"
done

# If a previous Dockerized build already ran (work dir persists inside the
# pigen_work container, or on host for non-docker builds), skip rebuilding the
# base stages (~30 min). Our stage's prerun still copies stage4's rootfs.
# Force a full rebuild with REBUILD_BASE=1.
if [ "${REBUILD_BASE:-0}" != "1" ] && \
   { [ -d "$PIGEN_DIR/work/teleop_lerobot/stage4/rootfs" ] || \
     docker container inspect pigen_work >/dev/null 2>&1; }; then
	echo "Base stages already built -> skipping stage0..stage4 rebuild."
	for s in stage0 stage1 stage2 stage3 stage4; do
		[ -d "$PIGEN_DIR/$s" ] && touch "$PIGEN_DIR/$s/SKIP"
	done
fi

# 3) Inject host-provided values (secrets stay out of git).
{
	echo ""
	echo "# ---- injected by build.sh ----"
	printf 'FIRST_USER_NAME=%q\n'  "$FIRST_USER_NAME"
	printf 'export FIRST_USER_NAME\n'
	printf 'FIRST_USER_PASS=%q\n'  "$FIRST_USER_PASS"
	printf 'TARGET_HOSTNAME=%q\n'  "$TARGET_HOSTNAME"
	[ -n "${TELEOP_REPO_URL:-}" ] && printf 'export TELEOP_REPO_URL=%q\n' "$TELEOP_REPO_URL"
	[ -n "${TELEOP_REPO_REF:-}" ] && printf 'export TELEOP_REPO_REF=%q\n' "$TELEOP_REPO_REF"
	if [ -n "${WPA_ESSID:-}" ]; then
		printf 'WPA_ESSID=%q\n'    "$WPA_ESSID"
		printf 'WPA_PASSWORD=%q\n' "${WPA_PASSWORD:-}"
		printf 'WPA_COUNTRY=%q\n'  "${WPA_COUNTRY:-NL}"
	fi
} >> "$PIGEN_DIR/config"

# 4) Optionally bake a first-boot onboarding env (robot name / Tailscale key).
#    Written straight into the rootfs staging area used by the teleop stage.
if [ -n "${LEROBOT_ROBOT_NAME:-}" ] || [ -n "${TAILSCALE_AUTH_KEY:-}" ] || [ -n "${WPA_COUNTRY:-}" ]; then
	ENV_STAGE_DIR="$HERE/stage-teleop/00-install-teleop/files"
	{
		[ -n "${LEROBOT_ROBOT_NAME:-}" ] && printf 'LEROBOT_ROBOT_NAME=%s\n' "$LEROBOT_ROBOT_NAME"
		[ -n "${TAILSCALE_AUTH_KEY:-}" ] && printf 'TAILSCALE_AUTH_KEY=%s\n' "$TAILSCALE_AUTH_KEY"
		# WLAN regulatory country used at first boot to unblock the radio for
		# BLE WiFi-onboarding (provision.sh defaults to NL when unset).
		[ -n "${WPA_COUNTRY:-}" ] && printf 'LEROBOT_WIFI_COUNTRY=%s\n' "$WPA_COUNTRY"
	} > "$ENV_STAGE_DIR/firstboot.env"
	chmod 0600 "$ENV_STAGE_DIR/firstboot.env"
	# Append a copy step to the stage run script only if not already present.
	RUN="$HERE/stage-teleop/00-install-teleop/01-run.sh"
	if ! grep -q "firstboot.env" "$RUN"; then
		printf '\n# injected: bake onboarding env\ninstall -m 0600 files/firstboot.env "${ROOTFS_DIR}/etc/lerobot/firstboot.env"\n' >> "$RUN"
	fi
fi

# 5) Copy our custom stage into pi-gen (after all edits to it are done) so it is
#    a real directory inside the mounted /pi-gen, then build.
rm -rf "$PIGEN_DIR/stage-teleop"
cp -a "$HERE/stage-teleop" "$PIGEN_DIR/stage-teleop"

cd "$PIGEN_DIR"
CONTINUE=1 ./build-docker.sh

echo ""
echo "✅ Image(s) in: $PIGEN_DIR/deploy/"
ls -lh "$PIGEN_DIR/deploy/" || true
