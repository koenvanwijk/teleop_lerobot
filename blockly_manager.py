"""
Blockly Manager for LeRobot
Handles Blockly visual programming and Python code execution
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
import json
import time
import io
import sys
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class RobotAPI:
    """
    Real LeRobot API wrapper for Blockly programs
    Communicates with the actual robot hardware
    """
    
    def __init__(self, robot_port: Optional[str] = None, robot_type: Optional[str] = None, robot_id: Optional[str] = None):
        """
        Initialize robot API
        
        Args:
            robot_port: Serial port of the follower robot (e.g., /dev/tty_follower)
            robot_type: Robot type (e.g., 'so101', 'so100', 'koch')
            robot_id: Robot identifier (e.g., 'white', 'black', 'default')
        """
        self.robot = None
        self.robot_port = robot_port
        self.robot_type = robot_type or "so101"  # Default to so101
        self.robot_id = robot_id or "default"  # Default to 'default'
        self.positions = [0.0] * 6  # Cache for 5 DOF + gripper
        # Don't initialize robot here - do it lazily when needed

    
    def _initialize_robot(self):
        """Initialize the real LeRobot connection"""
        try:
            if self.robot_port:
                # Dynamic import based on robot type (from port name like /dev/tty_white_follower_so101)
                # Extract robot type from port if not provided
                if not self.robot_type and "_follower_" in self.robot_port:
                    # e.g., /dev/tty_white_follower_so101 -> so101
                    self.robot_type = self.robot_port.split("_follower_")[-1].split("_")[0]
                
                robot_type = self.robot_type.lower()
                
                logger.info(f"Initializing {robot_type} robot arm on port: {self.robot_port}, id: {self.robot_id}")
                
                # Import robot module dynamically
                robot_module_name = f"{robot_type}_follower"
                robot_module = __import__(f"lerobot.robots.{robot_module_name}", fromlist=[
                    f"{robot_type.upper()}Follower",
                    f"{robot_type.upper()}FollowerConfig"
                ])
                
                # Get robot class and config class
                robot_class = getattr(robot_module, f"{robot_type.upper()}Follower")
                config_class = getattr(robot_module, f"{robot_type.upper()}FollowerConfig")
                
                # Create config with port and id
                config = config_class(port=self.robot_port, id=self.robot_id)
                self.robot = robot_class(config=config)
                self.robot.connect()
                
                logger.info(f"✅ {robot_type.upper()} robot arm connected successfully")
                
                # Read initial positions
                self._update_positions()
            else:
                logger.warning("No robot port provided, using simulation mode")
                
        except Exception as e:
            logger.error(f"Failed to initialize robot: {e}", exc_info=True)
            logger.warning("Falling back to simulation mode")
            self.robot = None
    
    def _update_positions(self):
        """Read current positions from robot"""
        if self.robot:
            try:
                # Get current observation from robot arm
                obs = self.robot.get_observation()
                # Extract positions from observation dict (motor_name.pos format)
                motor_names = list(self.robot.bus.motors.keys())
                self.positions = [obs[f"{name}.pos"] for name in motor_names]
            except Exception as e:
                logger.error(f"Error reading positions: {e}")
    
    def move_joint(self, joint: int, angle: float):
        """
        Move a specific joint to target angle
        
        Args:
            joint: Joint index (0-5: joints 1-5 + gripper)
            angle: Target angle in degrees
        """
        if joint < 0 or joint >= 6:
            logger.error(f"Invalid joint index: {joint}")
            return
        
        try:
            if self.robot:
                # Get motor names from robot bus
                motor_names = list(self.robot.bus.motors.keys())
                
                if joint >= len(motor_names):
                    logger.error(f"Joint {joint} out of range (robot has {len(motor_names)} motors)")
                    return
                
                # Create action dict with target position for specific motor
                # Format: {"motor_name.pos": value, ...}
                action = {}
                for i, name in enumerate(motor_names):
                    if i == joint:
                        action[f"{name}.pos"] = angle
                    else:
                        action[f"{name}.pos"] = self.positions[i]
                
                # Send action to robot
                self.robot.send_action(action)
                self.positions[joint] = angle
                
                logger.info(f"Moved joint {joint} ({motor_names[joint]}) to {angle}°")
            else:
                # Simulation mode
                self.positions[joint] = angle
                print(f"[SIM] Moving joint {joint} to {angle}°")
                
        except Exception as e:
            logger.error(f"Error moving joint {joint}: {e}")
    
    def get_joint_position(self, joint: int) -> float:
        """
        Get current position of a joint
        
        Args:
            joint: Joint index (0-5)
            
        Returns:
            Current angle in degrees
        """
        if joint < 0 or joint >= 6:
            logger.error(f"Invalid joint index: {joint}")
            return 0.0
        
        if self.robot:
            self._update_positions()
        
        return self.positions[joint]
    
    def read_all_positions(self) -> list:
        """
        Read all joint positions from robot
        
        Returns:
            List of 6 joint angles in percentage (-100 to 100)
        """
        # Try to get positions from teleoperation manager first (if running)
        try:
            from teleoperation_manager import get_teleoperation_manager
            teleop_manager = get_teleoperation_manager()
            
            if teleop_manager.is_running:
                positions_dict = teleop_manager.get_current_positions()
                if positions_dict:
                    # Extract positions in consistent order
                    motor_names = ['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos', 
                                   'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos']
                    angles = []
                    for name in motor_names:
                        # Remove .pos suffix for lookup
                        clean_name = name.replace('.pos', '')
                        if clean_name in positions_dict:
                            angles.append(positions_dict[clean_name])
                        elif name in positions_dict:
                            angles.append(positions_dict[name])
                        else:
                            angles.append(0.0)
                    
                    self.positions = angles
                    logger.info(f"Read positions from teleoperation: {angles}")
                    return angles
        except Exception as e:
            logger.debug(f"Could not get positions from teleoperation: {e}")
        
        # Fallback: read directly from robot if available
        if self.robot:
            try:
                # Read observation from robot arm
                obs = self.robot.get_observation()
                motor_names = list(self.robot.bus.motors.keys())
                angles = [obs[f"{name}.pos"] for name in motor_names]
                
                # Update cache
                self.positions = angles
                
                logger.info(f"Read positions from robot: {angles}")
                return angles
                
            except Exception as e:
                logger.error(f"Error reading all positions: {e}", exc_info=True)
                return [0.0] * 6
        else:
            # Simulation mode - return cached values
            logger.info(f"[SIM] Positions: {self.positions}")
            return self.positions
    
    def disconnect(self):
        """Disconnect from robot"""
        if self.robot:
            try:
                self.robot.disconnect()
                logger.info("Robot disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting robot: {e}")


class BlocklyManager:
    """Manages Blockly programs and execution"""

    def __init__(self, robot_port: Optional[str] = None, robot_type: Optional[str] = None, robot_id: Optional[str] = None):
        self.saved_programs: Dict[str, Dict[str, Any]] = {}
        self.programs_file = Path.home() / ".lerobot_blockly_programs.json"
        self.saved_positions: Dict[str, Dict[str, Any]] = {}
        self.positions_file = Path.home() / ".lerobot_saved_positions.json"
        self.robot_api = RobotAPI(robot_port, robot_type, robot_id)
        self.load_programs()
        self.load_saved_positions()
        logger.info(f"BlocklyManager initialized (port: {robot_port}, type: {robot_type}, id: {robot_id})")

    def load_programs(self):
        """Load saved programs from disk"""
        try:
            if self.programs_file.exists():
                with open(self.programs_file, 'r') as f:
                    self.saved_programs = json.load(f)
                logger.info(f"Loaded {len(self.saved_programs)} saved programs")
        except Exception as e:
            logger.error(f"Error loading programs: {e}")
            self.saved_programs = {}

    def save_programs(self):
        """Save programs to disk"""
        try:
            with open(self.programs_file, 'w') as f:
                json.dump(self.saved_programs, f, indent=2)
            logger.info(f"Saved {len(self.saved_programs)} programs")
        except Exception as e:
            logger.error(f"Error saving programs: {e}")

    def load_saved_positions(self):
        """Load saved positions from disk"""
        try:
            if self.positions_file.exists():
                with open(self.positions_file, 'r') as f:
                    self.saved_positions = json.load(f)
                logger.info(f"Loaded {len(self.saved_positions)} saved positions")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
            self.saved_positions = {}

    def save_positions_to_disk(self):
        """Save positions to disk"""
        try:
            with open(self.positions_file, 'w') as f:
                json.dump(self.saved_positions, f, indent=2)
            logger.info(f"Saved {len(self.saved_positions)} positions to disk")
        except Exception as e:
            logger.error(f"Error saving positions: {e}")

    def save_position(self, name: str, angles: List[float], description: str = "") -> bool:
        """
        Save a robot position
        
        Args:
            name: Position name
            angles: List of joint angles (percentage -100 to 100)
            description: Optional description
            
        Returns:
            True if successful
        """
        try:
            self.saved_positions[name] = {
                'angles': angles,
                'description': description,
                'timestamp': datetime.now().isoformat()
            }
            self.save_positions_to_disk()
            logger.info(f"Saved position: {name} with angles: {angles}")
            return True
        except Exception as e:
            logger.error(f"Error saving position {name}: {e}")
            return False

    def get_saved_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all saved positions"""
        return self.saved_positions

    def delete_position(self, name: str) -> bool:
        """Delete a saved position"""
        try:
            if name in self.saved_positions:
                del self.saved_positions[name]
                self.save_positions_to_disk()
                logger.info(f"Deleted position: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting position {name}: {e}")
            return False

    def save_program(self, name: str, workspace_json: str, python_code: str) -> bool:
        """
        Save a Blockly program
        
        Args:
            name: Program name
            workspace_json: Blockly workspace JSON representation
            python_code: Generated Python code
            
        Returns:
            True if successful
        """
        try:
            self.saved_programs[name] = {
                'workspace': workspace_json,
                'python_code': python_code,
                'timestamp': asyncio.get_event_loop().time()
            }
            self.save_programs()
            logger.info(f"Saved program: {name}")
            return True
        except Exception as e:
            logger.error(f"Error saving program {name}: {e}")
            return False

    def load_program(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load a saved program
        
        Args:
            name: Program name
            
        Returns:
            Program dict or None
        """
        return self.saved_programs.get(name)

    def delete_program(self, name: str) -> bool:
        """
        Delete a saved program
        
        Args:
            name: Program name
            
        Returns:
            True if successful
        """
        try:
            if name in self.saved_programs:
                del self.saved_programs[name]
                self.save_programs()
                logger.info(f"Deleted program: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting program {name}: {e}")
            return False

    def list_programs(self) -> Dict[str, Dict[str, Any]]:
        """
        List all saved programs
        
        Returns:
            Dictionary of programs
        """
        return self.saved_programs

    async def execute_python_code(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute Python code safely with real robot access
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Execution result dict
        """
        try:
            logger.info("Executing Blockly-generated Python code")
            
            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()
            
            try:
                # Create execution environment with real robot API
                local_vars = {}
                global_vars = {
                    '__builtins__': {
                        '__import__': __import__,  # Allow imports
                        'print': print,
                        'range': range,
                        'len': len,
                        'enumerate': enumerate,
                        'str': str,
                        'int': int,
                        'float': float,
                        'list': list,
                        'dict': dict,
                        'abs': abs,
                        'min': min,
                        'max': max,
                        'round': round,
                    },
                    'time': time,
                    'robot': self.robot_api,  # Real robot access!
                    'positions': self.saved_positions,  # Saved positions access!
                }
                
                # Execute code
                exec(code, global_vars, local_vars)
                
                # Get captured output
                output = captured_output.getvalue()
                
                return {
                    'success': True,
                    'output': output or 'Execution completed successfully',
                    'variables': {k: str(v) for k, v in local_vars.items() if not k.startswith('_')}
                }
                
            except Exception as e:
                logger.error(f"Error executing code: {e}", exc_info=True)
                output = captured_output.getvalue()
                return {
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'output': output
                }
            finally:
                sys.stdout = old_stdout
                
        except Exception as e:
            logger.error(f"Unexpected error in execute_python_code: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    def shutdown(self):
        """Shutdown and cleanup"""
        logger.info("Shutting down BlocklyManager")
        if self.robot_api:
            self.robot_api.disconnect()

    def generate_custom_blocks(self) -> str:
        """
        Generate custom Blockly blocks definition for LeRobot
        
        Returns:
            JavaScript code for custom blocks
        """
        return """
// Custom LeRobot Blocks
Blockly.Blocks['robot_move_joint'] = {
  init: function() {
    this.appendValueInput("JOINT")
        .setCheck("Number")
        .appendField("Move joint");
    this.appendValueInput("ANGLE")
        .setCheck("Number")
        .appendField("to angle");
    this.setPreviousStatement(true, null);
    this.setNextStatement(true, null);
    this.setColour(230);
    this.setTooltip("Move a robot joint to specified angle");
    this.setHelpUrl("");
  }
};

Blockly.Python['robot_move_joint'] = function(block) {
  var value_joint = Blockly.Python.valueToCode(block, 'JOINT', Blockly.Python.ORDER_ATOMIC);
  var value_angle = Blockly.Python.valueToCode(block, 'ANGLE', Blockly.Python.ORDER_ATOMIC);
  var code = 'move_joint(' + value_joint + ', ' + value_angle + ')\\n';
  return code;
};

Blockly.Blocks['robot_get_position'] = {
  init: function() {
    this.appendValueInput("JOINT")
        .setCheck("Number")
        .appendField("Get position of joint");
    this.setOutput(true, "Number");
    this.setColour(230);
    this.setTooltip("Get current position of a joint");
    this.setHelpUrl("");
  }
};

Blockly.Python['robot_get_position'] = function(block) {
  var value_joint = Blockly.Python.valueToCode(block, 'JOINT', Blockly.Python.ORDER_ATOMIC);
  var code = 'get_joint_position(' + value_joint + ')';
  return [code, Blockly.Python.ORDER_FUNCTION_CALL];
};

Blockly.Blocks['robot_wait'] = {
  init: function() {
    this.appendValueInput("DURATION")
        .setCheck("Number")
        .appendField("Wait");
    this.appendDummyInput()
        .appendField("seconds");
    this.setPreviousStatement(true, null);
    this.setNextStatement(true, null);
    this.setColour(160);
    this.setTooltip("Wait for specified duration");
    this.setHelpUrl("");
  }
};

Blockly.Python['robot_wait'] = function(block) {
  var value_duration = Blockly.Python.valueToCode(block, 'DURATION', Blockly.Python.ORDER_ATOMIC);
  var code = 'import time\\ntime.sleep(' + value_duration + ')\\n';
  return code;
};

Blockly.Blocks['robot_gripper'] = {
  init: function() {
    this.appendDummyInput()
        .appendField("Gripper")
        .appendField(new Blockly.FieldDropdown([["Open","open"], ["Close","close"]]), "ACTION");
    this.setPreviousStatement(true, null);
    this.setNextStatement(true, null);
    this.setColour(290);
    this.setTooltip("Control gripper");
    this.setHelpUrl("");
  }
};

Blockly.Python['robot_gripper'] = function(block) {
  var dropdown_action = block.getFieldValue('ACTION');
  var code = 'gripper_' + dropdown_action + '()\\n';
  return code;
};
"""
