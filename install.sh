#!/usr/bin/env bash
set -euo pipefail

# ========= Config =========
CONDA_DIR="$HOME/miniconda3"
CONDA_ENV="lerobot"
UDEV_RULE="/etc/udev/rules.d/99-usb-serial-aliases.rules"
GITHUB_REPO="koenvanwijk/teleop_lerobot"
# ==========================

usage() {
  cat <<'EOF'
Gebruik: ./install.sh

Installeert:
- Miniconda met Python 3.10
- lerobot package met feetech support
- Udev rules (gedownload van laatste GitHub release)

Ondersteunt: x86_64 (Intel/AMD) en aarch64 (ARM64/Raspberry Pi)

Symlinks:
  /dev/tty_<nice>_<role>   (bv. /dev/tty_black_leader)
  /dev/tty_follower        (voor elke follower)
  /dev/tty_leader          (voor elke leader)
EOF
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

# Detecteer architectuur
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    echo "🖥️  Detecteerde architectuur: x86_64 (Intel/AMD)"
    ;;
  aarch64)
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh"
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

# Accepteer TOS (nodig voor conda install e.d.)
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# ---- 2) Env 'lerobot' met Python 3.10 + lerobot ----
if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
  echo "✅ Conda env bestaat: $CONDA_ENV"
else
  echo "🧪 Maak env $CONDA_ENV (python=3.10)…"
  conda create -y -n "$CONDA_ENV" python=3.10
fi

echo "📦 pip install lerobot en dependencies…"
conda activate "$CONDA_ENV"
pip install --upgrade pip
pip install lerobot[feetech]
pip install fastapi uvicorn[standard] pydantic websockets python-multipart
pip install opencv-python numpy

# ---- 3) Calibration files installeren ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/sync_calibration.sh" ]]; then
  echo "📋 Installeer calibration files…"
  "$SCRIPT_DIR/sync_calibration.sh" import
else
  echo "⚠️  sync_calibration.sh niet gevonden, overgeslagen"
fi

# ---- 4) Udev rules downloaden ----
echo "⬇️  Download udev-regels van GitHub release…"

# Backup bestaand rules-bestand
if [[ -f "$UDEV_RULE" ]]; then
  sudo cp -a "$UDEV_RULE" "${UDEV_RULE}.bak.$(date +%Y%m%d-%H%M%S)"
  echo "🗂  Backup: ${UDEV_RULE}.bak.*"
fi

TMP_RULE="$(mktemp /tmp/udev.rules.XXXXXX)"

# Download laatste release .rules bestand
DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/latest/download/99-usb-serial-aliases.rules"
if curl -fsSL "$DOWNLOAD_URL" -o "$TMP_RULE"; then
  echo "✅ Udev rules gedownload"
else
  echo "❌ Kon udev rules niet downloaden van $DOWNLOAD_URL"
  echo "   Gebruik ./create_mapping.sh en gen_udev-rules.py om handmatig te genereren"
  rm -f "$TMP_RULE"
  exit 1
fi

echo "📝 Schrijf naar $UDEV_RULE…"
sudo mv "$TMP_RULE" "$UDEV_RULE"
sudo chown root:root "$UDEV_RULE"
sudo chmod 0644 "$UDEV_RULE"

echo "🔁 Udev reload + trigger…"
sudo udevadm control --reload
sudo udevadm trigger

# ---- 5) Crontab entry voor webserver ----
WEBSERVER_SCRIPT="$SCRIPT_DIR/webserver.py"

# Gebruik conda uit condabin voor crontab
CONDA_BIN="$CONDA_DIR/condabin/conda"

# Verwijder oude startup.py entries als die er zijn
if crontab -l 2>/dev/null | grep -qF "startup.py"; then
  echo "🗑️  Verwijder oude startup.py entry uit crontab…"
  crontab -l 2>/dev/null | grep -vF "startup.py" | crontab -
fi

if [[ -f "$WEBSERVER_SCRIPT" ]]; then
  echo "🔧 Configureer crontab voor webserver.py (FastAPI met uvicorn)…"
  
  chmod +x "$WEBSERVER_SCRIPT"
  
  # Use uvicorn to run FastAPI app
  WEBSERVER_CRON="@reboot $CONDA_BIN run -n $CONDA_ENV uvicorn webserver:app --host 0.0.0.0 --port 5000 >> $HOME/webserver.log 2>&1"
  
  # Verwijder bestaande webserver.py entries en voeg nieuwe toe
  if crontab -l 2>/dev/null | grep -qF "webserver"; then
    echo "🗑️  Verwijder oude webserver entry uit crontab…"
    (crontab -l 2>/dev/null | grep -vF "webserver" || true; echo "$WEBSERVER_CRON") | crontab -
  else
    (crontab -l 2>/dev/null || true; echo "$WEBSERVER_CRON") | crontab -
  fi
  
  echo "✅ Crontab entry toegevoegd: FastAPI webserver draait bij reboot (uvicorn)"
  echo "   Log: $HOME/webserver.log"
  echo "   Web interface: http://localhost:5000"
else
  echo "⚠️  webserver.py niet gevonden, crontab entry overgeslagen"
fi

echo ""
echo "✅ Installatie compleet!"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📋 Geïnstalleerde componenten:"
echo "   • Miniconda met conda env 'lerobot'"
echo "   • lerobot package met feetech support"
echo "   • FastAPI webserver met uvicorn (auto-start bij reboot)"
echo "   • Camera streaming met OpenCV (multi-camera support)"
echo "   • Network management (AP/WiFi switching)"
echo "   • WebSocket real-time updates"
echo "   • Udev rules voor USB devices"
echo "   • Calibration files"
echo ""
echo "🚀 Bij reboot (AUTOMATISCH):"
echo "   1. Webserver start (na 5 sec)"
echo "   2. Devices worden gedetecteerd"
echo "   3. Camera's worden geïnitialiseerd"
echo "   4. Teleoperation start automatisch!"
echo "   5. Web interface: http://localhost:5000"
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
