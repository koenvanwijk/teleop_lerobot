#!/usr/bin/env python3
"""
Startup script voor LeRobot op Raspberry Pi.
Dit script wordt automatisch uitgevoerd bij reboot via crontab.
"""

import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path


def log(message: str) -> None:
    """Print bericht met timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def check_devices() -> bool:
    """
    Controleer of USB serial devices beschikbaar zijn.
    Returns: True als devices gevonden zijn.
    """
    dev_dir = Path("/dev")
    
    # Zoek naar tty_* symlinks
    tty_devices = list(dev_dir.glob("tty_*"))
    
    if tty_devices:
        log(f"✅ Gevonden {len(tty_devices)} USB serial device(s):")
        for dev in sorted(tty_devices):
            log(f"   - {dev.name}")
        return True
    else:
        log("⚠️  Geen USB serial devices gevonden")
        return False


def initialize_lerobot() -> None:
    """
    Initialiseer LeRobot systeem.
    Voeg hier je specifieke initialisatie code toe.
    """
    log("🤖 Initialiseer LeRobot systeem...")
    
    # Check of lerobot package beschikbaar is
    try:
        import lerobot
        log(f"✅ LeRobot package geladen (versie: {lerobot.__version__ if hasattr(lerobot, '__version__') else 'unknown'})")
    except ImportError as e:
        log(f"❌ LeRobot package niet gevonden: {e}")
        return
    
    log("✅ LeRobot systeem geïnitialiseerd")


def start_teleoperation() -> None:
    """
    Start LeRobot teleoperation in de achtergrond.
    """
    log("🎮 Start teleoperation...")
    
    dev_dir = Path("/dev")
    
    # Zoek follower device met symbolic link
    follower_links = list(dev_dir.glob("tty_*_follower"))
    if not follower_links:
        log("⚠️  Geen follower device gevonden (tty_*_follower)")
        return
    
    # Gebruik eerste follower link
    follower_link = follower_links[0]
    # Extraheer robot ID uit symbolic link naam (bijv. tty_white_follower -> white)
    follower_id = follower_link.name.replace("tty_", "").replace("_follower", "")
    follower_port = follower_link.resolve()
    
    # Zoek leader device met symbolic link
    leader_links = list(dev_dir.glob("tty_*_leader"))
    if not leader_links:
        log("⚠️  Geen leader device gevonden (tty_*_leader)")
        return
    
    # Gebruik eerste leader link
    leader_link = leader_links[0]
    # Extraheer teleop ID uit symbolic link naam (bijv. tty_black_leader -> black)
    leader_id = leader_link.name.replace("tty_", "").replace("_leader", "")
    leader_port = leader_link.resolve()
    
    # Teleoperation commando
    cmd = [
        "python", "-m", "lerobot.teleoperate",
        "--robot.type=so101_follower",
        f"--robot.port={follower_port}",
        f"--robot.id={follower_id}",
        "--teleop.type=so101_leader",
        f"--teleop.port={leader_port}",
        f"--teleop.id={leader_id}"
    ]
    
    try:
        log(f"   Command: {' '.join(cmd)}")
        # Start als achtergrond proces
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        log(f"✅ Teleoperation gestart (PID: {process.pid})")
        log(f"   Follower: {follower_link.name} -> {follower_port} (ID: {follower_id})")
        log(f"   Leader: {leader_link.name} -> {leader_port} (ID: {leader_id})")
        
    except Exception as e:
        log(f"❌ Fout bij starten teleoperation: {e}")
        import traceback
        traceback.print_exc()


def main() -> None:
    """Main startup functie."""
    log("=" * 60)
    log("🚀 LeRobot Startup Script")
    log("=" * 60)
    
    # Wacht even tot systeem volledig opgestart is
    log("⏳ Wacht 10 seconden voor systeem initialisatie...")
    time.sleep(10)
    
    # Check USB devices
    devices_found = check_devices()
    
    if not devices_found:
        log("⚠️  Start zonder USB devices")
    
    # Initialiseer LeRobot
    try:
        initialize_lerobot()
    except Exception as e:
        log(f"❌ Fout tijdens initialisatie: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Start teleoperation
    if devices_found:
        try:
            start_teleoperation()
        except Exception as e:
            log(f"❌ Fout bij starten teleoperation: {e}")
            import traceback
            traceback.print_exc()
    else:
        log("⚠️  Skip teleoperation (geen devices)")
    
    log("=" * 60)
    log("✅ Startup compleet")
    log("=" * 60)


if __name__ == "__main__":
    main()
