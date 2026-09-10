from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from motion_compatibility import MotionCompatibilityRegistry
from reachy_mini_target import ReachyMiniTargetError, build_reachy_target


class ReachyMiniTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = MotionCompatibilityRegistry(ROOT / "motion_profiles")

    def test_so101_normalized_midpoint_maps_to_neutral_reachy_target(self) -> None:
        resolved = self.registry.resolve(
            "MC-SO101-LEADER-REACHY-MINI-V1",
            {
                "shoulder_pan": 0.0,
                "shoulder_lift": 0.0,
                "elbow_flex": 0.0,
                "wrist_flex": 0.0,
                "wrist_roll": 0.0,
                "gripper": 50.0,
            },
        )

        target = resolved["target_native_command"]
        self.assertAlmostEqual(target["head_yaw"], 0.0)
        self.assertAlmostEqual(target["head_pitch"], 0.0)
        self.assertAlmostEqual(target["head_roll"], 0.0)
        self.assertAlmostEqual(target["head_z"], 0.0)
        self.assertAlmostEqual(target["right_antenna"], 0.0)
        self.assertAlmostEqual(target["left_antenna"], 0.0)

        payload = build_reachy_target(target)
        self.assertEqual(payload["head"]["x_m"], 0.0)
        self.assertEqual(payload["head"]["y_m"], 0.0)
        self.assertAlmostEqual(payload["antennas_rad"][0], 0.0, places=12)
        self.assertAlmostEqual(payload["antennas_rad"][1], 0.0, places=12)

    def test_full_scale_mapping_stays_inside_declared_reachy_limits(self) -> None:
        resolved = self.registry.resolve(
            "MC-SO101-LEADER-REACHY-MINI-V1",
            {
                "shoulder_pan": 100.0,
                "shoulder_lift": 100.0,
                "elbow_flex": 100.0,
                "wrist_flex": 100.0,
                "wrist_roll": 100.0,
                "gripper": 100.0,
            },
        )
        target = resolved["target_native_command"]

        self.assertAlmostEqual(target["head_yaw"], math.radians(60.0))
        self.assertAlmostEqual(target["head_pitch"], math.radians(35.0))
        self.assertAlmostEqual(target["head_roll"], math.radians(30.0))
        self.assertAlmostEqual(target["head_z"], 0.02)
        self.assertAlmostEqual(target["right_antenna"], math.radians(45.0))
        self.assertAlmostEqual(target["left_antenna"], math.radians(45.0))

    def test_reachy_sdk_antenna_order_is_right_then_left(self) -> None:
        payload = build_reachy_target(
            {
                "head_yaw": 0.1,
                "head_pitch": 0.2,
                "head_roll": 0.3,
                "head_z": 0.01,
                "right_antenna": 0.4,
                "left_antenna": -0.5,
            }
        )
        self.assertEqual(payload["antennas_rad"], [0.4, -0.5])

    def test_missing_target_field_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ReachyMiniTargetError,
            "missing Reachy Mini target fields: head_z",
        ):
            build_reachy_target(
                {
                    "head_yaw": 0.0,
                    "head_pitch": 0.0,
                    "head_roll": 0.0,
                    "right_antenna": 0.0,
                    "left_antenna": 0.0,
                }
            )


if __name__ == "__main__":
    unittest.main()
