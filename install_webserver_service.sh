#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_DIR="${CONDA_DIR:-$HOME/miniconda3}"
CONDA_ENV="${CONDA_ENV:-lerobot}"
CONDA_BIN="$CONDA_DIR/condabin/conda"
WEBSERVER_SCRIPT="$SCRIPT_DIR/webserver.py"
SERVICE_FILE="/etc/systemd/system/lerobot-webserver.service"

if [[ ! -x "$CONDA_BIN" ]]; then
  echo "❌ conda not found at $CONDA_BIN"
  exit 1
fi
if [[ ! -f "$WEBSERVER_SCRIPT" ]]; then
  echo "❌ webserver.py not found at $WEBSERVER_SCRIPT"
  exit 1
fi

# Web SSH uses the host's normal sshd authentication.
if command -v apt-get >/dev/null 2>&1; then
  if ! command -v ssh >/dev/null 2>&1 || ! command -v sshd >/dev/null 2>&1; then
    echo "💻 Installing OpenSSH client/server for /ssh ..."
    sudo apt-get update -y
    sudo apt-get install -y openssh-client openssh-server
  fi
  sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd 2>/dev/null || true
fi

# Remove legacy cron startup to avoid duplicate servers.
if crontab -l 2>/dev/null | grep -qF "webserver"; then
  (crontab -l 2>/dev/null | grep -vF "webserver" || true) | crontab -
fi

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
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

echo "✅ lerobot-webserver.service installed and restarted"
echo "   Web UI: http://<robot-ip>:5000/"
echo "   SSH UI: http://<robot-ip>:5000/ssh"
echo "   Status: sudo systemctl status lerobot-webserver.service"
echo "   Logs:   journalctl -u lerobot-webserver.service -f"
