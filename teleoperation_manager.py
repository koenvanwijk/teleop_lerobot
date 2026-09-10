#!/usr/bin/env python3
"""
Teleoperation Manager - Based on LeRobot's lerobot_teleoperate.py
Adapted to run in-process with access to robot positions for web visualization

This implementation stays close to LeRobot's original code for easy updates.
"""

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License")

import hashlib
import json
import logging
import os
import time
import threading
import sys
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Optional, Dict, Any
from pprint import pformat

import draccus

from lerobot.motors import MotorNormMode

from lerobot.processor import (
    RobotAction,
    RobotObservation,
    RobotProcessorPipeline,
    make_default_processors,
)
from lerobot.robots import (
    Robot,
    RobotConfig,
    make_robot_from_config,
)
from lerobot.teleoperators import (
    Teleoperator,
    TeleoperatorConfig,
    make_teleoperator_from_config,
)
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging
from lerobot.scripts.lerobot_teleoperate import TeleoperateConfig

from motion_compatibility import (
    MotionCompatibilityRegistry,
    bind_runtime_calibration,
    profile_digest,
    resolve_motion,
)


class TeleoperationManager:
    """
    Manages teleoperation with access to robot positions.
    Based on LeRobot's teleoperate.py but runs in-process.
    """
    
    def __init__(self):
        self.teleop: Optional[Teleoperator] = None
        self.robot: Optional[Robot] = None
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.current_observation: Optional[Dict[str, Any]] = None
        self.current_action: Optional[Dict[str, Any]] = None
        self.current_canonical_action: Optional[Dict[str, float]] = None
        self.motion_registry: Optional[MotionCompatibilityRegistry] = None
        self.motion_profile_id: Optional[str] = None
        self.motion_profile: Optional[Dict[str, Any]] = None
        self.motion_profile_digest: Optional[str] = None
        self.motion_mapping_id: Optional[str] = None
        self.motion_admitted_ranges: Dict[str, Dict[str, float]] = {}
        self.lock = threading.Lock()
        self.fps = 60
        self.actual_fps = 0.0
        self.processing_ms = 0.0
        self.loop_errors = 0
        self.connection_state = "stopped"
        self.last_error: Optional[str] = None
        self.started_at: Optional[float] = None
        self._fps_window_started = time.perf_counter()
        self._fps_window_count = 0
        
        # Processors (same as LeRobot)
        self.teleop_action_processor = None
        self.robot_action_processor = None
        self.robot_observation_processor = None
        
        # Preserve the webserver's handlers (GUI ring buffer/file/stdout). When
        # this manager is used standalone, initialize LeRobot logging normally.
        if not logging.getLogger().handlers:
            init_logging()
        register_third_party_plugins()
    
    def start(self, robot_type: str, robot_port: str, robot_id: str, 
              teleop_type: str, teleop_port: str, teleop_id: str, fps: int = 60,
              motion_profile_id: Optional[str] = None):
        """
        Start teleoperation with given configuration.
        
        Args:
            robot_type: Robot type (e.g., "so101_follower")
            robot_port: Robot serial port
            robot_id: Robot ID (e.g., "white", "black")
            teleop_type: Teleoperator type (e.g., "so101_leader")
            teleop_port: Teleoperator serial port
            teleop_id: Teleoperator ID
            fps: Target frames per second
            motion_profile_id: Optional EPAOA Motion Compatibility Profile. When
                set, every source action is resolved source-native -> canonical
                -> target-native before the Robot action processor.
        """
        if self.is_running:
            logging.warning("Teleoperation already running")
            return False
        
        try:
            self.connection_state = "connecting"
            self.last_error = None
            # Use LeRobot's draccus parser to build config (same as command-line tool)
            # This ensures 100% compatibility with LeRobot's config system
            old_argv = sys.argv
            try:
                sys.argv = [
                    'teleoperate',
                    f'--robot.type={robot_type}',
                    f'--robot.port={robot_port}',
                    f'--robot.id={robot_id}',
                    '--robot.use_degrees=true',
                    f'--teleop.type={teleop_type}',
                    f'--teleop.port={teleop_port}',
                    f'--teleop.id={teleop_id}',
                    '--teleop.use_degrees=true',
                    f'--fps={fps}'
                ]
                
                # Parse using draccus (exactly how lerobot-teleoperate does it)
                cfg = draccus.parse(TeleoperateConfig)
                
            finally:
                sys.argv = old_argv
            
            logging.info(f"Robot config: {cfg.robot}")
            logging.info(f"Teleop config: {cfg.teleop}")
            
            # Create robot and teleoperator (LeRobot's factory functions)
            self.robot = make_robot_from_config(cfg.robot)
            self.teleop = make_teleoperator_from_config(cfg.teleop)

            self.motion_profile_id = motion_profile_id
            self.motion_registry = None
            self.motion_profile = None
            self.motion_profile_digest = None
            self.motion_mapping_id = None
            self.motion_admitted_ranges = {}
            if motion_profile_id:
                self.motion_registry = MotionCompatibilityRegistry(Path(__file__).parent / "motion_profiles")
                profile_template = self.motion_registry.get(motion_profile_id)
                target_adapter = profile_template["target"]["adapter_mapping_ref"]
                if target_adapter != "lerobot.so101-follower.degrees.v1":
                    raise RuntimeError(
                        f"Motion profile {motion_profile_id} targets {target_adapter}, "
                        "not the in-process SO101 follower"
                    )
                self.motion_mapping_id = profile_template["mapping"]["mapping_id"]

            # This application deliberately exposes one unit only:
            # degrees for every motor, including the gripper.
            for device in (self.robot, self.teleop):
                bus = getattr(device, "bus", None)
                if bus and "gripper" in bus.motors:
                    bus.motors["gripper"].norm_mode = MotorNormMode.DEGREES
            
            # Create processors (LeRobot's default processors)
            self.teleop_action_processor, self.robot_action_processor, self.robot_observation_processor = make_default_processors()
            
            # Connect devices. Web/server boot must never ask for keyboard input.
            # It may, however, heal one stable mismatch by writing the existing
            # repo/cache calibration to Feetech registers, because LeRobot 0.6.1
            # treats a transient register-read mismatch as "not calibrated" and
            # would otherwise ask for ENTER in calibrate().
            self._connect_device_non_interactive(self.teleop, "teleoperator")
            self._connect_device_non_interactive(self.robot, "robot")

            if self.motion_profile_id and self.motion_registry is not None:
                profile_template = self.motion_registry.get(self.motion_profile_id)
                calibration_fingerprints = self.get_calibration_fingerprints()
                source_ref = calibration_fingerprints.get("source")
                target_ref = calibration_fingerprints.get("target")
                if not source_ref or not target_ref:
                    raise RuntimeError("Cannot bind motion compatibility without source and target calibration fingerprints")

                source_ranges = self._device_degree_ranges(self.teleop)
                target_ranges = self._device_degree_ranges(self.robot)
                self.motion_profile = bind_runtime_calibration(
                    profile_template,
                    source_calibration_ref=source_ref,
                    target_calibration_ref=target_ref,
                    source_ranges=source_ranges,
                    target_ranges=target_ranges,
                )
                self.motion_profile_digest = profile_digest(self.motion_profile)
                self.motion_admitted_ranges = {
                    item["source_dof"]: {
                        "minimum": float(item["source_range"]["minimum"]),
                        "maximum": float(item["source_range"]["maximum"]),
                    }
                    for item in self.motion_profile["mapping"]["dof_mappings"]
                }
                logging.info(
                    "EPAOA motion compatibility enabled: profile=%s mapping=%s calibration-bound digest=%s",
                    self.motion_profile_id,
                    self.motion_mapping_id,
                    self.motion_profile_digest,
                )
                logging.info("EPAOA admitted source ranges (deg): %s", self.motion_admitted_ranges)
            
            self.fps = fps
            self.actual_fps = 0.0
            self.processing_ms = 0.0
            self._fps_window_started = time.perf_counter()
            self._fps_window_count = 0
            self.started_at = time.time()
            self.is_running = True
            self.connection_state = "running"
            
            # Start teleoperation loop in separate thread
            self.thread = threading.Thread(target=self._teleop_loop, daemon=True)
            self.thread.start()
            
            logging.info("Teleoperation started successfully")
            return True
            
        except Exception as e:
            self.connection_state = "error"
            self.last_error = str(e)
            logging.error(f"Failed to start teleoperation: {e}")
            self.stop(preserve_error=True)
            return False

    def _connect_device_non_interactive(self, device, label: str):
        """Connect with existing calibration only; never open an interactive prompt.

        LeRobot's default connect(calibrate=True) path can call calibrate(), and
        calibrate() prompts: "Press ENTER to use provided calibration file...".
        That is fine in a terminal but fatal during headless delivery.

        Delivery behavior implemented here:
          1. connect(calibrate=False) with a few retries for cold-boot USB/bus timing;
          2. verify calibration by reading the motor registers repeatedly;
          3. on transient read errors, wait/retry instead of treating it as lost calibration;
          4. if there is a stable register mismatch and a repo/cache calibration exists,
             write that existing calibration to the Feetech registers once;
          5. verify again; otherwise fail visibly in logs/UI.
        """
        last_error = None
        for attempt in range(1, 4):
            try:
                try:
                    device.connect(calibrate=False)
                except TypeError:
                    raise RuntimeError(
                        f"{label} connect() does not support calibrate=False; refusing interactive connect()"
                    )
                break
            except Exception as exc:
                last_error = exc
                logging.warning("%s non-interactive connect attempt %d/3 failed: %s", label, attempt, exc)
                time.sleep(0.75 * attempt)
        else:
            raise RuntimeError(f"{label} failed to connect non-interactively: {last_error}")

        self._ensure_existing_calibration_applied(device, label)

    def _ensure_existing_calibration_applied(self, device, label: str) -> None:
        """Verify and, if needed, apply the existing calibration non-interactively."""
        bus = getattr(device, "bus", None)
        calibration = getattr(device, "calibration", None)
        device_id = getattr(device, "id", "unknown")

        if bus is None:
            logging.info("%s has no bus; skipping register-level calibration verification", label)
            return

        if not calibration:
            raise RuntimeError(
                f"{label} id={device_id} has no calibration file loaded; cannot start headless teleop"
            )

        if self._calibration_matches_with_retries(device, label, attempts=6, delay_s=0.35):
            logging.info("%s id=%s calibration registers match existing file", label, device_id)
            return

        logging.warning(
            "%s id=%s has a stable calibration register mismatch; applying existing repo/cache calibration once",
            label,
            device_id,
        )
        try:
            bus.write_calibration(calibration)
        except Exception as exc:
            raise RuntimeError(f"{label} failed to write existing calibration to motor registers: {exc}") from exc

        if not self._calibration_matches_with_retries(device, label, attempts=6, delay_s=0.35):
            raise RuntimeError(
                f"{label} id={device_id} calibration still mismatches after applying existing calibration"
            )

        logging.info("%s id=%s existing calibration applied and verified", label, device_id)

    def _calibration_matches_with_retries(self, device, label: str, attempts: int, delay_s: float) -> bool:
        """Read LeRobot's is_calibrated repeatedly to absorb cold-boot bus glitches."""
        failures = []
        false_count = 0
        for attempt in range(1, attempts + 1):
            try:
                if bool(device.is_calibrated):
                    if failures or false_count:
                        logging.info(
                            "%s calibration matched after %d attempt(s); transient bus mismatch/read issue recovered",
                            label,
                            attempt,
                        )
                    return True
                false_count += 1
                logging.warning(
                    "%s calibration register mismatch on attempt %d/%d",
                    label,
                    attempt,
                    attempts,
                )
            except Exception as exc:
                failures.append(str(exc))
                logging.warning(
                    "%s calibration register read failed on attempt %d/%d: %s",
                    label,
                    attempt,
                    attempts,
                    exc,
                )
            time.sleep(delay_s)

        if failures and false_count == 0:
            raise RuntimeError(
                f"{label} calibration registers could not be read reliably after {attempts} attempts: {failures[-1]}"
            )
        return False
    
    def _teleop_loop(self):
        """
        Main teleoperation loop - adapted from LeRobot's teleop_loop function.
        Stays close to original implementation for easy updates.
        """
        start = time.perf_counter()
        
        while self.is_running:
            loop_start = time.perf_counter()
            
            try:
                # Get robot observation (LeRobot's method)
                obs = self.robot.get_observation()
                
                # Get teleop action (LeRobot's method)
                raw_action = self.teleop.get_action()
                
                # Process teleop action through pipeline (LeRobot's processors)
                teleop_action = self.teleop_action_processor((raw_action, obs))

                # Optional EPAOA Motion Compatibility boundary. Native source
                # values are never treated as native target values by assumption.
                action_for_robot = teleop_action
                resolved_motion = None
                if self.motion_profile is not None and self.motion_profile_id is not None:
                    profile = self.motion_profile
                    source_names = {
                        item["source_dof"]
                        for item in profile["mapping"]["dof_mappings"]
                    }
                    source_values: Dict[str, float] = {}
                    for key, value in teleop_action.items():
                        base = str(key).replace(".pos", "")
                        if base not in source_names:
                            continue
                        try:
                            source_values[base] = float(value)
                        except (TypeError, ValueError) as exc:
                            raise RuntimeError(
                                f"Non-numeric teleoperation value for {base}: {value!r}"
                            ) from exc

                    resolved_motion = resolve_motion(
                        self.motion_profile,
                        source_values,
                    )
                    target_native = resolved_motion["target_native_command"]

                    # Preserve LeRobot's original action-key shape. Some versions
                    # use base motor names and others use a '.pos' suffix.
                    action_for_robot = {}
                    emitted_targets = set()
                    for original_key in teleop_action:
                        base = str(original_key).replace(".pos", "")
                        if base in target_native:
                            action_for_robot[original_key] = target_native[base]
                            emitted_targets.add(base)
                    for base, value in target_native.items():
                        if base not in emitted_targets:
                            action_for_robot[f"{base}.pos"] = value

                # Process action for robot through pipeline (LeRobot's processors)
                robot_action_to_send = self.robot_action_processor((action_for_robot, obs))
                
                # Send processed action to robot (LeRobot's method)
                _ = self.robot.send_action(robot_action_to_send)
                
                # Store current state for web access
                with self.lock:
                    self.current_observation = obs
                    self.current_action = robot_action_to_send
                    self.current_canonical_action = (
                        dict(resolved_motion["canonical_command"])
                        if resolved_motion is not None else None
                    )
                    
                    # Debug: log observation keys once at startup
                    if not hasattr(self, '_logged_obs_keys'):
                        self._logged_obs_keys = True
                        logging.info(f"Observation keys sample: {list(obs.keys())[:10]}")
                        if obs:
                            first_key = list(obs.keys())[0]
                            logging.info(f"Sample observation: {first_key} = {obs[first_key]}")
                
                # Maintain target FPS and publish lightweight diagnostics.
                dt_s = time.perf_counter() - loop_start
                self.processing_ms = dt_s * 1000.0
                sleep_s = max(0.0, (1 / self.fps) - dt_s)
                precise_sleep(sleep_s)

                self._fps_window_count += 1
                now = time.perf_counter()
                fps_elapsed = now - self._fps_window_started
                if fps_elapsed >= 1.0:
                    self.actual_fps = self._fps_window_count / fps_elapsed
                    self._fps_window_started = now
                    self._fps_window_count = 0
                
            except Exception as e:
                if self.is_running:  # Only log if not stopping
                    self.loop_errors += 1
                    self.last_error = str(e)
                    self.connection_state = "error"
                    self.is_running = False
                    logging.error(f"Error in teleoperation loop: {e}")
                break
    
    def stop(self, preserve_error: bool = False):
        """Stop teleoperation and cleanup."""
        if not self.is_running and self.robot is None and self.teleop is None:
            if not preserve_error:
                self.connection_state = "stopped"
            return
        
        logging.info("Stopping teleoperation...")
        if not preserve_error:
            self.connection_state = "stopping"
        self.is_running = False
        
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        
        # Disconnect devices (LeRobot's cleanup)
        try:
            if self.teleop:
                self.teleop.disconnect()
        except Exception as e:
            logging.error(f"Error disconnecting teleoperator: {e}")
        
        try:
            if self.robot:
                self.robot.disconnect()
        except Exception as e:
            logging.error(f"Error disconnecting robot: {e}")
        
        # Clear state
        self.teleop = None
        self.robot = None
        self.current_observation = None
        self.current_action = None
        self.current_canonical_action = None
        self.motion_profile = None
        self.motion_admitted_ranges = {}
        
        if not preserve_error:
            self.connection_state = "stopped"
            self.last_error = None
        logging.info("Teleoperation stopped")
    
    def get_current_positions(self) -> Optional[Dict[str, float]]:
        """
        Get current robot joint positions.
        
        Returns:
            Dictionary mapping motor names to positions in degrees, or None if not available
        """
        with self.lock:
            if self.current_observation is None:
                return None
            
            # Extract positions from observation
            # LeRobot observation is a flat dict with motor names as keys
            # Try different possible structures
            positions = {}
            
            # Method 1: Direct motor names (most common)
            for key, value in self.current_observation.items():
                # Skip non-numeric values
                if isinstance(value, (int, float)):
                    # Remove common prefixes if present
                    motor_name = key
                    if key.startswith("observation.state."):
                        motor_name = key.replace("observation.state.", "")
                    elif key.startswith("state."):
                        motor_name = key.replace("state.", "")
                    
                    positions[motor_name] = value
            
            # Debug log once
            if not hasattr(self, '_logged_positions'):
                self._logged_positions = True
                logging.info(f"Extracted {len(positions)} positions: {list(positions.keys())}")
            
            return positions if positions else None
    
    def get_current_action(self) -> Optional[Dict[str, float]]:
        """
        Get current action being sent to robot.
        
        Returns:
            Dictionary mapping motor names to target positions, or None if not available
        """
        with self.lock:
            return self.current_action.copy() if self.current_action else None
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get teleoperation status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "is_running": self.is_running,
            "connection_state": self.connection_state,
            "has_robot": self.robot is not None,
            "has_teleop": self.teleop is not None,
            "target_fps": self.fps,
            "actual_fps": round(self.actual_fps, 1),
            "processing_ms": round(self.processing_ms, 2),
            "loop_errors": self.loop_errors,
            "last_error": self.last_error,
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at else 0.0,
            "has_positions": self.current_observation is not None,
            "motion_profile_id": self.motion_profile_id,
            "motion_profile_digest": self.motion_profile_digest,
            "motion_mapping_id": self.motion_mapping_id,
            "motion_admitted_ranges": dict(self.motion_admitted_ranges),
            "calibration_fingerprints": self.get_calibration_fingerprints(),
        }

    @staticmethod
    def _device_degree_ranges(device: Any) -> Dict[str, tuple[float, float]]:
        """Return the calibrated degree envelope used by LeRobot 0.6.1.

        LeRobot's DEGREES normalization uses the calibration midpoint and motor
        resolution. The valid calibrated envelope therefore depends on the
        actual range_min/range_max stored for each connected device.
        """
        bus = getattr(device, "bus", None)
        calibration = getattr(device, "calibration", None)
        if bus is None or not calibration:
            raise RuntimeError("Device has no bus/calibration for runtime motion compatibility")

        ranges: Dict[str, tuple[float, float]] = {}
        for motor_name, motor in bus.motors.items():
            cal = calibration.get(motor_name)
            if cal is None:
                raise RuntimeError(f"Missing calibration for motor {motor_name}")
            min_raw = float(cal.range_min)
            max_raw = float(cal.range_max)
            if min_raw >= max_raw:
                raise RuntimeError(f"Invalid calibration range for motor {motor_name}: {min_raw}..{max_raw}")
            try:
                resolution = float(bus.model_resolution_table[motor.model])
            except Exception as exc:
                raise RuntimeError(f"Cannot determine motor resolution for {motor_name}/{motor.model}") from exc
            max_res = resolution - 1.0
            midpoint = (min_raw + max_raw) / 2.0
            min_deg = (min_raw - midpoint) * 360.0 / max_res
            max_deg = (max_raw - midpoint) * 360.0 / max_res
            ranges[motor_name] = (min(min_deg, max_deg), max(min_deg, max_deg))
        return ranges

    @staticmethod
    def _stable_calibration_value(value: Any) -> Any:
        if is_dataclass(value):
            return {
                str(k): TeleoperationManager._stable_calibration_value(v)
                for k, v in asdict(value).items()
            }
        if isinstance(value, dict):
            return {
                str(k): TeleoperationManager._stable_calibration_value(v)
                for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple)):
            return [TeleoperationManager._stable_calibration_value(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _calibration_fingerprint(cls, device: Any) -> Optional[str]:
        calibration = getattr(device, "calibration", None)
        if not calibration:
            return None
        stable = cls._stable_calibration_value(calibration)
        payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def get_calibration_fingerprints(self) -> Dict[str, Optional[str]]:
        return {
            "source": self._calibration_fingerprint(self.teleop) if self.teleop is not None else None,
            "target": self._calibration_fingerprint(self.robot) if self.robot is not None else None,
        }

    def get_motion_evidence(self) -> Dict[str, Any]:
        with self.lock:
            canonical = dict(self.current_canonical_action) if self.current_canonical_action else None
        return {
            "compatibility_id": self.motion_profile_id,
            "profile_digest": self.motion_profile_digest,
            "mapping_id": self.motion_mapping_id,
            "calibration_fingerprints": self.get_calibration_fingerprints(),
            "admitted_ranges": dict(self.motion_admitted_ranges),
            "canonical_command": canonical,
        }

    def apply_leader_positions(self, positions: Dict[str, float]) -> bool:
        """
        Apply leader-provided target positions directly to the robot.
        Expects joint targets in degrees for every motor, including the gripper.
        """
        if not self.is_running or self.robot is None:
            logging.warning("Cannot apply leader positions: teleoperation not running or robot missing")
            return False

        try:
            # Build a RobotAction-compatible dict using observation keys
            # Normalize keys by stripping '.pos'
            action = {}
            for k, v in positions.items():
                base = str(k).replace('.pos', '')
                # Use both base and '.pos' to maximize compatibility
                action[base] = float(v)
                action[f"{base}.pos"] = float(v)

            # Process through the robot action processor if available
            with self.lock:
                obs = self.current_observation or {}
            if self.robot_action_processor is not None:
                processed = self.robot_action_processor((action, obs))
            else:
                processed = action

            # Send to robot
            _ = self.robot.send_action(processed)

            # Cache as current action
            with self.lock:
                self.current_action = processed

            return True
        except Exception as e:
            logging.error(f"apply_leader_positions failed: {e}")
            return False


# Global instance for web server access
_teleoperation_manager: Optional[TeleoperationManager] = None


def get_teleoperation_manager() -> TeleoperationManager:
    """Get or create the global teleoperation manager instance."""
    global _teleoperation_manager
    if _teleoperation_manager is None:
        _teleoperation_manager = TeleoperationManager()
    return _teleoperation_manager


if __name__ == "__main__":
    # Test example
    manager = TeleoperationManager()
    
    if manager.start(
        robot_type="so101_follower",
        robot_port="/dev/ttyACM0",
        robot_id="black",
        teleop_type="so101_leader",
        teleop_port="/dev/ttyACM1",
        teleop_id="yellow",
        fps=60
    ):
        try:
            print("Teleoperation running... Press Ctrl+C to stop")
            while True:
                time.sleep(1)
                positions = manager.get_current_positions()
                if positions:
                    print(f"Positions: {positions}")
        except KeyboardInterrupt:
            pass
        finally:
            manager.stop()

