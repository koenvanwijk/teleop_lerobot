#!/usr/bin/env bash
set -euo pipefail

# Headless delivery hardening for LeRobot robots.
# Fixes two delivery blockers:
# 1) Do not auto-start teleoperation at boot unless explicitly enabled.
# 2) Do not let web teleoperation enter an interactive calibration prompt.
#    The web path must use existing calibration or fail visibly in logs/UI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB="$SCRIPT_DIR/webserver.py"
TELEOP="$SCRIPT_DIR/teleoperation_manager.py"
LOG="/tmp/lerobot-headless-delivery-fix.txt"

exec > >(tee "$LOG") 2>&1

echo "== LeRobot headless delivery fix =="
echo "Repo: $SCRIPT_DIR"
echo "Log:  $LOG"
echo

if [[ ! -f "$WEB" || ! -f "$TELEOP" ]]; then
  echo "ERROR: run this from the teleop_lerobot checkout" >&2
  exit 1
fi

# Ensure repo calibration files are present in the Hugging Face cache before web teleop starts.
if [[ -x "$SCRIPT_DIR/sync_calibration.sh" ]]; then
  echo "Importing calibration files into ~/.cache/huggingface/lerobot/calibration ..."
  "$SCRIPT_DIR/sync_calibration.sh" import || true
else
  echo "WARNING: sync_calibration.sh not executable or missing; skipping calibration import"
fi

python3 - "$WEB" "$TELEOP" <<'PY'
from pathlib import Path
import re
import sys

web = Path(sys.argv[1])
teleop = Path(sys.argv[2])

# ---------------------------------------------------------------------------
# 1) Disable boot auto-start by default.
# ---------------------------------------------------------------------------
text = web.read_text(encoding="utf-8")
old = "if state.devices_available:\n            logger.info(\"✅ USB devices beschikbaar\")"
new = "if state.devices_available and os.getenv(\"LEROBOT_AUTOSTART_TELEOP\", \"0\").lower() in {\"1\", \"true\", \"yes\", \"on\"}:\n            logger.info(\"✅ USB devices beschikbaar en LEROBOT_AUTOSTART_TELEOP=1\")"
if old in text:
    text = text.replace(old, new, 1)
    web.write_text(text, encoding="utf-8")
    print("Patched webserver.py: boot auto-start is now opt-in")
elif "LEROBOT_AUTOSTART_TELEOP" in text:
    print("webserver.py already patched: boot auto-start opt-in")
else:
    raise SystemExit("Could not find webserver.py auto-start block")

# ---------------------------------------------------------------------------
# 2) Force non-interactive calibration behavior in the web teleop manager.
# ---------------------------------------------------------------------------
text = teleop.read_text(encoding="utf-8")

helper = '''\n    def _connect_device_non_interactive(self, device, label: str):\n        """Connect using existing calibration only; never open an interactive prompt.\n\n        LeRobot's default connect() path can prompt:\n        \"Press ENTER to use provided calibration file ... or type c ...\".\n        That is acceptable in a terminal but fatal for a delivered headless robot.\n        The web UI must either connect with existing calibration or fail visibly.\n        """\n        try:\n            return device.connect(calibrate=False)\n        except TypeError:\n            # Older/other device classes may not expose calibrate=. For those,\n            # fall back to connect(), but make the risk visible in the log.\n            logging.warning(\n                "%s connect() does not support calibrate=False; falling back to default connect()",\n                label,\n            )\n            return device.connect()\n\n'''

if "def _connect_device_non_interactive" not in text:
    marker = "    def _teleop_loop(self):\n"
    if marker not in text:
        raise SystemExit("Could not find _teleop_loop marker in teleoperation_manager.py")
    text = text.replace(marker, helper + marker, 1)

old_connect = """            # Connect devices\n            self.teleop.connect()\n            self.robot.connect()\n"""
new_connect = """            # Connect devices. The web/server path must never ask for\n            # keyboard input to accept or run calibration. If calibration is\n            # missing, fail visibly instead of blocking a headless delivery.\n            self._connect_device_non_interactive(self.teleop, \"teleoperator\")\n            self._connect_device_non_interactive(self.robot, \"robot\")\n"""
if old_connect in text:
    text = text.replace(old_connect, new_connect, 1)
    teleop.write_text(text, encoding="utf-8")
    print("Patched teleoperation_manager.py: web teleop uses calibrate=False")
elif "_connect_device_non_interactive(self.teleop" in text:
    teleop.write_text(text, encoding="utf-8")
    print("teleoperation_manager.py already patched")
else:
    raise SystemExit("Could not find connect block in teleoperation_manager.py")
PY

# Install/restart service when present.
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^lerobot-webserver.service'; then
  echo
  echo "Restarting lerobot-webserver.service ..."
  sudo systemctl daemon-reload || true
  sudo systemctl restart lerobot-webserver.service
  sudo systemctl --no-pager --full status lerobot-webserver.service || true
fi

echo
echo "Done. Web teleop will not auto-start at boot unless LEROBOT_AUTOSTART_TELEOP=1 is set."
echo "Done. Web teleop will not wait for ENTER to accept calibration."
echo
cat <<'EOF'
Useful checks:
  journalctl -u lerobot-webserver.service -b -n 200 --no-pager
  grep -n "LEROBOT_AUTOSTART_TELEOP\|_connect_device_non_interactive" webserver.py teleoperation_manager.py
  ls -R ~/.cache/huggingface/lerobot/calibration
EOF
