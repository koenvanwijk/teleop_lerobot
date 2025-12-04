#!/usr/bin/env python3
"""
Teleoperation Manager - Based on LeRobot's lerobot_teleoperate.py
Adapted to run in-process with access to robot positions for web visualization

This implementation stays close to LeRobot's original code for easy updates.
"""

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License")

import logging
import time
import threading
import sys
from dataclasses import asdict, dataclass
from typing import Optional, Dict, Any
from pprint import pformat

import draccus

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
from lerobot.utils.import_utils import register_third_party_devices
from lerobot.utils.robot_utils import busy_wait
from lerobot.utils.utils import init_logging
from lerobot.scripts.lerobot_teleoperate import TeleoperateConfig


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
        self.lock = threading.Lock()
        self.fps = 60
        
        # Processors (same as LeRobot)
        self.teleop_action_processor = None
        self.robot_action_processor = None
        self.robot_observation_processor = None
        
        init_logging()
        register_third_party_devices()
    
    def start(self, robot_type: str, robot_port: str, robot_id: str, 
              teleop_type: str, teleop_port: str, teleop_id: str, fps: int = 60):
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
        """
        if self.is_running:
            logging.warning("Teleoperation already running")
            return False
        
        try:
            # Use LeRobot's draccus parser to build config (same as command-line tool)
            # This ensures 100% compatibility with LeRobot's config system
            old_argv = sys.argv
            try:
                sys.argv = [
                    'teleoperate',
                    f'--robot.type={robot_type}',
                    f'--robot.port={robot_port}',
                    f'--robot.id={robot_id}',
                    f'--teleop.type={teleop_type}',
                    f'--teleop.port={teleop_port}',
                    f'--teleop.id={teleop_id}',
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
            
            # Create processors (LeRobot's default processors)
            self.teleop_action_processor, self.robot_action_processor, self.robot_observation_processor = make_default_processors()
            
            # Connect devices
            self.teleop.connect()
            self.robot.connect()
            
            self.fps = fps
            self.is_running = True
            
            # Start teleoperation loop in separate thread
            self.thread = threading.Thread(target=self._teleop_loop, daemon=True)
            self.thread.start()
            
            logging.info("Teleoperation started successfully")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start teleoperation: {e}")
            self.stop()
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
                
                # Process action for robot through pipeline (LeRobot's processors)
                robot_action_to_send = self.robot_action_processor((teleop_action, obs))
                
                # Send processed action to robot (LeRobot's method)
                _ = self.robot.send_action(robot_action_to_send)
                
                # Store current state for web access
                with self.lock:
                    self.current_observation = obs
                    self.current_action = robot_action_to_send
                    
                    # Debug: log observation keys once at startup
                    if not hasattr(self, '_logged_obs_keys'):
                        self._logged_obs_keys = True
                        logging.info(f"Observation keys sample: {list(obs.keys())[:10]}")
                        if obs:
                            first_key = list(obs.keys())[0]
                            logging.info(f"Sample observation: {first_key} = {obs[first_key]}")
                
                # Maintain target FPS (LeRobot's busy_wait)
                dt_s = time.perf_counter() - loop_start
                busy_wait(1 / self.fps - dt_s)
                
            except Exception as e:
                if self.is_running:  # Only log if not stopping
                    logging.error(f"Error in teleoperation loop: {e}")
                break
    
    def stop(self):
        """Stop teleoperation and cleanup."""
        if not self.is_running:
            return
        
        logging.info("Stopping teleoperation...")
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
        
        logging.info("Teleoperation stopped")
    
    def get_current_positions(self) -> Optional[Dict[str, float]]:
        """
        Get current robot joint positions.
        
        Returns:
            Dictionary mapping motor names to positions (radians), or None if not available
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
            "has_robot": self.robot is not None,
            "has_teleop": self.teleop is not None,
            "fps": self.fps,
            "has_positions": self.current_observation is not None
        }

    def apply_leader_positions(self, positions: Dict[str, float]) -> bool:
        """
        Apply leader-provided target positions directly to the robot.
        Expects percentage values: joints in -100..100, gripper in 0..100.
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

