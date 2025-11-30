#!/usr/bin/env bash
set -euo pipefail

# ========= Config =========
CONDA_DIR="$HOME/miniconda3"
CONDA_ENV="lerobot"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh"
UDEV_RULE="/etc/udev/rules.d/99-usb-serial-aliases.rules"
GITHUB_REPO="koenvanwijk/pi_lerobot"
# ==========================

usage() {
  cat <<'EOF'
Gebruik: ./install.sh

Installeert:
- Miniconda met Python 3.10
- lerobot package met feetech support
- Udev rules (gedownload van laatste GitHub release)

Symlinks:
  /dev/tty_<nice>_<role>   (bv. /dev/tty_black_leader)
  /dev/tty_follower        (voor elke follower)
  /dev/tty_leader          (voor elke leader)
EOF
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }

ARCH="$(uname -m)"
[[ "$ARCH" == "aarch64" ]] || { echo "❌ Verwacht aarch64 (64-bit). Gevonden: $ARCH"; exit 1; }

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
fi

# Conda in deze shell
# shellcheck disable=SC1091
source "$CONDA_DIR/etc/profile.d/conda.sh"

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

echo "📦 pip install lerobot…"
conda activate "$CONDA_ENV"
pip install --upgrade pip
pip install lerobot[feetech]

# ---- 3) Udev rules downloaden ----
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

# ---- 4) Crontab entry voor startup.py ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STARTUP_SCRIPT="$SCRIPT_DIR/startup.py"

if [[ -f "$STARTUP_SCRIPT" ]]; then
  echo "🔧 Configureer crontab voor startup.py…"
  
  # Maak startup.py executable
  chmod +x "$STARTUP_SCRIPT"
  
  # Gebruik conda uit condabin voor crontab
  CONDA_BIN="$CONDA_DIR/condabin/conda"
  
  # Crontab entry met conda run
  CRON_ENTRY="@reboot $CONDA_BIN run -n $CONDA_ENV python $STARTUP_SCRIPT >> $HOME/startup.log 2>&1"
  
  # Check of de entry al bestaat
  if crontab -l 2>/dev/null | grep -qF "$STARTUP_SCRIPT"; then
    echo "✅ Crontab entry bestaat al voor startup.py"
  else
    # Voeg toe aan crontab
    (crontab -l 2>/dev/null || true; echo "$CRON_ENTRY") | crontab -
    echo "✅ Crontab entry toegevoegd: startup.py draait bij reboot"
    echo "   Log: $HOME/startup.log"
  fi
else
  echo "⚠️  startup.py niet gevonden, crontab entry overgeslagen"
fi

echo "✅ Installatie compleet!"
