#!/bin/bash -e
#
# Bakes the teleop_lerobot repo into the image and installs a one-shot
# first-boot service that runs the repo's own install.sh once, natively.

FIRST_USER_NAME="${FIRST_USER_NAME:-pi}"
TELEOP_REPO_URL="${TELEOP_REPO_URL:-https://github.com/koenvanwijk/teleop_lerobot.git}"
TELEOP_REPO_REF="${TELEOP_REPO_REF:-main}"

USER_HOME="/home/${FIRST_USER_NAME}"
REPO_DIR="${USER_HOME}/teleop_lerobot"

# 1) Clone the repo into the user's home inside the image.
#    on_chroot runs `bash -e` and reads these commands from stdin; the ${..}
#    vars above are expanded on the host before the heredoc is sent.
on_chroot <<EOF
if [ ! -d "${REPO_DIR}/.git" ]; then
	git clone "${TELEOP_REPO_URL}" "${REPO_DIR}"
fi
cd "${REPO_DIR}"
git fetch --all --tags --prune || true
git checkout "${TELEOP_REPO_REF}"
git submodule update --init --recursive || true
chown -R "${FIRST_USER_NAME}:${FIRST_USER_NAME}" "${REPO_DIR}"
EOF

# 2) Install the first-boot provisioner + systemd unit.
install -d "${ROOTFS_DIR}/opt/lerobot-firstboot"
install -m 0755 files/provision.sh "${ROOTFS_DIR}/opt/lerobot-firstboot/provision.sh"
sed -i "s/__FIRST_USER__/${FIRST_USER_NAME}/g" "${ROOTFS_DIR}/opt/lerobot-firstboot/provision.sh"
install -m 0644 files/lerobot-firstboot.service "${ROOTFS_DIR}/etc/systemd/system/lerobot-firstboot.service"

# 3) Optional onboarding env (robot name / Tailscale key). build.sh appends a
#    copy step below when TELEOP_FIRSTBOOT_ENV/onboarding vars are set.
install -d "${ROOTFS_DIR}/etc/lerobot"

# 4) Enable the one-shot service so it runs on first boot.
on_chroot <<EOF
systemctl enable lerobot-firstboot.service
EOF
