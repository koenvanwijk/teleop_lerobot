#!/usr/bin/env python3
"""
LeRobot Teleoperation Script
Gebruikt voor het bedienen van de robot met leader-follower configuratie.
"""

import argparse
import sys
import time
from pathlib import Path


def check_devices(required_devices: list[str]) -> bool:
    """
    Controleer of vereiste USB serial devices beschikbaar zijn.
    
    Args:
        required_devices: Lijst van device namen (bijv. ['tty_leader', 'tty_follower'])
    
    Returns:
        True als alle devices gevonden zijn.
    """
    dev_dir = Path("/dev")
    missing_devices = []
    
    for device in required_devices:
        device_path = dev_dir / device
        if not device_path.exists():
            missing_devices.append(device)
    
    if missing_devices:
        print(f"❌ Ontbrekende devices: {', '.join(missing_devices)}", file=sys.stderr)
        print(f"   Beschikbare tty_* devices:", file=sys.stderr)
        for dev in sorted(dev_dir.glob("tty_*")):
            print(f"   - {dev.name}", file=sys.stderr)
        return False
    
    print(f"✅ Alle vereiste devices gevonden: {', '.join(required_devices)}")
    return True


def start_teleoperation(repo_id: str, fps: int = 30, display_cameras: bool = True) -> None:
    """
    Start LeRobot teleoperation.
    
    Args:
        repo_id: HuggingFace repository ID voor het opslaan van data
        fps: Frames per seconde voor recording
        display_cameras: Of camera feeds getoond moeten worden
    """
    try:
        from lerobot.scripts.control_robot import control_robot
        print(f"🤖 Start teleoperation met repo: {repo_id}")
        print(f"   FPS: {fps}")
        print(f"   Display cameras: {display_cameras}")
        
        # Start teleoperation
        # TODO: Pas deze argumenten aan op basis van je specifieke setup
        control_robot(
            repo_id=repo_id,
            fps=fps,
            display_cameras=display_cameras,
        )
        
    except ImportError as e:
        print(f"❌ Kon lerobot package niet laden: {e}", file=sys.stderr)
        print("   Zorg ervoor dat lerobot[feetech] is geïnstalleerd", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fout tijdens teleoperation: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="LeRobot Teleoperation - Bedien de robot met leader-follower configuratie"
    )
    
    parser.add_argument(
        "--repo-id",
        type=str,
        required=True,
        help="HuggingFace repository ID (bijv. 'username/robot-dataset')"
    )
    
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Frames per seconde voor recording (standaard: 30)"
    )
    
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Schakel camera display uit"
    )
    
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Controleer alleen of devices beschikbaar zijn (start geen teleoperation)"
    )
    
    args = parser.parse_args()
    
    # Controleer vereiste devices
    required_devices = ["tty_leader", "tty_follower"]
    devices_ok = check_devices(required_devices)
    
    if not devices_ok:
        print("\n💡 Tips:", file=sys.stderr)
        print("   1. Controleer of USB kabels aangesloten zijn", file=sys.stderr)
        print("   2. Run 'sudo udevadm trigger' om udev rules te herladen", file=sys.stderr)
        print("   3. Controleer /dev voor beschikbare devices", file=sys.stderr)
        sys.exit(1)
    
    if args.check_only:
        print("✅ Device check compleet")
        return
    
    # Start teleoperation
    print("\n" + "=" * 60)
    print("🚀 Start LeRobot Teleoperation")
    print("=" * 60)
    
    start_teleoperation(
        repo_id=args.repo_id,
        fps=args.fps,
        display_cameras=not args.no_display
    )


if __name__ == "__main__":
    main()
