#!/usr/bin/env python3
"""
LeRobot CLI wrapper that exposes SO-100/SO-101 motor positions in degrees.

LeRobot 0.6.1 uses degrees for the five arm joints when use_degrees=True,
but its SO gripper is still configured with a normalized range. This wrapper
switches that gripper motor to MotorNormMode.DEGREES before hardware connect,
so teleoperation, recording, replay and rollout all use one unit: degrees.

Examples:
    python lerobot_degrees.py teleoperate --robot.type=so101_follower ...
    python lerobot_degrees.py record --robot.type=so101_follower ...
    python lerobot_degrees.py replay --robot.type=so101_follower ...
    python lerobot_degrees.py rollout --robot.type=so101_follower ...
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from lerobot.motors import MotorNormMode


def _patch_gripper_to_degrees(cls: type) -> None:
    """Patch one LeRobot SO class so its gripper uses degree normalization."""
    if getattr(cls, "_teleop_lerobot_all_degrees", False):
        return

    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        bus = getattr(self, "bus", None)
        if bus is not None and "gripper" in bus.motors:
            bus.motors["gripper"].norm_mode = MotorNormMode.DEGREES

    cls.__init__ = patched_init
    cls._teleop_lerobot_all_degrees = True


def enable_all_degrees() -> None:
    """Apply the SO follower/leader gripper degree override."""
    from lerobot.robots.so_follower import SOFollower
    from lerobot.teleoperators.so_leader import SOLeader

    _patch_gripper_to_degrees(SOFollower)
    _patch_gripper_to_degrees(SOLeader)


def _ensure_degree_flags(argv: list[str]) -> None:
    """Default SO robot/teleoperator configs to native degree mode."""
    has_so_robot = any(
        arg.startswith("--robot.type=") and arg.split("=", 1)[1] in {"so100_follower", "so101_follower"}
        for arg in argv
    )
    has_so_teleop = any(
        arg.startswith("--teleop.type=") and arg.split("=", 1)[1] in {"so100_leader", "so101_leader"}
        for arg in argv
    )

    if has_so_robot and not any(arg.startswith("--robot.use_degrees=") for arg in argv):
        argv.append("--robot.use_degrees=true")
    if has_so_teleop and not any(arg.startswith("--teleop.use_degrees=") for arg in argv):
        argv.append("--teleop.use_degrees=true")


def _command_main(command: str) -> Callable[[], None]:
    if command == "teleoperate":
        from lerobot.scripts.lerobot_teleoperate import main
    elif command == "record":
        from lerobot.scripts.lerobot_record import main
    elif command == "replay":
        from lerobot.scripts.lerobot_replay import main
    elif command == "rollout":
        from lerobot.scripts.lerobot_rollout import main
    else:
        raise SystemExit(
            "Usage: lerobot_degrees.py {teleoperate|record|replay|rollout} [LeRobot arguments...]"
        )
    return main


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: lerobot_degrees.py {teleoperate|record|replay|rollout} [LeRobot arguments...]"
        )

    command = sys.argv.pop(1)
    enable_all_degrees()
    _ensure_degree_flags(sys.argv)
    _command_main(command)()


if __name__ == "__main__":
    main()
