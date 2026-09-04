#!/usr/bin/env bash
set -euo pipefail

# ========= Config =========
CONDA_DIR="$HOME/miniconda3"
CONDA_ENV="lerobot"
LEROBOT_VERSION="0.4.3"  # Exacte versie voor consistentie (belangrijke wijzigingen in 0.4.3: so101/so100 → so)
UDEV_RULE="/etc/udev/rules.d/99-usb-serial-aliases.rules"
GITHUB_REPO="koenvanwijk/teleop_lerobot"
# ==========================

usage() {
  cat <<'EOF'
Gebruik: ./install.sh

Deze installer is idempotent en is ook de upgrade-entrypoint.
Aanbevolen upgrade:
  cd ~/teleop_lerobot
  git pull --ff-only
  ./install.sh
  sudo reboot

Installeert:
- Miniconda met Python 3.10
- lerobot package met feetech support
- Udev rules (gedownload van laatste GitHub release)

Ondersteunt: x86_64 (Intel/AMD) en aarch64 (ARM64/Raspberry Pi)

Symlinks:
  /dev/tty_<nice>_<role>   (bv. /dev/tty_black_leader)
  /dev/tty_follower        (voor elke follower)
  /dev/tty_leader          (voor elke leader)

Opties:
  --lerobot-src <pad>      Installeer lerobot vanuit lokale bron met 'pip install -e <pad>'
  --lerobot-git <url>      Clone lerobot uit Git en installeer editable
  --lerobot-branch <naam>  (optioneel) Branch/tag voor --lerobot-git
EOF
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

# Parseer eenvoudige opties
LEROBOT_SRC=""
LEROBOT_GIT=""
LEROBOT_BRANCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lerobot-src)
      LEROBOT_SRC="$2"; shift 2 ;;
    --lerobot-git)
      LEROBOT_GIT="$2"; shift 2 ;;
    --lerobot-branch)
      LEROBOT_BRANCH="$2"; shift 2 ;;
    *)
      echo "Onbekende optie: $1"; usage; exit 1 ;;
  esac
done

# Detecteer architectuur
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    echo "🖥️  Detecteerde architectuur: x86_64 (Intel/AMD)"
    ;;
  aarch64)
    MINICONDA_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh"
    echo "🍓 Detecteerde architectuur: aarch64 (ARM64/Raspberry Pi)"
    ;;
  *)
    echo "❌ Niet-ondersteunde architectuur: $ARCH"
    echo "   Ondersteund: x86_64, aarch64"
    exit 1
    ;;
esac

# ---- 1) Miniconda installeren (idempotent) ----
if [[ -x "$CONDA_DIR/bin/conda" ]]; then
  echo "✅ Miniconda al aanwezig: $CONDA_DIR"
else
  echo "⬇️  Download Miniconda…"
  TMP_SH="$(mktemp /tmp/miniconda.XXXXXX.sh)"
  curl -fsSL "$MINICONDA_URL" -o "$TMP_SH"
  echo "🛠  Installeren naar $CONDA_DIR…"
  bash "$TMP_SH" -b -p "$CONDA_DIR"
  rm -f "$TMP_SH"
  
  echo "🔧 Initialiseer conda voor bash…"
  "$CONDA_DIR/bin/conda" init bash
  echo "✅ Conda init compleet (herstart shell of run 'source ~/.bashrc')"
fi

# Conda in deze shell
# shellcheck disable=SC1091
source "$CONDA_DIR/etc/profile.d/conda.sh"

# Als conda al bestond, run conda init toch (idempotent)
if ! grep -q "conda initialize" "$HOME/.bashrc" 2>/dev/null; then
  echo "🔧 Initialiseer conda voor bash…"
  conda init bash
  echo "✅ Conda init compleet"
fi

# Accepteer TOS (alleen beschikbaar op Anaconda/Miniconda; niet op Miniforge/Mamba)
# Check of de 'conda tos' subcommand bestaat, anders overslaan.
if conda help | grep -q "\btos\b"; then
  echo "📝 Conda TOS subcommand gevonden: accepteer TOS voor main en r kanalen…"
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r || true
else
  echo "ℹ️  'conda tos' niet beschikbaar (Miniforge/Mamba): TOS-acceptatie overgeslagen."
fi

# ---- 2) Env 'lerobot' met Python 3.10 + lerobot ----
if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
  echo "✅ Conda env bestaat: $CONDA_ENV"
else
  echo "🧪 Maak env $CONDA_ENV (python=3.12)…"
  conda create -y -n "$CONDA_ENV" python=3.12
fi

echo "📦 pip install lerobot en dependencies…"
conda activate "$CONDA_ENV"
pip install --upgrade pip

# ---- Verwijder oude lerobot versie (clean install) ----
echo ""
echo "🗑️  Controleer bestaande lerobot versie..."
if pip show lerobot >/dev/null 2>&1; then
  OLD_VERSION=$(pip show lerobot | grep "^Version:" | awk '{print $2}')
  echo "   Huidige versie: $OLD_VERSION"
  if [[ "$OLD_VERSION" != "$LEROBOT_VERSION" ]]; then
    echo "   Verwijderen oude versie..."
    pip uninstall -y lerobot || echo "⚠️  Kon lerobot niet verwijderen"
  else
    echo "   ✅ Juiste versie al geïnstalleerd ($LEROBOT_VERSION)"
  fi
else
  echo "   Geen bestaande lerobot installatie gevonden"
fi
echo ""

# Kies installatiemodus voor lerobot
if [[ -n "$LEROBOT_SRC" ]]; then
  echo "🔗 Installeer lerobot editable vanuit lokale bron: $LEROBOT_SRC"
  if [[ ! -d "$LEROBOT_SRC" ]]; then
    echo "❌ Opgegeven pad bestaat niet: $LEROBOT_SRC"; exit 1
  fi
  pip install -e "$LEROBOT_SRC"[feetech]
elif [[ -n "$LEROBOT_GIT" ]]; then
  echo "🌿 Clone lerobot uit Git: $LEROBOT_GIT ${LEROBOT_BRANCH:+(branch: $LEROBOT_BRANCH)}"
  if ! command -v git >/dev/null 2>&1; then
    echo "🔧 Installeer git…"
    sudo apt-get update -y && sudo apt-get install -y git
  fi
  CLONE_DIR="$HOME/lerobot_src"
  rm -rf "$CLONE_DIR"
  if [[ -n "$LEROBOT_BRANCH" ]]; then
    git clone --branch "$LEROBOT_BRANCH" --single-branch "$LEROBOT_GIT" "$CLONE_DIR"
  else
    git clone "$LEROBOT_GIT" "$CLONE_DIR"
  fi
  echo "🧪 Editable install: $CLONE_DIR"
  pip install -e "$CLONE_DIR"[feetech]
else
  echo "📦 Installeer lerobot v$LEROBOT_VERSION vanaf PyPI (met feetech)"
  pip install "lerobot[feetech]==$LEROBOT_VERSION"
fi

# ---- Verificatie van geïnstalleerde versie ----
echo ""
echo "✅ Verificatie lerobot versie:"
if pip show lerobot >/dev/null 2>&1; then
  INSTALLED_VERSION=$(pip show lerobot | grep "^Version:" | awk '{print $2}')
  echo "   Geïnstalleerde versie: $INSTALLED_VERSION"
  if [[ -z "$LEROBOT_SRC" && -z "$LEROBOT_GIT" ]]; then
    if [[ "$INSTALLED_VERSION" != "$LEROBOT_VERSION" ]]; then
      echo "   ⚠️  WAARSCHUWING: Verwachte versie $LEROBOT_VERSION, maar geïnstalleerd: $INSTALLED_VERSION"
    else
      echo "   ✅ Versie komt overeen!"
    fi
  fi
else
  echo "   ❌ FOUT: lerobot niet gedetecteerd na installatie!"
  exit 1
fi
echo ""
pip install fastapi uvicorn[standard] pydantic websockets python-multipart
pip install opencv-python numpy draccus

# SSH client/server for the LAN-only browser SSH terminal.
if command -v apt-get >/dev/null 2>&1; then
  echo "💻 Controleer OpenSSH voor webterminal…"
  if ! command -v ssh >/dev/null 2>&1 || ! command -v sshd >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y openssh-client openssh-server
  fi
  sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd 2>/dev/null || true
fi

# Bluetooth dependencies (optioneel) - Using Bleak (modern BLE library)
echo "📡 Installeer Bluetooth dependencies…"
if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "x86_64" ]]; then
  # Installeer system dependencies
  if command -v apt-get >/dev/null 2>&1; then
    echo "🔧 Installeer bluetooth system packages…"
    sudo apt-get install -y bluetooth bluez || {
      echo "⚠️  Kon bluetooth packages niet installeren"
    }
  fi
  
  # Installeer Python packages voor BLE advertising
  pip install dbus-next netifaces || {
    echo "⚠️  Kon dbus-next niet installeren (optioneel)"
    echo "   BLE advertising zal niet beschikbaar zijn"
  }
else
  echo "⚠️  Bluetooth overgeslagen voor architectuur: $ARCH"
fi

# ---- 3) Calibration files installeren ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/sync_calibration.sh" ]]; then
  echo "📋 Installeer calibration files…"
  "$SCRIPT_DIR/sync_calibration.sh" import
else
  echo "⚠️  sync_calibration.sh niet gevonden, overgeslagen"
fi

# ---- 4) Udev rules genereren uit mapping.csv ----
echo "📝 Genereer udev-regels uit mapping.csv…"

# Check of mapping.csv bestaat
MAPPING_FILE="$SCRIPT_DIR/mapping.csv"
if [[ ! -f "$MAPPING_FILE" ]]; then
  echo "❌ mapping.csv niet gevonden: $MAPPING_FILE"
  echo "   Gebruik ./create_mapping.sh om mapping.csv te maken"
  exit 1
fi

# Backup bestaand rules-bestand
if [[ -f "$UDEV_RULE" ]]; then
  sudo cp -a "$UDEV_RULE" "${UDEV_RULE}.bak.$(date +%Y%m%d-%H%M%S)"
  echo "🗂  Backup: ${UDEV_RULE}.bak.*"
fi

# Genereer udev rules uit mapping.csv
TMP_RULE="$(mktemp /tmp/udev.rules.XXXXXX)"

echo "   • Lezen mapping.csv: $MAPPING_FILE"
python3 "$SCRIPT_DIR/gen_udev_rules.py" "$MAPPING_FILE" --output "$TMP_RULE"

if [[ ! -s "$TMP_RULE" ]]; then
  echo "❌ gen_udev_rules.py produceerde geen output"
  rm -f "$TMP_RULE"
  exit 1
fi

echo "✅ Udev rules gegenereerd uit mapping.csv"

echo "📝 Schrijf naar $UDEV_RULE…"
sudo mv "$TMP_RULE" "$UDEV_RULE"
sudo chown root:root "$UDEV_RULE"
sudo chmod 0644 "$UDEV_RULE"

echo "🔁 Udev reload + trigger…"
sudo udevadm control --reload
sudo udevadm trigger

# ---- 4.5) Bluetooth configuratie voor headless pairing ----
echo "📡 Configureer Bluetooth voor automatische pairing (headless mode)…"

BLUETOOTH_CONF="/etc/bluetooth/main.conf"
if [[ -f "$BLUETOOTH_CONF" ]]; then
  # Backup bestaande configuratie
  if [[ ! -f "${BLUETOOTH_CONF}.bak" ]]; then
    sudo cp "$BLUETOOTH_CONF" "${BLUETOOTH_CONF}.bak"
    echo "🗂  Backup: ${BLUETOOTH_CONF}.bak"
  fi
  
  # Configureer AlwaysPairable en JustWorksRepairing voor automatische pairing zonder user input
  # Dit voorkomt "Please confirm code..." prompts op headless systemen
  
  # Check en update AlwaysPairable
  if grep -q "^#\?AlwaysPairable" "$BLUETOOTH_CONF"; then
    sudo sed -i 's/^#\?AlwaysPairable.*/AlwaysPairable = true/' "$BLUETOOTH_CONF"
  else
    # Voeg toe onder [Policy] sectie
    sudo sed -i '/^\[Policy\]/a AlwaysPairable = true' "$BLUETOOTH_CONF"
  fi
  
  # Check en update JustWorksRepairing
  if grep -q "^#\?JustWorksRepairing" "$BLUETOOTH_CONF"; then
    sudo sed -i 's/^#\?JustWorksRepairing.*/JustWorksRepairing = always/' "$BLUETOOTH_CONF"
  else
    sudo sed -i '/^\[Policy\]/a JustWorksRepairing = always' "$BLUETOOTH_CONF"
  fi
  
  echo "✅ Bluetooth configuratie bijgewerkt voor headless pairing"
  
  # Disable GNOME Bluetooth agents and pairing dialogs aggressively
  if command -v systemctl >/dev/null 2>&1; then
    echo "🔇 Uitschakelen GNOME Bluetooth agents en pairing dialogs…"
    
    # Disable obex service
    systemctl --user mask obex.service 2>/dev/null || true
    systemctl --user stop obex.service 2>/dev/null || true
    
    # Kill any running GNOME Bluetooth agent processes
    pkill -f gnome-bluetooth-agent 2>/dev/null || true
    pkill -f bluetooth-agent 2>/dev/null || true
    pkill -f blueman-agent 2>/dev/null || true
    
    # Disable GNOME Settings daemon's Bluetooth pairing plugin (if exists)
    if [[ -d "/usr/lib/gnome-settings-daemon-3.0" ]]; then
      # Create override to disable Bluetooth pairing UI
      mkdir -p "$HOME/.config/autostart"
      
      # Disable bluetooth applet if it exists
      if [[ -f "/etc/xdg/autostart/blueman.desktop" ]]; then
        cat > "$HOME/.config/autostart/blueman.desktop" <<'AUTOSTART_EOF'
[Desktop Entry]
Type=Application
Name=Blueman
Hidden=true
AUTOSTART_EOF
        echo "   • Disabled blueman autostart"
      fi
    fi
    
    echo "   • GNOME Bluetooth GUI agents uitgeschakeld"
    echo "   ⚠️  BELANGRIJK: Log uit en in om GUI dialogen volledig te verwijderen"
  fi
  
  # Herstart Bluetooth service om veranderingen toe te passen
  echo "🔄 Herstarten Bluetooth service…"
  sudo systemctl restart bluetooth
  sleep 2
  
  echo "✅ Bluetooth geconfigureerd voor automatische pairing zonder GUI prompts"
  echo ""
  echo "⚠️  BELANGRIJK voor GUI systemen (GNOME/Ubuntu Desktop):"
  echo "   Om pairing dialogs volledig te verwijderen:"
  echo "   1. Log uit en weer in (of herstart)"
  echo "   2. Zorg dat geen Bluetooth applets actief zijn in systray"
  echo "   3. Test: 'ps aux | grep bluetooth-agent' moet leeg zijn"
else
  echo "⚠️  Bluetooth configuratie bestand niet gevonden: $BLUETOOTH_CONF"
  echo "   Bluetooth agent in bluetooth_gatt_server.py zal nog steeds automatisch pairing doen"
fi

# ---- 5) Vroege systemd auto-start voor webserver ----
WEBSERVER_SCRIPT="$SCRIPT_DIR/webserver.py"
CONDA_BIN="$CONDA_DIR/condabin/conda"
WEBSERVER_SERVICE="/etc/systemd/system/lerobot-webserver.service"

if [[ -f "$WEBSERVER_SCRIPT" ]]; then
  echo "🔧 Configureer vroege systemd start voor webserver.py…"
  chmod +x "$WEBSERVER_SCRIPT"

  # Remove the old @reboot cron entry to prevent two webservers after upgrades.
  if crontab -l 2>/dev/null | grep -qF "webserver"; then
    echo "🗑️  Verwijder oude @reboot webserver entry uit crontab…"
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

  echo "✅ systemd service actief: lerobot-webserver.service"
  echo "   Status: sudo systemctl status lerobot-webserver.service"
  echo "   Logs:   journalctl -u lerobot-webserver.service -f"
  echo "   Web:    http://localhost:5000"
  echo "   SSH UI: http://localhost:5000/ssh"
else
  echo "⚠️  webserver.py niet gevonden, systemd service overgeslagen"
fi

# ---- 6) Open de lokale Web GUI automatisch na grafische login ----
# XDG autostart wordt alleen uitgevoerd in een desktop sessie en heeft dus
# geen effect op headless robots.
WEBUI_URL="http://localhost:5000/"
WEBUI_LAUNCHER_DIR="$HOME/.local/bin"
WEBUI_LAUNCHER="$WEBUI_LAUNCHER_DIR/lerobot-open-webui"
WEBUI_AUTOSTART_DIR="$HOME/.config/autostart"
WEBUI_AUTOSTART="$WEBUI_AUTOSTART_DIR/lerobot-webui.desktop"

mkdir -p "$WEBUI_LAUNCHER_DIR" "$WEBUI_AUTOSTART_DIR"

cat > "$WEBUI_LAUNCHER" <<'WEBUI_LAUNCHER_EOF'
#!/usr/bin/env bash
set -u

URL="http://localhost:5000/"

# Wait up to one minute for the local FastAPI listener. This keeps the browser
# from showing a connection error during a cold boot or slow desktop login.
for _ in $(seq 1 60); do
  if (echo >/dev/tcp/127.0.0.1/5000) >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Use the configured default browser where possible, with common fallbacks.
if command -v xdg-open >/dev/null 2>&1; then
  exec xdg-open "$URL"
elif command -v gio >/dev/null 2>&1; then
  exec gio open "$URL"
elif command -v firefox >/dev/null 2>&1; then
  exec firefox "$URL"
elif command -v chromium >/dev/null 2>&1; then
  exec chromium "$URL"
elif command -v chromium-browser >/dev/null 2>&1; then
  exec chromium-browser "$URL"
fi

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

echo "✅ Desktop autostart geconfigureerd: standaard browser opent $WEBUI_URL na login"

echo ""
echo "✅ Installatie compleet!"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📋 Geïnstalleerde componenten:"
echo "   • Miniconda met conda env 'lerobot'"
echo "   • lerobot package v$LEROBOT_VERSION met feetech support"
echo "   • FastAPI webserver met uvicorn (auto-start bij reboot)"
echo "   • Web GUI opent automatisch in de standaard browser na grafische login"
echo "   • Camera streaming met OpenCV (multi-camera support)"
echo "   • Network management (AP/WiFi switching)"
echo "   • Bluetooth GATT server (headless auto-pairing)"
echo "   • WebSocket real-time updates"
echo "   • Udev rules voor USB devices"
echo "   • Calibration files"
echo ""
echo "🚀 Bij reboot (AUTOMATISCH):"
echo "   1. Webserver start direct via systemd; hardware initialiseert daarna op de achtergrond"
echo "   2. Devices worden gedetecteerd"
echo "   3. Camera's worden geïnitialiseerd"
echo "   4. Teleoperation start automatisch!"
echo "   5. Bij grafische login opent de standaard browser automatisch"
echo "   6. Web interface: http://localhost:5000"
echo ""
echo "🔄 Voor toekomstige updates:"
echo "   cd $SCRIPT_DIR && git pull --ff-only && ./install.sh && sudo reboot"
echo ""
echo "⚡ Plug & Play:"
echo "   Sluit USB devices + cameras aan → Reboot → Klaar!"
echo ""
echo "🛠️  Handmatig gebruik:"
echo "   • Webserver: python webserver.py"
echo "   • Of met uvicorn: uvicorn webserver:app --host 0.0.0.0 --port 5000"
echo "   • Interactieve selectie: ./select_teleop.py"
echo "   • Direct: lerobot-teleoperate --robot.type=... --robot.port=..."
echo ""
echo "🌐 Web Control Interface (NIEUWE FEATURES!):"
echo "   • Lokaal: http://localhost:5000"
echo "   • Netwerk: http://[IP]:5000"
echo "   • API docs: http://localhost:5000/docs"
echo "   • Health check: http://localhost:5000/health"
echo ""
echo "✨ Features:"
echo "   🎮 Teleoperation: Start/Stop control"
echo "   📹 Cameras: Live MJPEG streaming"
echo "   🌐 Network: AP/WiFi management"
echo "   📡 Bluetooth: IP query + headless auto-pairing"
echo "   🔌 WebSocket: Real-time updates"
echo "   ⚙️  System: Info & monitoring"
echo ""
echo "📖 Zie FEATURES.md voor complete documentatie"
echo ""
echo "📝 Logs:"
echo "   • Webserver: tail -f ~/webserver.log"
echo "   • Teleoperation: tail -f ~/teleoperation.log"
echo ""
echo "📖 Documentatie:"
echo "   • README_TELEOP.md - Teleoperation uitleg"
echo "   • MAPPING.md - Device mapping info"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ---- 6) Activate conda environment 'lerobot' (optional convenience) ----
# Try to activate the environment so the user can immediately start using commands.
# If conda or the env is missing, print a helpful message and continue.
activate_lerobot_env() {
  # Ensure conda is initialized in this shell
  if [[ -f "$CONDA_DIR/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1090
    . "$CONDA_DIR/etc/profile.d/conda.sh"
  fi

  if ! command -v conda >/dev/null 2>&1; then
    echo "[INFO] Conda not available in current shell. Skipping activation."
    echo "       You can manually activate later: 'source ~/.bashrc && conda activate $CONDA_ENV'"
    return 0
  fi

  if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    echo "Activating conda environment: $CONDA_ENV"
    conda activate "$CONDA_ENV" || {
      echo "[WARN] Failed to activate '$CONDA_ENV'. Try manually: 'conda activate $CONDA_ENV'"
      return 0
    }
    python -V || true
    which python || true
  else
    echo "[INFO] Conda environment '$CONDA_ENV' not found. Skipping activation."
    echo "       Create it or ensure it was installed, then run: 'conda activate $CONDA_ENV'"
  fi
}

activate_lerobot_env

