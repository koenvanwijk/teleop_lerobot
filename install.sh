#!/usr/bin/env bash
set -euo pipefail

# LeRobot delivery installer / updater.
# Normal flow for a tested robot:
#   cd ~/teleop_lerobot && git pull --ff-only && ./install.sh && sudo reboot
#
# Guarantees:
# - repo calibration is imported every install/update
# - udev aliases are regenerated from mapping.csv
# - webserver starts on port 80 at reboot
# - teleoperation auto-start remains enabled at reboot
# - web teleop must never wait for an interactive calibration prompt

# ========= Config =========
CONDA_DIR="$HOME/miniconda3"
CONDA_ENV="lerobot"
LEROBOT_VERSION="0.6.1"
UDEV_RULE="/etc/udev/rules.d/99-usb-serial-aliases.rules"
WEBSERVER_SERVICE="/etc/systemd/system/lerobot-webserver.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ==========================

usage() {
  cat <<'EOF'
Gebruik: ./install.sh [opties]

Normale update voor een geteste robot:
  cd ~/teleop_lerobot
  git pull --ff-only
  ./install.sh
  sudo reboot

Opties:
  --lerobot-src <pad>      Installeer lerobot vanuit lokale bron met pip install -e
  --lerobot-git <url>      Clone lerobot uit Git en installeer editable
  --lerobot-branch <naam>  Branch/tag voor --lerobot-git
EOF
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

LEROBOT_SRC=""
LEROBOT_GIT=""
LEROBOT_BRANCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lerobot-src) LEROBOT_SRC="$2"; shift 2 ;;
    --lerobot-git) LEROBOT_GIT="$2"; shift 2 ;;
    --lerobot-branch) LEROBOT_BRANCH="$2"; shift 2 ;;
    *) echo "Onbekende optie: $1"; usage; exit 1 ;;
  esac
done

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    echo "🖥️  Architectuur: x86_64"
    ;;
  aarch64)
    MINICONDA_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh"
    echo "🍓 Architectuur: aarch64"
    ;;
  *)
    echo "❌ Niet-ondersteunde architectuur: $ARCH" >&2
    exit 1
    ;;
esac

# ---- System packages ----
if command -v apt-get >/dev/null 2>&1; then
  echo "🔧 Controleer system packages…"
  sudo apt-get update -y
  sudo apt-get install -y git curl bluetooth bluez openssh-client openssh-server
  sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd 2>/dev/null || true
fi

# ---- Conda ----
if [[ -x "$CONDA_DIR/bin/conda" ]]; then
  echo "✅ Conda al aanwezig: $CONDA_DIR"
else
  echo "⬇️  Installeer Conda/Miniforge…"
  TMP_SH="$(mktemp /tmp/miniconda.XXXXXX.sh)"
  curl -fsSL "$MINICONDA_URL" -o "$TMP_SH"
  bash "$TMP_SH" -b -p "$CONDA_DIR"
  rm -f "$TMP_SH"
fi

# shellcheck disable=SC1091
source "$CONDA_DIR/etc/profile.d/conda.sh"
conda init bash >/dev/null 2>&1 || true

if conda help | grep -q "\btos\b"; then
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r || true
fi

# ---- Python env + LeRobot ----
if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
  echo "✅ Conda env bestaat: $CONDA_ENV"
  CURRENT_PY=$(conda run -n "$CONDA_ENV" python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
  if [[ "$CURRENT_PY" != "3.12" ]]; then
    conda install -y -n "$CONDA_ENV" python=3.12
  fi
else
  echo "🧪 Maak conda env $CONDA_ENV met Python 3.12…"
  conda create -y -n "$CONDA_ENV" python=3.12
fi

conda activate "$CONDA_ENV"
pip install --upgrade pip

if [[ -n "$LEROBOT_SRC" ]]; then
  [[ -d "$LEROBOT_SRC" ]] || { echo "❌ Pad bestaat niet: $LEROBOT_SRC" >&2; exit 1; }
  pip install -e "$LEROBOT_SRC"[core_scripts,feetech]
elif [[ -n "$LEROBOT_GIT" ]]; then
  CLONE_DIR="$HOME/lerobot_src"
  rm -rf "$CLONE_DIR"
  if [[ -n "$LEROBOT_BRANCH" ]]; then
    git clone --branch "$LEROBOT_BRANCH" --single-branch "$LEROBOT_GIT" "$CLONE_DIR"
  else
    git clone "$LEROBOT_GIT" "$CLONE_DIR"
  fi
  pip install -e "$CLONE_DIR"[core_scripts,feetech]
else
  pip install "lerobot[core_scripts,feetech]==$LEROBOT_VERSION"
fi

pip install fastapi uvicorn[standard] pydantic websockets python-multipart opencv-python numpy draccus dbus-next netifaces

INSTALLED_VERSION=$(pip show lerobot | awk '/^Version:/ {print $2}')
echo "✅ LeRobot versie: ${INSTALLED_VERSION:-unknown}"

# ---- Calibration from repo is mandatory for delivery ----
echo "📋 Importeer repo-calibration naar LeRobot cache…"
if [[ ! -f "$SCRIPT_DIR/sync_calibration.sh" ]]; then
  echo "❌ sync_calibration.sh ontbreekt; delivery install kan calibration niet importeren" >&2
  exit 1
fi
bash "$SCRIPT_DIR/sync_calibration.sh" import

if [[ -d "$SCRIPT_DIR/calibration" ]]; then
  echo "✅ Repo-calibration aanwezig:"
  find "$SCRIPT_DIR/calibration" -type f -name '*.json' | sort | sed 's#^#   #'
else
  echo "❌ calibration/ map ontbreekt in repo" >&2
  exit 1
fi

# ---- Udev rules ----
echo "📝 Genereer udev-regels uit mapping.csv…"
MAPPING_FILE="$SCRIPT_DIR/mapping.csv"
[[ -f "$MAPPING_FILE" ]] || { echo "❌ mapping.csv ontbreekt: $MAPPING_FILE" >&2; exit 1; }
[[ -f "$SCRIPT_DIR/gen_udev_rules.py" ]] || { echo "❌ gen_udev_rules.py ontbreekt" >&2; exit 1; }

TMP_RULE="$(mktemp /tmp/udev.rules.XXXXXX)"
python3 "$SCRIPT_DIR/gen_udev_rules.py" "$MAPPING_FILE" --output "$TMP_RULE"
[[ -s "$TMP_RULE" ]] || { echo "❌ gen_udev_rules.py produceerde geen output" >&2; rm -f "$TMP_RULE"; exit 1; }

if [[ -f "$UDEV_RULE" ]]; then
  sudo cp -a "$UDEV_RULE" "${UDEV_RULE}.bak.$(date +%Y%m%d-%H%M%S)"
fi
sudo mv "$TMP_RULE" "$UDEV_RULE"
sudo chown root:root "$UDEV_RULE"
sudo chmod 0644 "$UDEV_RULE"
sudo udevadm control --reload
sudo udevadm trigger

# ---- NetworkManager rights for BLE WiFi provisioning ----
echo "🌐 Configureer NetworkManager-rechten voor BLE WiFi provisioning…"
SERVICE_USER="$USER"
POLKIT_RULE="/etc/polkit-1/rules.d/49-lerobot-networkmanager.rules"
sudo tee "$POLKIT_RULE" >/dev/null <<EOF
polkit.addRule(function(action, subject) {
  if ((action.id.indexOf("org.freedesktop.NetworkManager.") === 0) && subject.user == "$SERVICE_USER") {
    return polkit.Result.YES;
  }
});
EOF
sudo chmod 0644 "$POLKIT_RULE"
if getent group netdev >/dev/null 2>&1; then
  sudo usermod -aG netdev "$SERVICE_USER" || true
fi
sudo systemctl restart polkit 2>/dev/null || true
sudo systemctl restart NetworkManager 2>/dev/null || true

# ---- Bluetooth headless config ----
echo "📡 Configureer Bluetooth headless pairing…"
BLUETOOTH_CONF="/etc/bluetooth/main.conf"
if [[ -f "$BLUETOOTH_CONF" ]]; then
  [[ -f "${BLUETOOTH_CONF}.bak" ]] || sudo cp "$BLUETOOTH_CONF" "${BLUETOOTH_CONF}.bak"
  if grep -q "^#\?AlwaysPairable" "$BLUETOOTH_CONF"; then
    sudo sed -i 's/^#\?AlwaysPairable.*/AlwaysPairable = true/' "$BLUETOOTH_CONF"
  else
    sudo sed -i '/^\[Policy\]/a AlwaysPairable = true' "$BLUETOOTH_CONF" || true
  fi
  if grep -q "^#\?JustWorksRepairing" "$BLUETOOTH_CONF"; then
    sudo sed -i 's/^#\?JustWorksRepairing.*/JustWorksRepairing = always/' "$BLUETOOTH_CONF"
  else
    sudo sed -i '/^\[Policy\]/a JustWorksRepairing = always' "$BLUETOOTH_CONF" || true
  fi
  sudo systemctl restart bluetooth || true
fi

# ---- Webserver systemd service: autostart at reboot ----
WEBSERVER_SCRIPT="$SCRIPT_DIR/webserver.py"
CONDA_BIN="$CONDA_DIR/condabin/conda"
[[ -f "$WEBSERVER_SCRIPT" ]] || { echo "❌ webserver.py ontbreekt" >&2; exit 1; }
chmod +x "$WEBSERVER_SCRIPT"

# Remove old @reboot cron entry to avoid duplicate webservers.
if crontab -l 2>/dev/null | grep -qF "webserver"; then
  (crontab -l 2>/dev/null | grep -vF "webserver" || true) | crontab -
fi

sudo tee "$WEBSERVER_SERVICE" >/dev/null <<EOF
[Unit]
Description=LeRobot Teleoperation Web Server
After=local-fs.target
Before=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment=PYTHONUNBUFFERED=1
Environment=LEROBOT_WEB_SSH=1
Environment=PORT=80
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ExecStart=$CONDA_BIN run --no-capture-output -n $CONDA_ENV python -u $WEBSERVER_SCRIPT
Restart=always
RestartSec=2
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable lerobot-webserver.service
sudo systemctl restart lerobot-webserver.service

# ---- Browser autostart after graphical login ----
WEBUI_URL="http://localhost/"
WEBUI_LAUNCHER_DIR="$HOME/.local/bin"
WEBUI_LAUNCHER="$WEBUI_LAUNCHER_DIR/lerobot-open-webui"
WEBUI_AUTOSTART_DIR="$HOME/.config/autostart"
WEBUI_AUTOSTART="$WEBUI_AUTOSTART_DIR/lerobot-webui.desktop"
mkdir -p "$WEBUI_LAUNCHER_DIR" "$WEBUI_AUTOSTART_DIR"

cat > "$WEBUI_LAUNCHER" <<'WEBUI_LAUNCHER_EOF'
#!/usr/bin/env bash
set -u
URL="http://localhost/"
STATE_DIR="$HOME/.local/state"
LOG="$STATE_DIR/lerobot-webui-autostart.log"
mkdir -p "$STATE_DIR"
exec >>"$LOG" 2>&1

echo "[$(date -Is)] LeRobot browser autostart launched"

ready=0
for _ in $(seq 1 60); do
  if (echo >/dev/tcp/127.0.0.1/80) >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  echo "[$(date -Is)] Webserver did not become reachable on port 80"
  exit 1
fi

if command -v google-chrome >/dev/null 2>&1; then
  nohup google-chrome --new-window "$URL" >/dev/null 2>&1 &
elif command -v google-chrome-stable >/dev/null 2>&1; then
  nohup google-chrome-stable --new-window "$URL" >/dev/null 2>&1 &
elif command -v chromium >/dev/null 2>&1; then
  nohup chromium --new-window "$URL" >/dev/null 2>&1 &
elif command -v chromium-browser >/dev/null 2>&1; then
  nohup chromium-browser --new-window "$URL" >/dev/null 2>&1 &
elif command -v firefox >/dev/null 2>&1; then
  nohup firefox --new-window "$URL" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
  nohup xdg-open "$URL" >/dev/null 2>&1 &
elif command -v gio >/dev/null 2>&1; then
  nohup gio open "$URL" >/dev/null 2>&1 &
else
  echo "[$(date -Is)] No supported browser launcher found"
  exit 1
fi

echo "[$(date -Is)] Browser launch requested for $URL"
exit 0
WEBUI_LAUNCHER_EOF
chmod +x "$WEBUI_LAUNCHER"

cat > "$WEBUI_AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=LeRobot Control Center
Comment=Open the local LeRobot web interface after desktop login
Exec=$WEBUI_LAUNCHER
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

echo ""
echo "✅ Installatie/update compleet"
echo ""
echo "Bij reboot automatisch:"
echo "  1. webserver op http://localhost/ en http://<ip>/"
echo "  2. Bluetooth IP/WiFi provisioning"
echo "  3. AP fallback LeRobot-AP als geen netwerk bereikbaar is"
echo "  4. teleoperation start automatisch als leader+follower aanwezig zijn"
echo "  5. web teleop gebruikt bestaande repo-calibration zonder Enter-prompt"
echo ""
echo "Controle:"
echo "  sudo systemctl status lerobot-webserver.service"
echo "  journalctl -u lerobot-webserver.service -b -n 200 --no-pager"
echo "  ls -R ~/.cache/huggingface/lerobot/calibration"
echo ""
