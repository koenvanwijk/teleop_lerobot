#!/usr/bin/env python3
"""
LeRobot Teleoperation Server
FastAPI server voor remote control van teleoperation.
Met camera streaming, WebSocket en network management.
"""

import asyncio
import logging
import sys
import subprocess
import signal
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import camera en network managers (conditional imports voor ontwikkeling zonder hardware)
try:
    from camera_manager import CameraManager, generate_mjpeg_stream, detect_cameras
    CAMERA_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Camera manager not available: {e}")
    CAMERA_AVAILABLE = False

try:
    from network_manager import NetworkManager
    NETWORK_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Network manager not available: {e}")
    NETWORK_AVAILABLE = False

try:
    from blockly_manager import BlocklyManager
    BLOCKLY_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Blockly manager not available: {e}")
    BLOCKLY_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('webserver.log')
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# Robot State Management
# ============================================================================

class RobotState:
    """Globale state voor robot control met camera en network support."""
    def __init__(self):
        # Teleoperation
        self.teleop_manager = None  # TeleoperationManager instance
        self.teleop_mode: str = "stopped"
        self.devices_available: bool = False
        self.follower_port: Optional[str] = None
        self.leader_port: Optional[str] = None
        self.follower_type: Optional[str] = None
        self.leader_type: Optional[str] = None
        self.follower_id: Optional[str] = None
        self.leader_id: Optional[str] = None
        
        # Camera management
        self.camera_manager: Optional[CameraManager] = None
        self.cameras_enabled: bool = False
        
        # Network management
        self.network_manager: Optional[NetworkManager] = None
        self.network_enabled: bool = False
        
        # Blockly management
        self.blockly_manager: Optional[BlocklyManager] = None
        self.blockly_enabled: bool = False
        
        # WebSocket clients
        self.websocket_clients: List[WebSocket] = []
    
    def is_running(self) -> bool:
        """Check of teleoperation draait."""
        if self.teleop_manager is None:
            return False
        return self.teleop_manager.is_running
    
    async def broadcast_status(self, message: Dict[str, Any]):
        """Broadcast status update to all WebSocket clients."""
        disconnected = []
        for client in self.websocket_clients:
            try:
                await client.send_json(message)
            except:
                disconnected.append(client)
        
        # Remove disconnected clients
        for client in disconnected:
            if client in self.websocket_clients:
                self.websocket_clients.remove(client)
    
    def refresh_state(self):
        """Refresh state van system."""
        # Check devices
        dev_dir = Path("/dev")
        tty_devices = list(dev_dir.glob("tty_*"))
        self.devices_available = len(tty_devices) > 0
        
        # Load config
        if not self.follower_port:
            self.load_device_config()
    
    def load_device_config(self) -> bool:
        """Laad device configuratie."""
        config_file = Path.home() / ".lerobot_teleop_config"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    lines = f.read().strip().split('\n')
                    if len(lines) >= 2:
                        saved_follower = lines[0].strip()
                        saved_leader = lines[1].strip()
                        
                        if Path(saved_follower).exists() and Path(saved_leader).exists():
                            follower_name = Path(saved_follower).name.replace("tty_", "")
                            leader_name = Path(saved_leader).name.replace("tty_", "")
                            
                            follower_parts = follower_name.split("_")
                            leader_parts = leader_name.split("_")
                            
                            if len(follower_parts) >= 3 and len(leader_parts) >= 3:
                                self.follower_type = follower_parts[-1]
                                self.follower_id = "_".join(follower_parts[:-2])
                                self.leader_type = leader_parts[-1]
                                self.leader_id = "_".join(leader_parts[:-2])
                                self.follower_port = saved_follower
                                self.leader_port = saved_leader
                                return True
            except Exception:
                pass
        
        # Defaults
        self.follower_port = "/dev/tty_follower"
        self.leader_port = "/dev/tty_leader"
        self.follower_type = "so101"
        self.follower_id = "default"
        self.leader_type = "so101"
        self.leader_id = "default"
        
        return Path(self.follower_port).exists() and Path(self.leader_port).exists()


# Global state instance
state = RobotState()


# ============================================================================
# Pydantic Models
# ============================================================================

class TeleopControl(BaseModel):
    action: str  # "start" or "stop"


class WiFiConfig(BaseModel):
    ssid: str
    password: str


class NetworkMode(BaseModel):
    mode: str  # "ap" or "wifi"


class CameraConfig(BaseModel):
    index: int
    name: str
    resolution: List[int] = [640, 480]
    fps: int = 30


class BlocklyProgram(BaseModel):
    name: str
    workspace: str  # JSON representation of workspace
    python_code: str


class BlocklyExecute(BaseModel):
    code: str
    timeout: int = 30


# ============================================================================
# Teleoperation Functions
# ============================================================================

async def start_teleoperation() -> bool:
    """Start LeRobot teleoperation using in-process manager."""
    if state.is_running():
        logger.warning("Teleoperation draait al")
        return False
    
    logger.info("🎮 Start teleoperation...")
    
    if not state.follower_port or not state.leader_port:
        if not state.load_device_config():
            logger.error("Geen geldige device configuratie")
            return False
    
    # Get or create teleoperation manager
    from teleoperation_manager import get_teleoperation_manager
    teleop_manager = get_teleoperation_manager()
    
    try:
        logger.info(f"   Follower: {state.follower_port} ({state.follower_type}/{state.follower_id})")
        logger.info(f"   Leader: {state.leader_port} ({state.leader_type}/{state.leader_id})")
        
        # Start teleoperation in-process with proper LeRobot types
        robot_type = f"{state.follower_type}_follower"
        teleop_type = f"{state.leader_type}_leader"
        
        if teleop_manager.start(
            robot_type=robot_type,
            robot_port=state.follower_port,
            robot_id=state.follower_id,
            teleop_type=teleop_type,
            teleop_port=state.leader_port,
            teleop_id=state.leader_id,
            fps=60
        ):
            state.teleop_manager = teleop_manager
            state.teleop_mode = "teleoperation"
            logger.info("✅ Teleoperation gestart (in-process)")
            return True
        else:
            logger.error("❌ Failed to start teleoperation")
            return False
        
    except Exception as e:
        logger.error(f"❌ Fout bij starten teleoperation: {e}", exc_info=True)
        state.teleop_manager = None
        state.teleop_mode = "stopped"
        return False


async def stop_teleoperation() -> bool:
    """Stop teleoperation."""
    if not state.is_running():
        logger.warning("Teleoperation draait niet")
        state.teleop_mode = "stopped"
        return False
    
    logger.info("🛑 Stop teleoperation...")
    
    try:
        logger.info("Stopping teleoperation manager...")
        state.teleop_manager.stop()
        logger.info("✅ Teleoperation gestopt")
        
        state.teleop_manager = None
        state.teleop_mode = "stopped"
        return True
        
    except Exception as e:
        logger.error(f"❌ Fout bij stoppen teleoperation: {e}")
        return False


# ============================================================================
# FastAPI Lifespan
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("=" * 60)
    logger.info("🌐 LeRobot Teleoperation Server")
    logger.info("=" * 60)
    
    try:
        # Wacht even voor systeem stabiliteit (vooral bij boot)
        logger.info("⏳ Wacht 5 seconden voor systeem initialisatie...")
        await asyncio.sleep(5)
        
        # Initialize camera manager
        if CAMERA_AVAILABLE:
            logger.info("📹 Initializing camera manager...")
            try:
                # Detect available cameras
                available_cameras = await detect_cameras(max_index=4)
                if available_cameras:
                    camera_configs = [
                        {'index': idx, 'name': f'Camera {idx}', 'resolution': [640, 480], 'fps': 30}
                        for idx in available_cameras
                    ]
                    state.camera_manager = CameraManager(camera_configs)
                    if await state.camera_manager.initialize():
                        state.cameras_enabled = True
                        logger.info(f"✅ Camera manager initialized: {len(available_cameras)} cameras")
                    else:
                        logger.warning("⚠️  Camera manager failed to initialize")
                else:
                    logger.info("ℹ️  No cameras detected")
            except Exception as e:
                logger.error(f"Error initializing cameras: {e}")
        
        # Initialize network manager
        if NETWORK_AVAILABLE:
            logger.info("🌐 Initializing network manager...")
            try:
                state.network_manager = NetworkManager(
                    ap_ssid="LeRobot-AP",
                    ap_password="robotics123",
                    interface="wlan0"
                )
                if await state.network_manager.initialize():
                    state.network_enabled = True
                    logger.info("✅ Network manager initialized")
                else:
                    logger.warning("⚠️  Network manager failed to initialize")
            except Exception as e:
                logger.error(f"Error initializing network: {e}")
        
        # Initial state refresh to get device ports
        state.refresh_state()
        
        # Initialize Blockly manager AFTER state refresh to get correct robot port
        if BLOCKLY_AVAILABLE:
            logger.info("🧩 Initializing Blockly manager...")
            try:
                # Pass follower robot port, type and ID to Blockly for direct robot control
                robot_port = state.follower_port if state.follower_port else None
                robot_type = state.follower_type if state.follower_type else None
                robot_id = state.follower_id if state.follower_id else None
                logger.info(f"Using robot for Blockly: port={robot_port}, type={robot_type}, id={robot_id}")
                state.blockly_manager = BlocklyManager(
                    robot_port=robot_port,
                    robot_type=robot_type,
                    robot_id=robot_id
                )
                state.blockly_enabled = True
                logger.info(f"✅ Blockly manager initialized (port: {robot_port}, type: {robot_type}, id: {robot_id})")
            except Exception as e:
                logger.error(f"Error initializing Blockly: {e}")
        
        # Initial state refresh
        state.refresh_state()
        
        if state.devices_available:
            logger.info("✅ USB devices beschikbaar")
            
            # Auto-start teleoperation als devices beschikbaar zijn
            logger.info("🎮 Auto-start teleoperation...")
            await asyncio.sleep(2)  # Extra delay voor device stabiliteit
            
            if await start_teleoperation():
                logger.info("✅ Teleoperation automatisch gestart")
            else:
                logger.warning("⚠️  Kon teleoperation niet automatisch starten")
        else:
            logger.warning("⚠️  Geen USB devices gevonden - teleoperation niet gestart")
            logger.info("   💡 Sluit devices aan en start handmatig via web interface")
        
        logger.info("Server initialization complete")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
    
    yield
    
    # Shutdown
    logger.info("=" * 60)
    logger.info("🛑 Shutdown LeRobot Teleoperation Server")
    logger.info("=" * 60)
    
    try:
        # Stop teleoperation
        if state.is_running():
            logger.info("Stopping teleoperation...")
            await stop_teleoperation()
        
        # Shutdown cameras
        if state.camera_manager:
            logger.info("Shutting down cameras...")
            await state.camera_manager.shutdown()
        
        # Shutdown Blockly manager (disconnect robot)
        if state.blockly_manager:
            logger.info("Shutting down Blockly manager...")
            state.blockly_manager.shutdown()
        
        # Close WebSocket connections
        for ws in state.websocket_clients:
            try:
                await ws.close()
            except:
                pass
        
        logger.info("✅ Shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="LeRobot Teleoperation Server",
    description="FastAPI server for remote control of LeRobot teleoperation",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - serve web interface"""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        with open(template_path, 'r') as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="<h1>Template not found</h1><p>Please ensure templates/index.html exists</p>")


@app.get("/viewer")
async def robot_viewer():
    """Robot 3D viewer page (URDF-based, bambot quality)"""
    template_path = Path(__file__).parent / "templates" / "robot_viewer.html"
    if template_path.exists():
        with open(template_path, 'r') as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="<h1>Viewer not found</h1><p>Please ensure templates/robot_viewer.html exists</p>")


@app.get("/api")
async def api_info():
    """API information"""
    return {
        "name": "LeRobot Teleoperation Server",
        "version": "2.0.0",
        "endpoints": {
            "/": "Web Interface",
            "/health": "Health check",
            "/api/status": "Get teleoperation status",
            "/api/teleoperation/start": "Start teleoperation",
            "/api/teleoperation/stop": "Stop teleoperation",
            "/api/teleoperation/current-position": "Get current robot position during teleoperation",
            "/api/teleoperation/save-current-position": "Save current position during teleoperation",
            "/api/positions": "Get all saved positions",
            "/api/positions/{name}": "Delete a saved position",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "teleoperation_running": state.is_running()
    }


@app.get("/api/status")
async def get_status():
    """Get current teleoperation status"""
    state.refresh_state()
    
    return {
        "running": state.is_running(),
        "mode": state.teleop_mode,
        "devices_available": state.devices_available,
        "follower_port": state.follower_port,
        "leader_port": state.leader_port,
        "follower_type": state.follower_type,
        "leader_type": state.leader_type,
        "follower_id": state.follower_id,
        "leader_id": state.leader_id,
    }


@app.post("/api/teleoperation/start")
async def api_start_teleoperation():
    """Start teleoperation"""
    success = await start_teleoperation()
    return {
        "success": success,
        "message": "Teleoperation started" if success else "Failed to start teleoperation"
    }


@app.post("/api/teleoperation/stop")
async def api_stop_teleoperation():
    """Stop teleoperation"""
    success = await stop_teleoperation()
    return {
        "success": success,
        "message": "Teleoperation stopped" if success else "Failed to stop teleoperation"
    }


@app.get("/api/teleoperation/current-position")
async def get_teleoperation_current_position():
    """Get current position during teleoperation"""
    if not state.teleop_manager or not state.teleop_manager.is_running:
        return {
            "success": False,
            "error": "Teleoperation not running"
        }
    
    try:
        positions_dict = state.teleop_manager.get_current_positions()
        
        # Extract motor names and positions
        motor_names = list(positions_dict.keys())
        positions = list(positions_dict.values())
        
        return {
            "success": True,
            "positions": positions,
            "motor_names": motor_names,
            "source": "teleoperation"
        }
    except Exception as e:
        logger.error(f"Error getting teleoperation positions: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/teleoperation/save-current-position")
async def save_teleoperation_position(request: Request):
    """Save current position during teleoperation"""
    if not state.teleop_manager or not state.teleop_manager.is_running:
        return {
            "success": False,
            "message": "Teleoperation not running"
        }
    
    try:
        # Get request body
        body = await request.json()
        name = body.get('name', 'unnamed')
        description = body.get('description', '')
        
        # Get current positions from teleoperation
        positions_dict = state.teleop_manager.get_current_positions()
        motor_names = list(positions_dict.keys())
        positions = list(positions_dict.values())
        
        # Save to Blockly manager if available
        if state.blockly_manager:
            # Convert to format expected by Blockly (6 values array)
            position_array = positions[:6] if len(positions) >= 6 else positions
            state.blockly_manager.save_position(name, position_array, description)
        
        return {
            "success": True,
            "message": f"Position '{name}' saved successfully",
            "angles": positions,
            "motor_names": motor_names
        }
    except Exception as e:
        logger.error(f"Error saving position: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@app.get("/api/positions")
async def get_saved_positions():
    """Get all saved positions"""
    if not state.blockly_manager:
        return {
            "success": False,
            "count": 0,
            "positions": {}
        }
    
    try:
        positions = state.blockly_manager.get_saved_positions()
        return {
            "success": True,
            "count": len(positions),
            "positions": positions
        }
    except Exception as e:
        logger.error(f"Error getting saved positions: {e}")
        return {
            "success": False,
            "count": 0,
            "positions": {},
            "error": str(e)
        }


@app.delete("/api/positions/{position_name}")
async def delete_saved_position(position_name: str):
    """Delete a saved position"""
    if not state.blockly_manager:
        return {
            "success": False,
            "message": "Blockly manager not available"
        }
    
    try:
        success = state.blockly_manager.delete_position(position_name)
        return {
            "success": success,
            "message": f"Position '{position_name}' deleted" if success else "Position not found"
        }
    except Exception as e:
        logger.error(f"Error deleting position: {e}")
        return {
            "success": False,
            "message": str(e)
        }


# ============================================================================
# Camera API Endpoints
# ============================================================================

@app.get("/api/cameras")
async def get_cameras():
    """Get list of available cameras"""
    if not state.cameras_enabled or not state.camera_manager:
        return {"cameras": [], "enabled": False}
    
    return {
        "cameras": state.camera_manager.get_camera_names(),
        "enabled": True,
        "stats": state.camera_manager.get_all_stats()
    }


@app.get("/api/cameras/{camera_name}/stream")
async def camera_stream(camera_name: str):
    """MJPEG camera stream"""
    if not state.cameras_enabled or not state.camera_manager:
        raise HTTPException(status_code=503, detail="Cameras not available")
    
    camera = state.camera_manager.get_camera(camera_name)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_name}' not found")
    
    return StreamingResponse(
        generate_mjpeg_stream(camera, quality=85),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/api/cameras/detect")
async def detect_available_cameras():
    """Detect available cameras"""
    if not CAMERA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Camera support not available")
    
    cameras = await detect_cameras(max_index=10)
    return {"cameras": cameras, "count": len(cameras)}


# ============================================================================
# Network API Endpoints
# ============================================================================

@app.get("/api/network/status")
async def get_network_status():
    """Get current network status"""
    if not state.network_enabled or not state.network_manager:
        return {"enabled": False}
    
    status = await state.network_manager.get_status()
    status['enabled'] = True
    return status


@app.post("/api/network/ap/start")
async def start_access_point():
    """Start Access Point mode"""
    if not state.network_enabled or not state.network_manager:
        raise HTTPException(status_code=503, detail="Network management not available")
    
    success = await state.network_manager.start_access_point()
    return {
        "success": success,
        "message": "Access Point started" if success else "Failed to start Access Point"
    }


@app.post("/api/network/ap/stop")
async def stop_access_point():
    """Stop Access Point mode"""
    if not state.network_enabled or not state.network_manager:
        raise HTTPException(status_code=503, detail="Network management not available")
    
    success = await state.network_manager.stop_access_point()
    return {
        "success": success,
        "message": "Access Point stopped" if success else "Failed to stop Access Point"
    }


@app.post("/api/network/wifi/connect")
async def connect_wifi(config: WiFiConfig):
    """Connect to WiFi network"""
    if not state.network_enabled or not state.network_manager:
        raise HTTPException(status_code=503, detail="Network management not available")
    
    success = await state.network_manager.connect_to_wifi(config.ssid, config.password)
    return {
        "success": success,
        "message": f"Connected to {config.ssid}" if success else "Failed to connect to WiFi"
    }


@app.get("/api/network/wifi/scan")
async def scan_wifi():
    """Scan for available WiFi networks"""
    if not state.network_enabled or not state.network_manager:
        raise HTTPException(status_code=503, detail="Network management not available")
    
    networks = await state.network_manager.scan_wifi()
    return {"networks": networks, "count": len(networks)}


@app.post("/api/network/disconnect")
async def disconnect_network():
    """Disconnect from current network"""
    if not state.network_enabled or not state.network_manager:
        raise HTTPException(status_code=503, detail="Network management not available")
    
    success = await state.network_manager.disconnect()
    return {
        "success": success,
        "message": "Disconnected" if success else "Failed to disconnect"
    }


# ============================================================================
# Blockly API Endpoints
# ============================================================================

@app.get("/api/blockly/blocks")
async def get_custom_blocks():
    """Get custom Blockly blocks definition"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    return {
        "blocks": state.blockly_manager.generate_custom_blocks()
    }


@app.get("/api/blockly/programs")
async def list_programs():
    """List all saved Blockly programs"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    programs = state.blockly_manager.list_programs()
    return {
        "programs": programs,
        "count": len(programs)
    }


@app.post("/api/blockly/programs/save")
async def save_program(program: BlocklyProgram):
    """Save a Blockly program"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    success = state.blockly_manager.save_program(
        program.name,
        program.workspace,
        program.python_code
    )
    
    return {
        "success": success,
        "message": f"Program '{program.name}' saved" if success else "Failed to save program"
    }


@app.get("/api/blockly/programs/{name}")
async def load_program(name: str):
    """Load a saved Blockly program"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    program = state.blockly_manager.load_program(name)
    if not program:
        raise HTTPException(status_code=404, detail=f"Program '{name}' not found")
    
    return program


@app.delete("/api/blockly/programs/{name}")
async def delete_program(name: str):
    """Delete a saved Blockly program"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    success = state.blockly_manager.delete_program(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Program '{name}' not found")
    
    return {
        "success": True,
        "message": f"Program '{name}' deleted"
    }


@app.post("/api/blockly/execute")
async def execute_code(execution: BlocklyExecute):
    """Execute Blockly-generated Python code"""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")
    
    # Stop teleoperation if running (need exclusive access to robot)
    was_teleop_running = state.is_running()
    if was_teleop_running:
        logger.info("Stopping teleoperation for Blockly execution...")
        await stop_teleoperation()
        
        # SIGINT should handle cleanup better, but still wait a bit for hardware
        logger.info("Waiting for serial port to be released...")
        await asyncio.sleep(5.0)  # Reduced from 8s - SIGINT should cleanup faster
        logger.info("Port should now be available")
    
    try:
        # Initialize robot connection with retry logic
        logger.info("Initializing robot for Blockly...")
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            state.blockly_manager.robot_api._initialize_robot()
            
            if state.blockly_manager.robot_api.robot:
                logger.info(f"✅ Robot connected successfully on attempt {attempt + 1}")
                break
            
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Connection attempt {attempt + 1} failed, waiting {retry_delay}s before retry...")
                await asyncio.sleep(retry_delay)
                retry_delay += 1.0  # Increase delay: 2s, 3s, 4s
        
        if not state.blockly_manager.robot_api.robot:
            raise HTTPException(
                status_code=503,
                detail="Could not connect to robot after 3 attempts. Hardware may need more time to reset."
            )
        
        # Execute code
        result = await state.blockly_manager.execute_python_code(
            execution.code,
            execution.timeout
        )
        
        return result
        
    finally:
        # Disconnect robot
        logger.info("Disconnecting robot after Blockly execution...")
        state.blockly_manager.robot_api.disconnect()
        
        # Wait longer for hardware to fully reset after disconnect
        await asyncio.sleep(3.0)  # Increased to 3 seconds
        
        # Restart teleoperation if it was running
        if was_teleop_running:
            logger.info("Restarting teleoperation...")
            await start_teleoperation()


@app.get("/api/robot/positions")
async def get_robot_positions():
    """Get current robot joint positions from teleoperation or Blockly"""
    
    # Try teleoperation manager first (if running)
    if state.is_running():
        try:
            from teleoperation_manager import TeleoperationManager
            
            teleop_manager = state.teleop_manager
            positions_dict = teleop_manager.get_current_positions()
            
            if positions_dict:
                # Convert to list format (matching Blockly API)
                # LeRobot uses motor names, need to map to indices
                positions = []
                for motor_name in sorted(positions_dict.keys()):
                    positions.append(positions_dict[motor_name])
                
                return {
                    "success": True,
                    "positions": positions,
                    "motor_names": list(positions_dict.keys()),
                    "source": "teleoperation"
                }
        except Exception as e:
            logger.debug(f"Could not get positions from teleoperation: {e}")
    
    # Fallback to Blockly robot API
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Robot not available")
    
    try:
        positions = state.blockly_manager.robot_api.read_all_positions()
        return {
            "success": True,
            "positions": positions,
            "joint_names": [
                "shoulder_pan",
                "shoulder_lift", 
                "elbow_flex",
                "wrist_flex",
                "wrist_rotate",
                "gripper"
            ],
            "source": "blockly"
        }
    except Exception as e:
        logger.error(f"Error reading robot positions: {e}")
        return {
            "success": False,
            "error": str(e),
            "positions": [0.0] * 6
        }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time status updates"""
    await websocket.accept()
    state.websocket_clients.append(websocket)
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "data": {
                "running": state.is_running(),
                "cameras_enabled": state.cameras_enabled,
                "network_enabled": state.network_enabled
            }
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back for ping/pong
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in state.websocket_clients:
            state.websocket_clients.remove(websocket)


# ============================================================================
# Main Entry Point
# ============================================================================
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5000,
        log_level="info"
    )
