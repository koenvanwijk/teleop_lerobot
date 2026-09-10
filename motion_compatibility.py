#!/usr/bin/env python3
"""EPAOA-style motion compatibility for Teleopworks/LeRobot.

The boundary is deliberately transport-independent:

    source-native -> canonical Robot Control -> target-native

A source and target may use different units, ranges and names.  Every
conversion is explicit, versioned and fail-closed.  This module has no LeRobot
or FastAPI dependency so it can also be used by simulations and conformance
tests.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Dict, Mapping


class MotionCompatibilityError(ValueError):
    """Raised when a motion source/mapping/target tuple is not admissible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MotionCompatibilityError(message)


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MotionCompatibilityError(f"{label} must be numeric") from exc
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _range(entry: Mapping[str, Any], name: str) -> tuple[float, float]:
    spec = entry.get(name)
    _require(isinstance(spec, Mapping), f"{name} missing")
    low = _finite(spec.get("minimum"), f"{name}.minimum")
    high = _finite(spec.get("maximum"), f"{name}.maximum")
    _require(low < high, f"{name} minimum must be smaller than maximum")
    return low, high


def _affine(value: float, transform: Mapping[str, Any], label: str) -> float:
    scale = _finite(transform.get("scale"), f"{label}.scale")
    offset = _finite(transform.get("offset", 0.0), f"{label}.offset")
    result = value * scale + offset
    _require(math.isfinite(result), f"{label} produced non-finite value")
    return result


def profile_digest(profile: Mapping[str, Any]) -> str:
    encoded = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def mapping_digest(mapping: Mapping[str, Any]) -> str:
    material = {key: value for key, value in mapping.items() if key != "digest"}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Validate the executable subset of the EPAOA Motion Compatibility Profile."""

    required = (
        "compatibility_id", "version", "lifecycle_status", "compatibility_decision",
        "reason_codes", "source", "mapping", "target", "constraints",
        "validation", "evidence_refs", "valid_from", "invalidation_triggers",
    )
    for key in required:
        _require(key in profile, f"profile missing {key}")

    _require(profile["lifecycle_status"] == "approved", "profile is not approved")
    _require(
        profile["compatibility_decision"] in {"compatible", "conditionally_compatible"},
        "profile is not compatible",
    )

    source = profile["source"]
    mapping = profile["mapping"]
    target = profile["target"]
    _require(isinstance(source, Mapping), "source must be an object")
    _require(isinstance(mapping, Mapping), "mapping must be an object")
    _require(isinstance(target, Mapping), "target must be an object")

    for field in ("mapping_id", "version", "digest", "canonical_action_schema_id", "canonical_frame"):
        _require(mapping.get(field), f"mapping missing {field}")
    _require(mapping_digest(mapping) == mapping["digest"], "mapping digest mismatch")
    _require(mapping.get("command_space") in {"JOINT", "CARTESIAN", "TOOL", "MOBILE_BASE", "HYBRID", "DISCRETE"}, "invalid command space")
    _require(mapping.get("control_mode") in {"POSITION", "VELOCITY", "ACCELERATION", "EFFORT", "IMPEDANCE", "COMPLIANCE", "TRAJECTORY", "WAYPOINT", "SERVO", "DISCRETE_ACTION"}, "invalid control mode")

    for field in ("endpoint_id", "role", "capability_profile_ref", "calibration_ref", "input_schema_id", "frame"):
        _require(source.get(field), f"source missing {field}")
    for field in ("endpoint_id", "role", "capability_profile_ref", "calibration_ref", "accepted_action_schema_id", "adapter_mapping_ref", "frame"):
        _require(target.get(field), f"target missing {field}")
    _require(
        target["accepted_action_schema_id"] == mapping["canonical_action_schema_id"],
        "target does not accept the canonical action schema",
    )

    constraints = profile["constraints"]
    _require(constraints.get("missing_dof_behavior") == "reject", "reference runtime only supports fail-closed missing DOFs")
    _require(constraints.get("out_of_range_behavior") == "reject", "reference runtime only supports fail-closed range handling")
    _require(constraints.get("stale_calibration_behavior") == "reject", "reference runtime requires stale calibration rejection")
    if profile["compatibility_decision"] == "conditionally_compatible":
        _require(bool(profile.get("conditions")), "conditional compatibility requires conditions")

    dofs = mapping.get("dof_mappings")
    _require(isinstance(dofs, list) and dofs, "dof_mappings must not be empty")

    source_names: set[str] = set()
    canonical_names: set[str] = set()
    target_names: set[str] = set()
    for item in dofs:
        _require(isinstance(item, Mapping), "DOF mapping must be an object")
        for field in ("source_dof", "canonical_dof", "target_dof", "source_unit", "canonical_unit", "target_unit", "source_to_canonical", "target_from_canonical"):
            _require(item.get(field) is not None, f"DOF mapping missing {field}")
        source_min, source_max = _range(item, "source_range")
        target_min, target_max = _range(item, "target_range")
        for endpoint_value in (source_min, source_max):
            canonical_value = _affine(
                endpoint_value,
                item["source_to_canonical"],
                f"{item['source_dof']}.source_to_canonical",
            )
            target_value = _affine(
                canonical_value,
                item["target_from_canonical"],
                f"{item['source_dof']}.target_from_canonical",
            )
            _require(
                target_min <= target_value <= target_max,
                f"declared mapping exceeds target range for {item['target_dof']}",
            )
        _require(item["source_dof"] not in source_names, f"duplicate source DOF {item['source_dof']}")
        _require(item["canonical_dof"] not in canonical_names, f"duplicate canonical DOF {item['canonical_dof']}")
        _require(item["target_dof"] not in target_names, f"duplicate target DOF {item['target_dof']}")
        source_names.add(item["source_dof"])
        canonical_names.add(item["canonical_dof"])
        target_names.add(item["target_dof"])

    required_target = set(target.get("required_dofs") or [])
    _require(required_target <= target_names, "required target DOF is not mapped")


def resolve_motion(profile: Mapping[str, Any], source_values: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve source-native values into canonical and target-native values.

    No clipping is performed.  A value outside either declared operating range
    is rejected because silent clipping changes command semantics.
    """

    validate_profile(profile)
    mapping = profile["mapping"]

    canonical: Dict[str, float] = {}
    target_native: Dict[str, float] = {}
    units: Dict[str, Dict[str, str]] = {}

    for item in mapping["dof_mappings"]:
        source_name = item["source_dof"]
        _require(source_name in source_values, f"missing source DOF {source_name}")
        source_value = _finite(source_values[source_name], source_name)
        source_min, source_max = _range(item, "source_range")
        _require(source_min <= source_value <= source_max, f"{source_name} outside declared source range")

        canonical_value = _affine(source_value, item["source_to_canonical"], f"{source_name}.source_to_canonical")
        target_value = _affine(canonical_value, item["target_from_canonical"], f"{source_name}.target_from_canonical")

        target_min, target_max = _range(item, "target_range")
        _require(target_min <= target_value <= target_max, f"{item['target_dof']} outside declared target range")

        canonical[item["canonical_dof"]] = canonical_value
        target_native[item["target_dof"]] = target_value
        units[item["canonical_dof"]] = {
            "source": item["source_unit"],
            "canonical": item["canonical_unit"],
            "target": item["target_unit"],
        }

    return {
        "compatibility_id": profile["compatibility_id"],
        "profile_version": profile["version"],
        "profile_digest": profile_digest(profile),
        "mapping_id": mapping["mapping_id"],
        "mapping_version": mapping["version"],
        "canonical_action_schema_id": mapping["canonical_action_schema_id"],
        "command_space": mapping["command_space"],
        "control_mode": mapping["control_mode"],
        "semantics": mapping.get("semantics", "ABSOLUTE"),
        "canonical_frame": mapping.get("canonical_frame"),
        "canonical_command": canonical,
        "target_native_command": target_native,
        "units": units,
        "source": dict(profile["source"]),
        "target": dict(profile["target"]),
    }


class MotionCompatibilityRegistry:
    """Loads immutable JSON profiles from a directory."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        profiles: Dict[str, Dict[str, Any]] = {}
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.json")):
                profile = json.loads(path.read_text(encoding="utf-8"))
                validate_profile(profile)
                profile_id = str(profile["compatibility_id"])
                _require(profile_id not in profiles, f"duplicate compatibility_id {profile_id}")
                profile["_source_file"] = path.name
                profiles[profile_id] = profile
        self._profiles = profiles

    def get(self, profile_id: str) -> Dict[str, Any]:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise MotionCompatibilityError(f"unknown motion compatibility profile {profile_id}")
        return {k: v for k, v in profile.items() if not k.startswith("_")}

    def list(self) -> list[Dict[str, Any]]:
        result = []
        for profile_id, raw in sorted(self._profiles.items()):
            profile = {k: v for k, v in raw.items() if not k.startswith("_")}
            result.append({
                "compatibility_id": profile_id,
                "version": profile["version"],
                "source_role": profile["source"].get("role"),
                "target_role": profile["target"].get("role"),
                "target_adapter_mapping_ref": profile["target"].get("adapter_mapping_ref"),
                "command_space": profile["mapping"].get("command_space"),
                "control_mode": profile["mapping"].get("control_mode"),
                "validation": profile.get("validation", {}),
                "profile_digest": profile_digest(profile),
                "source_file": raw.get("_source_file"),
            })
        return result

    def resolve(self, profile_id: str, source_values: Mapping[str, Any]) -> Dict[str, Any]:
        return resolve_motion(self.get(profile_id), source_values)


class MotionSimulationState:
    """Thread-safe target state for the browser/URDF reference simulation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "updated_at": None,
            "sequence": 0,
            "compatibility_id": None,
            "canonical_command": {},
            "target_native_command": {},
        }

    def apply(self, resolved: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._state = {
                "updated_at": time.time(),
                "sequence": int(self._state["sequence"]) + 1,
                "compatibility_id": resolved["compatibility_id"],
                "profile_digest": resolved["profile_digest"],
                "canonical_action_schema_id": resolved["canonical_action_schema_id"],
                "canonical_command": dict(resolved["canonical_command"]),
                "target_native_command": dict(resolved["target_native_command"]),
                "units": dict(resolved["units"]),
            }
            return dict(self._state)

    def get(self) -> Dict[str, Any]:
        with self._lock:
            result = dict(self._state)
            result["canonical_command"] = dict(self._state["canonical_command"])
            result["target_native_command"] = dict(self._state["target_native_command"])
            return result
