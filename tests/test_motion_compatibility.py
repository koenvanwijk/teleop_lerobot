from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from motion_compatibility import (
    MotionCompatibilityError,
    MotionCompatibilityRegistry,
    MotionSimulationState,
    resolve_motion,
    validate_profile,
)


SO101_VALUES = {
    "shoulder_pan": 45.0,
    "shoulder_lift": -20.0,
    "elbow_flex": 10.0,
    "wrist_flex": 5.0,
    "wrist_roll": 30.0,
    "gripper": 0.0,
}

QUEST_VALUES = {
    "left_stick_x": 0.5,
    "left_stick_y": -0.25,
    "right_stick_y": 0.0,
    "left_trigger": 0.5,
    "right_stick_x": 0.25,
    "right_trigger": 0.5,
}


class MotionCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = MotionCompatibilityRegistry(ROOT / "motion_profiles")

    def test_reference_profiles_load_and_validate_digests(self) -> None:
        profiles = {item["compatibility_id"] for item in self.registry.list()}
        self.assertEqual(
            profiles,
            {
                "MC-SO101-LEADER-SO101-FOLLOWER-V1",
                "MC-SO101-LEADER-URDF-SIM-V1",
                "MC-QUEST-CONTROLLER-SO101-FOLLOWER-V1",
            },
        )

    def test_so101_leader_resolves_through_canonical_radians(self) -> None:
        resolved = self.registry.resolve(
            "MC-SO101-LEADER-SO101-FOLLOWER-V1",
            SO101_VALUES,
        )
        self.assertAlmostEqual(
            resolved["canonical_command"]["shoulder_pan"],
            math.pi / 4,
            places=10,
        )
        self.assertAlmostEqual(
            resolved["target_native_command"]["shoulder_pan"],
            45.0,
            places=10,
        )
        self.assertEqual(
            resolved["units"]["shoulder_pan"],
            {"source": "deg", "canonical": "rad", "target": "deg"},
        )

    def test_same_source_can_drive_urdf_simulation_with_different_target_units(self) -> None:
        resolved = self.registry.resolve(
            "MC-SO101-LEADER-URDF-SIM-V1",
            SO101_VALUES,
        )
        self.assertEqual(
            resolved["units"]["shoulder_pan"],
            {"source": "deg", "canonical": "rad", "target": "rad"},
        )
        self.assertAlmostEqual(
            resolved["target_native_command"]["Rotation"],
            3.14 + math.pi / 4,
            places=8,
        )

    def test_quest_controller_axes_can_map_to_so101_via_same_contract(self) -> None:
        resolved = self.registry.resolve(
            "MC-QUEST-CONTROLLER-SO101-FOLLOWER-V1",
            QUEST_VALUES,
        )
        self.assertAlmostEqual(
            resolved["target_native_command"]["shoulder_pan"],
            55.0,
            places=8,
        )
        self.assertAlmostEqual(
            resolved["target_native_command"]["wrist_flex"],
            0.0,
            places=8,
        )
        self.assertAlmostEqual(
            resolved["target_native_command"]["gripper"],
            0.0,
            places=8,
        )
        self.assertEqual(resolved["semantics"], "NORMALIZED_ABSOLUTE")

    def test_missing_source_dof_fails_closed(self) -> None:
        values = dict(SO101_VALUES)
        values.pop("elbow_flex")
        with self.assertRaisesRegex(MotionCompatibilityError, "missing source DOF elbow_flex"):
            self.registry.resolve("MC-SO101-LEADER-SO101-FOLLOWER-V1", values)

    def test_out_of_range_value_is_rejected_not_clipped(self) -> None:
        values = dict(SO101_VALUES)
        values["shoulder_pan"] = 111.0
        with self.assertRaisesRegex(MotionCompatibilityError, "outside declared source range"):
            self.registry.resolve("MC-SO101-LEADER-SO101-FOLLOWER-V1", values)

    def test_mapping_tamper_invalidates_digest(self) -> None:
        profile = self.registry.get("MC-SO101-LEADER-SO101-FOLLOWER-V1")
        tampered = copy.deepcopy(profile)
        tampered["mapping"]["dof_mappings"][0]["source_to_canonical"]["scale"] *= 2
        with self.assertRaisesRegex(MotionCompatibilityError, "mapping digest mismatch"):
            validate_profile(tampered)

    def test_simulation_target_retains_compatibility_evidence(self) -> None:
        state = MotionSimulationState()
        resolved = self.registry.resolve(
            "MC-SO101-LEADER-URDF-SIM-V1",
            SO101_VALUES,
        )
        first = state.apply(resolved)
        second = state.apply(resolved)
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(second["compatibility_id"], "MC-SO101-LEADER-URDF-SIM-V1")
        self.assertIn("shoulder_pan", second["canonical_command"])
        self.assertIn("Rotation", second["target_native_command"])


if __name__ == "__main__":
    unittest.main()
