#!/usr/bin/env bash
set -euo pipefail

# Create a local support ZIP for remote troubleshooting.
# Usage:
#   ./support_bundle.sh
#   ./support_bundle.sh --output /tmp/lerobot-support.zip

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT=""

usage() {
  cat <<'EOF'
Gebruik: ./support_bundle.sh [--output <zip-pad>]

Maakt een support-bundle ZIP met logs, systeemstatus, netwerkstatus,
USB-device-info, Tailscale-status en repo/calibratie-info.
Secrets zoals Tailscale auth keys en password/psk velden worden best-effort
uit tekstbestanden verwijderd.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Onbekende optie: $1" >&2; usage; exit 1 ;;
  esac
done

HOSTNAME_SAFE="$(hostname 2>/dev/null || echo lerobot)"
HOSTNAME_SAFE="${HOSTNAME_SAFE//[^A-Za-z0-9_.-]/_}"
TS="$(date +%Y%m%d-%H%M%S)"
BUNDLE_DIR="$(mktemp -d /tmp/lerobot-support.XXXXXX)"
STAGE="$BUNDLE_DIR/lerobot-support-$HOSTNAME_SAFE-$TS"
mkdir -p "$STAGE"/{systemd,logs,network,hardware,repo,python,calibration}

if [[ -z "$OUTPUT" ]]; then
  OUT_DIR="$HOME/lerobot-support-bundles"
  mkdir -p "$OUT_DIR"
  OUTPUT="$OUT_DIR/lerobot-support-$HOSTNAME_SAFE-$TS.zip"
fi

run_capture() {
  local outfile="$1"
  shift
  {
    echo "# $*"
    echo "# captured: $(date -Is)"
    echo
    "$@"
  } > "$outfile" 2>&1 || true
}

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst" 2>/dev/null || true
  fi
}

{
  echo "LeRobot support bundle"
  echo "created_at=$(date -Is)"
  echo "hostname=$(hostname 2>/dev/null || true)"
  echo "user=$USER"
  echo "pwd=$PWD"
  echo "script_dir=$SCRIPT_DIR"
  echo "kernel=$(uname -a 2>/dev/null || true)"
  echo "os_release="
  cat /etc/os-release 2>/dev/null || true
} > "$STAGE/manifest.txt"

# Systemd / service status
run_capture "$STAGE/systemd/lerobot-webserver.status.txt" systemctl status lerobot-webserver.service --no-pager
run_capture "$STAGE/systemd/lerobot-webserver.journal-current-boot.txt" journalctl -u lerobot-webserver.service -b -n 1000 --no-pager
run_capture "$STAGE/systemd/failed-units.txt" systemctl --failed --no-pager

# Local log files
copy_if_exists "$SCRIPT_DIR/webserver.log" "$STAGE/logs/webserver.log"
copy_if_exists "$SCRIPT_DIR/teleoperation.log" "$STAGE/logs/teleoperation.log"
copy_if_exists "$HOME/webserver.log" "$STAGE/logs/home-webserver.log"
copy_if_exists "$HOME/teleoperation.log" "$STAGE/logs/home-teleoperation.log"
copy_if_exists "$HOME/startup.log" "$STAGE/logs/startup.log"
copy_if_exists "$HOME/.local/state/lerobot-webui-autostart.log" "$STAGE/logs/lerobot-webui-autostart.log"

# Network and Tailscale
run_capture "$STAGE/network/ip-addr.txt" ip addr
run_capture "$STAGE/network/ip-route.txt" ip route
run_capture "$STAGE/network/resolvectl.txt" resolvectl status
run_capture "$STAGE/network/nmcli-device-status.txt" nmcli device status
run_capture "$STAGE/network/nmcli-connection-show.txt" nmcli connection show
run_capture "$STAGE/network/ss-listening.txt" ss -ltnp
if command -v tailscale >/dev/null 2>&1; then
  run_capture "$STAGE/network/tailscale-version.txt" tailscale version
  run_capture "$STAGE/network/tailscale-ip.txt" tailscale ip -4
  run_capture "$STAGE/network/tailscale-status.txt" tailscale status
  run_capture "$STAGE/network/tailscale-debug-prefs.txt" tailscale debug prefs
else
  echo "tailscale command not installed" > "$STAGE/network/tailscale-status.txt"
fi

# Hardware
run_capture "$STAGE/hardware/lsusb.txt" lsusb
run_capture "$STAGE/hardware/tty-links.txt" bash -lc 'ls -la /dev/tty* /dev/serial/by-id/* 2>/dev/null'
run_capture "$STAGE/hardware/video-devices.txt" bash -lc 'ls -la /dev/video* 2>/dev/null'
run_capture "$STAGE/hardware/dmesg-usb-tty.txt" bash -lc 'dmesg | grep -Ei "usb|tty|serial|feetech|ch340|cp210|ftdi" | tail -n 300'
copy_if_exists "/etc/udev/rules.d/99-usb-serial-aliases.rules" "$STAGE/hardware/99-usb-serial-aliases.rules"
copy_if_exists "$SCRIPT_DIR/mapping.csv" "$STAGE/hardware/mapping.csv"

# Repo and calibration
if command -v git >/dev/null 2>&1 && git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  run_capture "$STAGE/repo/git-status.txt" git -C "$SCRIPT_DIR" status --short --branch
  run_capture "$STAGE/repo/git-rev-parse.txt" git -C "$SCRIPT_DIR" rev-parse HEAD
  run_capture "$STAGE/repo/git-remote.txt" git -C "$SCRIPT_DIR" remote -v
  run_capture "$STAGE/repo/git-log-recent.txt" git -C "$SCRIPT_DIR" log --oneline -n 20
fi
run_capture "$STAGE/calibration/repo-calibration-list.txt" bash -lc "find '$SCRIPT_DIR/calibration' -type f -maxdepth 5 -print 2>/dev/null | sort"
run_capture "$STAGE/calibration/cache-calibration-list.txt" bash -lc "find '$HOME/.cache/huggingface/lerobot/calibration' -type f -maxdepth 8 -print 2>/dev/null | sort"

# Python/Conda state
run_capture "$STAGE/python/python-version.txt" python3 --version
if [[ -x "$HOME/miniconda3/condabin/conda" ]]; then
  run_capture "$STAGE/python/conda-env-list.txt" "$HOME/miniconda3/condabin/conda" env list
  run_capture "$STAGE/python/pip-freeze-lerobot.txt" "$HOME/miniconda3/condabin/conda" run -n lerobot python -m pip freeze
fi

# Best-effort redaction of obvious secrets in copied text files.
while IFS= read -r -d '' file; do
  sed -i -E \
    -e 's/(password|passwd|psk|auth[-_ ]?key|TAILSCALE_AUTH_KEY|tskey-auth)[=:][^[:space:]]+/\1=REDACTED/Ig' \
    -e 's/tskey-auth-[A-Za-z0-9_-]+/tskey-auth-REDACTED/g' \
    -e 's/(wifi-sec\.psk:)[[:space:]]+.*/\1 REDACTED/Ig' \
    "$file" 2>/dev/null || true
done < <(find "$STAGE" -type f -print0)

if ! command -v zip >/dev/null 2>&1; then
  echo "❌ zip command ontbreekt; installeer met: sudo apt-get install -y zip" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"
(
  cd "$BUNDLE_DIR"
  zip -qr "$OUTPUT" "$(basename "$STAGE")"
)
rm -rf "$BUNDLE_DIR"

echo "$OUTPUT"
