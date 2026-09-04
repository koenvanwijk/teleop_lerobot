#!/usr/bin/env python3
"""
LeRobot Teleoperation Server
FastAPI server voor remote control van teleoperation.
Met camera streaming, WebSocket en network management.
"""

import asyncio
import logging
import os
import sys
import subprocess
import threading
import signal
import time
import json
import ipaddress
import getpass
import socket
import shutil
import shlex
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from collections import defaultdict, deque

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

try:
    from bluetooth_gatt_server import BLEGattServer
    BLUETOOTH_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Bluetooth GATT server not available: {e}")
    BLUETOOTH_AVAILABLE = False

# Configure logging with force flush
log_handler = logging.FileHandler('webserver.log')
log_handler.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)

# Force flush after every log
class FlushingHandler(logging.Handler):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler
        
    def emit(self, record):
        self.handler.emit(record)
        self.handler.flush()

flushing_handler = FlushingHandler(log_handler)

# In-memory log buffer for the web GUI. This keeps startup messages available
# for clients that connect after the server or robot initialization has begun.
GUI_LOG_BUFFER_MAX = 1000
gui_log_buffer = deque(maxlen=GUI_LOG_BUFFER_MAX)
gui_log_lock = threading.Lock()
gui_log_sequence = 0


class GuiLogHandler(logging.Handler):
    """Capture normal Python logging records for display in the web GUI."""

    def emit(self, record):
        global gui_log_sequence
        try:
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + log_formatter.formatException(record.exc_info)

            entry = {
                "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }

            with gui_log_lock:
                gui_log_sequence += 1
                entry["seq"] = gui_log_sequence
                gui_log_buffer.append(entry)
        except Exception:
            # Logging must never interfere with robot control.
            pass


def get_gui_logs_since(after_seq: int = 0, limit: int = 200):
    """Return buffered GUI logs newer than after_seq, oldest first."""
    safe_limit = max(1, min(int(limit), 500))
    with gui_log_lock:
        entries = [dict(item) for item in gui_log_buffer if item["seq"] > after_seq]
    return entries[:safe_limit]


gui_log_handler = GuiLogHandler()
gui_log_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        flushing_handler,
        gui_log_handler
    ],
    force=True  # Override any existing logging config
)
logger = logging.getLogger(__name__)


# ============================================================================
# Device Detection
# ============================================================================

def scan_devices():
    """
    Scan /dev for leader and follower devices.
    Returns dict with 'leaders' and 'followers' lists.
    """
    dev_dir = Path("/dev")
    leaders = []
    followers = []
    
    # Zoek alle tty_* symlinks
    for device_link in sorted(dev_dir.glob("tty_*")):
        name = device_link.name
        
        # Parse naam: tty_<name>_<role>_<type>
        if not name.startswith("tty_"):
            continue
            
        parts = name.replace("tty_", "").split("_")
        if len(parts) < 3:
            continue
        
        robot_type = parts[-1]  # Laatste deel
        role = parts[-2]  # Voorlaatste deel
        nice_name = "_".join(parts[:-2])  # Rest is de nice name
        
        port_path = str(device_link.resolve())
        symlink_path = f"/dev/{name}"
        
        device_info = {
            "name": nice_name,
            "port": port_path,
            "symlink": symlink_path,
            "type": robot_type,
            "display_name": f"{nice_name} ({robot_type})"
        }
        
        if role == "leader":
            leaders.append(device_info)
        elif role == "follower":
            followers.append(device_info)
    
    return {"leaders": leaders, "followers": followers}


# ============================================================================
# Rate Limiting
# ============================================================================

class SimpleRateLimiter:
    """Simple rate limiter to prevent resource exhaustion."""
    def __init__(self, max_requests_per_second: int = 10, window_size: int = 60):
        self.max_requests_per_second = max_requests_per_second
        self.window_size = window_size
        self.requests = defaultdict(deque)  # IP -> deque of timestamps
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if request from this IP is allowed."""
        now = time.time()
        client_requests = self.requests[client_ip]
        
        # Remove old requests outside window
        while client_requests and client_requests[0] <= now - self.window_size:
            client_requests.popleft()
        
        # Count requests in last second
        recent_requests = sum(1 for req_time in client_requests if req_time > now - 1.0)
        
        if recent_requests >= self.max_requests_per_second:
            return False
        
        # Add current request
        client_requests.append(now)
        return True

# Global rate limiter for position requests
position_limiter = SimpleRateLimiter(max_requests_per_second=6)  # Max 6 req/sec per IP


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
        self.reconnect_count: int = 0
        self.last_reconnect_at: Optional[str] = None

        # Blockly -> teleoperation handover state
        self.blockly_resume_requested: bool = False
        self.blockly_resume_at: Optional[datetime] = None
        self.blockly_resume_task: Optional[asyncio.Task] = None
        self.blockly_resume_error: Optional[str] = None
        
        # Camera management
        self.camera_manager: Optional[CameraManager] = None
        self.cameras_enabled: bool = False
        
        # Network management
        self.network_manager: Optional[NetworkManager] = None
        self.network_enabled: bool = False
        
        # Blockly management
        self.blockly_manager: Optional[BlocklyManager] = None
        self.blockly_enabled: bool = False
        
        # Bluetooth management
        self.bluetooth_manager: Optional[BLEGattServer] = None
        self.bluetooth_enabled: bool = False
        
        # WebSocket clients
        self.websocket_clients: List[WebSocket] = []

        # Position caching to prevent excessive resource usage
        self._positions_cache: Optional[Dict[str, Any]] = None
        self._positions_cache_time: Optional[datetime] = None
        self._positions_cache_duration = timedelta(milliseconds=50)  # Cache for 50ms

        # Persisted defaults
        self.defaults_file = Path.home() / ".lerobot_device_defaults.json"
        self._load_persisted_defaults()
    
    def is_running(self) -> bool:
        """Check of teleoperation draait."""
        if self.teleop_manager is None:
            return False
        return self.teleop_manager.is_running
    
    def get_cached_positions(self) -> Optional[Dict[str, Any]]:
        """Get cached positions if still valid, otherwise return None."""
        now = datetime.now()
        if (self._positions_cache is not None and 
            self._positions_cache_time is not None and
            now - self._positions_cache_time < self._positions_cache_duration):
            return self._positions_cache
        return None
    
    def cache_positions(self, positions: Dict[str, Any]) -> None:
        """Cache positions with timestamp."""
        self._positions_cache = positions
        self._positions_cache_time = datetime.now()
    
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

        # Persisted defaults are loaded once during RobotState initialization
        # and updated explicitly by the defaults API. Do not re-read the file
        # on every 1 Hz status poll.
    
    def load_device_config(self) -> bool:
        """Laad device configuratie (fallback defaults only - JSON loading via _load_persisted_defaults)."""
        # Set defaults if not already loaded from JSON
        if not self.follower_port:
            self.follower_port = "/dev/tty_follower"
        if not self.leader_port:
            self.leader_port = "/dev/tty_leader"
        if not self.follower_type:
            self.follower_type = "so101"
        if not self.follower_id:
            self.follower_id = "default"
        if not self.leader_type:
            self.leader_type = "so101"
        if not self.leader_id:
            self.leader_id = "default"
        
        return Path(self.follower_port).exists() and Path(self.leader_port).exists()

    def _load_persisted_defaults(self):
        """Load defaults from JSON file if present"""
        try:
            if self.defaults_file.exists():
                with open(self.defaults_file, 'r') as f:
                    data = json.load(f)
                self.follower_port = data.get('follower_port', self.follower_port)
                self.follower_type = data.get('follower_type', self.follower_type)
                self.follower_id = data.get('follower_id', self.follower_id)
                self.leader_port = data.get('leader_port', self.leader_port)
                self.leader_type = data.get('leader_type', self.leader_type)
                self.leader_id = data.get('leader_id', self.leader_id)
                logger.info("Loaded device defaults from ~/.lerobot_device_defaults.json")
        except Exception as e:
            logger.error(f"Error loading device defaults: {e}")

    def save_persisted_defaults(self) -> bool:
        """Save defaults to JSON file"""
        try:
            data = {
                'follower_port': self.follower_port,
                'follower_type': self.follower_type,
                'follower_id': self.follower_id,
                'leader_port': self.leader_port,
                'leader_type': self.leader_type,
                'leader_id': self.leader_id,
            }
            with open(self.defaults_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving device defaults: {e}")
            return False


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
    sys.stdout.flush()
    sys.stderr.flush()
    
    if not state.follower_port or not state.leader_port:
        if not state.load_device_config():
            logger.error("Geen geldige device configuratie")
            return False
    
    # Get or create teleoperation manager
    logger.info("   Importing teleoperation_manager...")
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        from teleoperation_manager import get_teleoperation_manager
        teleop_manager = get_teleoperation_manager()
        logger.info("   ✅ Teleoperation manager imported")
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as import_error:
        logger.error(f"❌ Failed to import teleoperation_manager: {import_error}", exc_info=True)
        sys.stdout.flush()
        sys.stderr.flush()
        return False
    
    try:
        logger.info(f"   Follower: {state.follower_port} ({state.follower_type}/{state.follower_id})")
        logger.info(f"   Leader: {state.leader_port} ({state.leader_type}/{state.leader_id})")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Start teleoperation in-process with proper LeRobot types
        robot_type = f"{state.follower_type}_follower"
        teleop_type = f"{state.leader_type}_leader"
        
        logger.info(f"   Starting with robot_type={robot_type}, teleop_type={teleop_type}")
        sys.stdout.flush()
        sys.stderr.flush()
        
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
            sys.stdout.flush()
            sys.stderr.flush()
            return True
        else:
            logger.error("❌ Failed to start teleoperation")
            sys.stdout.flush()
            sys.stderr.flush()
            return False
        
    except Exception as e:
        logger.error(f"❌ Fout bij starten teleoperation: {e}", exc_info=True)
        sys.stdout.flush()
        sys.stderr.flush()
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

async def initialize_hardware_background():
    """Initialize cameras/network/robots after the web UI is already reachable."""
    try:
        # The HTTP/WebSocket server is already online. Give USB/network services
        # a moment to settle without delaying GUI availability.
        logger.info("⏳ Hardware initialization starts in background...")
        await asyncio.sleep(3)
        
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
                    
                    # Check for network connectivity
                    logger.info("🔍 Checking network connectivity...")
                    status = await state.network_manager.get_status()
                    
                    # If no network connection, auto-start AP
                    if status.get('state') != 'connected' and status.get('connectivity') != 'full':
                        logger.warning("⚠️  No network connection detected")
                        logger.info("📡 Auto-starting WiFi Access Point for setup...")
                        
                        try:
                            # Start AP mode
                            ap_started = await state.network_manager.start_ap()
                            if ap_started:
                                logger.info("✅ WiFi Access Point started")
                                logger.info(f"   SSID: LeRobot-AP")
                                logger.info(f"   Password: robotics123")
                                logger.info(f"   Connect and visit: http://192.168.4.1:5000")
                            else:
                                logger.error("❌ Failed to start Access Point")
                        except Exception as ap_error:
                            logger.error(f"Error starting AP: {ap_error}")
                    else:
                        logger.info(f"✅ Network connected: {status.get('ssid', 'unknown')}")
                        
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
        
        # Initialize Bluetooth GATT service
        if BLUETOOTH_AVAILABLE:
            logger.info("📡 Initializing Bluetooth GATT service...")
            try:
                bluetooth_mgr = BLEGattServer("LeRobot")
                bluetooth_mgr.start()
                state.bluetooth_manager = bluetooth_mgr
                state.bluetooth_enabled = True
                logger.info("✅ Bluetooth GATT service started")
            except Exception as e:
                logger.error(f"Error initializing Bluetooth GATT: {e}")
        
        # Initial state refresh
        state.refresh_state()
        logger.info("✅ State refreshed")
        sys.stdout.flush()
        sys.stderr.flush()
        
        if state.devices_available:
            logger.info("✅ USB devices beschikbaar")
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Auto-start teleoperation als devices beschikbaar zijn
            logger.info("🎮 Auto-start teleoperation...")
            sys.stdout.flush()
            sys.stderr.flush()
            await asyncio.sleep(2)  # Extra delay voor device stabiliteit
            
            logger.info("   Calling start_teleoperation()...")
            sys.stdout.flush()
            sys.stderr.flush()
            
            if await start_teleoperation():
                logger.info("✅ Teleoperation automatisch gestart")
                sys.stdout.flush()
                sys.stderr.flush()
            else:
                logger.warning("⚠️  Kon teleoperation niet automatisch starten")
                sys.stdout.flush()
                sys.stderr.flush()
        else:
            logger.warning("⚠️  Geen USB devices gevonden - teleoperation niet gestart")
            logger.info("   💡 Sluit devices aan en start handmatig via web interface")
            sys.stdout.flush()
            sys.stderr.flush()
        
        logger.info("Server initialization complete")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
    


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring HTTP/WebSocket online immediately; initialize hardware in background."""
    logger.info("=" * 60)
    logger.info("🌐 LeRobot Teleoperation Server")
    logger.info("✅ Web interface is available; hardware initialization continues in background")
    logger.info("=" * 60)

    initialization_task = asyncio.create_task(initialize_hardware_background())

    yield

    if not initialization_task.done():
        initialization_task.cancel()
        try:
            await initialization_task
        except asyncio.CancelledError:
            pass

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
        
        # Shutdown Bluetooth service
        if state.bluetooth_manager:
            logger.info("Shutting down Bluetooth service...")
            state.bluetooth_manager.stop()
        
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
    version="2.1.0",
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


@app.get("/bluetooth")
async def bluetooth_scanner():
    """Bluetooth scanner page - find robot IP via Web Bluetooth"""
    static_path = Path(__file__).parent / "static" / "bluetooth_scan.html"
    if static_path.exists():
        with open(static_path, 'r') as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="<h1>Bluetooth scanner not found</h1><p>Please ensure static/bluetooth_scan.html exists</p>")


@app.get("/qr")
async def qr_codes():
    """QR codes page - printable QR codes for easy access"""
    static_path = Path(__file__).parent / "static" / "qr_codes.html"
    if static_path.exists():
        with open(static_path, 'r') as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(content="<h1>QR codes page not found</h1><p>Please ensure static/qr_codes.html exists</p>")


@app.get("/ssh")
async def ssh_terminal_page():
    """Browser terminal that authenticates through the host's normal SSH daemon."""
    template_path = Path(__file__).parent / "templates" / "ssh_terminal.html"
    if template_path.exists():
        with open(template_path, 'r') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>SSH terminal template not found</h1>", status_code=404)


@app.get("/api/system/update-status")
async def system_update_status(check_remote: bool = False):
    """Inspect this checkout and optionally fetch origin to report update availability."""
    repo_dir = Path(__file__).resolve().parent

    def run_git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return result.stdout.strip()

    try:
        if check_remote:
            subprocess.run(
                ["git", "-C", str(repo_dir), "fetch", "--quiet", "--prune", "origin"],
                capture_output=True,
                text=True,
                timeout=45,
                check=True,
            )

        branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
        commit = run_git("rev-parse", "--short", "HEAD")
        dirty = bool(run_git("status", "--porcelain"))
        upstream = ""
        behind = 0
        ahead = 0

        try:
            upstream = run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            counts = run_git("rev-list", "--left-right", "--count", "HEAD...@{u}").split()
            if len(counts) == 2:
                ahead = int(counts[0])
                behind = int(counts[1])
        except Exception:
            upstream = ""

        update_command = (
            f"cd {shlex.quote(str(repo_dir))} && "
            "git pull --ff-only && "
            "./install.sh && "
            "sudo reboot"
        )

        return {
            "success": True,
            "repo_dir": str(repo_dir),
            "branch": branch,
            "commit": commit,
            "dirty": dirty,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "update_available": behind > 0,
            "update_command": update_command,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git update check timed out"}
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        return {"success": False, "error": detail}


@app.get("/api/ssh/info")
async def ssh_info(request: Request):
    """Return local SSH terminal availability. No credentials are stored by this service."""
    client_host = request.client.host if request.client else ""
    try:
        client_ip = ipaddress.ip_address(client_host)
        lan_allowed = client_ip.is_private or client_ip.is_loopback
    except ValueError:
        lan_allowed = False

    return {
        "enabled": os.environ.get("LEROBOT_WEB_SSH", "1") != "0",
        "lan_allowed": lan_allowed,
        "ssh_client_available": shutil.which("ssh") is not None,
        "hostname": socket.gethostname(),
        "default_user": getpass.getuser(),
        "target": "127.0.0.1",
    }


@app.get("/api")
async def api_info():
    """API information"""
    return {
        "name": "LeRobot Teleoperation Server",
        "version": "2.1.0",
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
            "/api/devices": "Get available robot and teleop devices",
        }
    }


@app.get("/api/devices")
async def get_devices():
    """Get available robot and teleoperator devices"""
    try:
        devices = scan_devices()
        return {
            "success": True,
            "leaders": devices["leaders"],
            "followers": devices["followers"],
            "count": {
                "leaders": len(devices["leaders"]),
                "followers": len(devices["followers"])
            }
        }
    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
        return {
            "success": False,
            "error": str(e),
            "leaders": [],
            "followers": [],
            "count": {"leaders": 0, "followers": 0}
        }
@app.get("/api/devices/defaults")
async def get_device_defaults():
    """Get persisted default leader/follower selection"""
    return {
        'success': True,
        'follower_port': state.follower_port,
        'follower_type': state.follower_type,
        'follower_id': state.follower_id,
        'leader_port': state.leader_port,
        'leader_type': state.leader_type,
        'leader_id': state.leader_id,
    }

@app.post("/api/devices/defaults")
async def set_device_defaults(request: Request):
    """Persist selected leader/follower as defaults"""
    try:
        body = await request.json()
        state.follower_port = body.get('follower_port', state.follower_port)
        state.follower_type = body.get('follower_type', state.follower_type)
        state.follower_id = body.get('follower_id', state.follower_id)
        state.leader_port = body.get('leader_port', state.leader_port)
        state.leader_type = body.get('leader_type', state.leader_type)
        state.leader_id = body.get('leader_id', state.leader_id)
        saved_json = state.save_persisted_defaults()

        # Reinitialize Blockly manager to use the updated follower selection
        try:
            if BLOCKLY_AVAILABLE:
                logger.info("🔄 Reinitializing Blockly manager with new follower defaults...")
                robot_port = state.follower_port if state.follower_port else None
                robot_type = state.follower_type if state.follower_type else None
                robot_id = state.follower_id if state.follower_id else None
                state.blockly_manager = BlocklyManager(
                    robot_port=robot_port,
                    robot_type=robot_type,
                    robot_id=robot_id
                )
                state.blockly_enabled = True
                logger.info(f"✅ Blockly now bound to follower: port={robot_port}, type={robot_type}, id={robot_id}")
        except Exception as e:
            logger.error(f"Error reinitializing Blockly after defaults change: {e}")

        return {
            'success': saved_json,
            'message': 'Defaults saved' if saved_json else 'Failed to save defaults'
        }
    except Exception as e:
        logger.error(f"Error setting device defaults: {e}")
        return {
            'success': False,
            'message': str(e)
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
    
    teleop_status = state.teleop_manager.get_status() if state.teleop_manager else {}
    return {
        "running": state.is_running(),
        "mode": state.teleop_mode,
        "connection_state": teleop_status.get("connection_state", "stopped"),
        "target_fps": teleop_status.get("target_fps", 60),
        "actual_fps": teleop_status.get("actual_fps", 0.0),
        "processing_ms": teleop_status.get("processing_ms", 0.0),
        "loop_errors": teleop_status.get("loop_errors", 0),
        "last_error": teleop_status.get("last_error"),
        "uptime_s": teleop_status.get("uptime_s", 0.0),
        "reconnect_count": state.reconnect_count,
        "last_reconnect_at": state.last_reconnect_at,
        "devices_available": state.devices_available,
        "follower_port": state.follower_port,
        "leader_port": state.leader_port,
        "follower_type": state.follower_type,
        "leader_type": state.leader_type,
        "follower_id": state.follower_id,
        "leader_id": state.leader_id,
    }


@app.get("/api/logs")
async def get_logs(after: int = 0, limit: int = 200):
    """Return recent server/robot logs for GUI backlog or fallback polling."""
    logs = get_gui_logs_since(after_seq=max(0, after), limit=limit)
    latest_seq = logs[-1]["seq"] if logs else max(0, after)
    return {
        "logs": logs,
        "latest_seq": latest_seq,
    }


@app.post("/api/teleoperation/start")
async def api_start_teleoperation(request: Request):
    """Start teleoperation with optional device selection"""
    try:
        # Try to get device config from request body
        body = await request.json()
        
        # Override state with selected devices if provided
        if body:
            if 'follower_port' in body:
                state.follower_port = body['follower_port']
            if 'follower_type' in body:
                state.follower_type = body['follower_type']
            if 'follower_id' in body:
                state.follower_id = body['follower_id']
            if 'leader_port' in body:
                state.leader_port = body['leader_port']
            if 'leader_type' in body:
                state.leader_type = body['leader_type']
            if 'leader_id' in body:
                state.leader_id = body['leader_id']
            
            logger.info(f"Starting teleoperation with selected devices:")
            logger.info(f"  Follower: {state.follower_type} @ {state.follower_port} (ID: {state.follower_id})")
            logger.info(f"  Leader: {state.leader_type} @ {state.leader_port} (ID: {state.leader_id})")
    except:
        # No body or invalid JSON - use default config
        pass
    
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


@app.post("/api/teleoperation/reconnect")
async def api_reconnect_teleoperation():
    """Explicit operator-triggered reconnect using the current device selection."""
    logger.info("🔄 Manual teleoperation reconnect requested")
    state.reconnect_count += 1
    state.last_reconnect_at = datetime.now().astimezone().isoformat(timespec="seconds")

    # Always clean up stale objects, including a manager whose loop entered error state.
    if state.teleop_manager is not None:
        try:
            state.teleop_manager.stop()
        except Exception as e:
            logger.warning(f"Cleanup before reconnect failed: {e}")
        state.teleop_manager = None
        state.teleop_mode = "stopped"

    await asyncio.sleep(0.5)
    success = await start_teleoperation()
    return {
        "success": success,
        "message": "Teleoperation reconnected" if success else "Reconnect failed",
        "reconnect_count": state.reconnect_count,
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
        
        # Build motor_names and positions with consistent ordering
        desired_order = [
            'shoulder_pan',
            'shoulder_lift',
            'elbow_flex',
            'wrist_flex',
            'wrist_roll',
            'gripper'
        ]
        motor_names = []
        positions = []
        # Add values in desired order when present
        for base in desired_order:
            key = base if base in positions_dict else (f"{base}.pos" if f"{base}.pos" in positions_dict else None)
            if key is not None:
                motor_names.append(base)
                positions.append(positions_dict[key])
        # Append any remaining keys preserving original order
        for k in positions_dict.keys():
            base = k.replace('.pos', '')
            if base not in motor_names:
                motor_names.append(base)
                positions.append(positions_dict[k])
        
        return {
            "success": True,
            "positions": positions,
            "motor_names": motor_names,
            "source": "teleoperation",
            "unit": "degrees"
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
        
        # Use consistent ordering for saving
        desired_order = [
            'shoulder_pan',
            'shoulder_lift',
            'elbow_flex',
            'wrist_flex',
            'wrist_roll',
            'gripper'
        ]
        motor_names = []
        positions = []
        for base in desired_order:
            key = base if base in positions_dict else (f"{base}.pos" if f"{base}.pos" in positions_dict else None)
            if key is not None:
                motor_names.append(base)
                positions.append(positions_dict[key])
        # Append any remaining keys preserving original order
        for k in positions_dict.keys():
            base = k.replace('.pos', '')
            if base not in motor_names:
                motor_names.append(base)
                positions.append(positions_dict[k])
        
        # Save to Blockly manager if available
        if state.blockly_manager:
            # Convert to format expected by Blockly (6 values array)
            position_array = positions[:6] if len(positions) >= 6 else positions
            state.blockly_manager.save_position(name, position_array, description)
        
        return {
            "success": True,
            "message": f"Position '{name}' saved successfully",
            "angles": positions,
            "motor_names": motor_names,
            "unit": "degrees"
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
# Bluetooth API Endpoints
# ============================================================================

@app.get("/api/bluetooth/status")
async def bluetooth_status():
    """Get Bluetooth GATT service status"""
    if not BLUETOOTH_AVAILABLE:
        return {
            "available": False,
            "running": False,
            "message": "Bluetooth not available (dbus-next not installed)"
        }
    
    if not state.bluetooth_enabled or not state.bluetooth_manager:
        return {
            "available": True,
            "running": False,
            "service_name": "LeRobot",
            "message": "Bluetooth GATT service not initialized"
        }
    
    return {
        "available": True,
        "running": state.bluetooth_manager.running,
        "service_name": state.bluetooth_manager.device_name,
        "ip_address": state.bluetooth_manager.get_local_ip(),
        "message": "Bluetooth GATT service running" if state.bluetooth_manager.running else "Stopped"
    }


@app.get("/api/bluetooth/ip")
async def bluetooth_get_ip():
    """Get current IP address(es) - for Bluetooth clients"""
    if not state.bluetooth_manager:
        # Fallback: use socket to get IP even if Bluetooth not available
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return {
                "primary_ip": ip,
                "all_ips": {"default": ip}
            }
        except Exception as e:
            return {
                "primary_ip": "No IP",
                "all_ips": {},
                "error": str(e)
            }
    
    return {
        "primary_ip": state.bluetooth_manager.get_local_ip()
    }


@app.post("/api/bluetooth/start")
async def bluetooth_start():
    """Start Bluetooth service"""
    if not BLUETOOTH_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bluetooth not available (dbus-next not installed)")
    
    if state.bluetooth_enabled and state.bluetooth_manager and state.bluetooth_manager.running:
        return {
            "success": True,
            "message": "Bluetooth GATT service already running"
        }
    
    try:
        bluetooth_mgr = BLEGattServer("LeRobot")
        bluetooth_mgr.start()
        state.bluetooth_manager = bluetooth_mgr
        state.bluetooth_enabled = True
        return {
            "success": True,
            "message": "Bluetooth GATT service started"
        }
    except Exception as e:
        logger.error(f"Error starting Bluetooth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bluetooth/stop")
async def bluetooth_stop():
    """Stop Bluetooth service"""
    if not state.bluetooth_enabled or not state.bluetooth_manager:
        return {
            "success": True,
            "message": "Bluetooth service not running"
        }
    
    try:
        state.bluetooth_manager.stop()
        return {
            "success": True,
            "message": "Bluetooth service stopped"
        }
    except Exception as e:
        logger.error(f"Error stopping Bluetooth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


async def _resume_teleoperation_after_blockly(delay_s: float):
    """Resume teleoperation after a visible Blockly handover delay."""
    try:
        await asyncio.sleep(delay_s)

        if not state.blockly_resume_requested:
            return

        logger.info("Blockly handover countdown complete; restarting teleoperation...")
        started = await start_teleoperation()
        if started:
            state.blockly_resume_error = None
            logger.info("✅ Teleoperation resumed after Blockly")
        else:
            state.blockly_resume_error = "Teleoperation failed to restart after Blockly"
            logger.error(state.blockly_resume_error)
    except asyncio.CancelledError:
        logger.info("Blockly teleoperation resume cancelled")
        raise
    except Exception as e:
        logger.error(f"Failed to resume teleoperation after Blockly: {e}", exc_info=True)
    finally:
        state.blockly_resume_requested = False
        state.blockly_resume_at = None
        state.blockly_resume_task = None


@app.get("/api/blockly/status")
async def get_blockly_status():
    """Return Blockly handover status so the GUI can show/recover the countdown."""
    resume_in_s = 0.0
    if state.blockly_resume_requested and state.blockly_resume_at:
        resume_in_s = max(
            0.0,
            (state.blockly_resume_at - datetime.now()).total_seconds(),
        )

    return {
        "resume_pending": state.blockly_resume_requested,
        "resume_in_s": resume_in_s,
        "teleoperation_running": state.is_running(),
        "resume_error": state.blockly_resume_error,
    }


@app.post("/api/blockly/cancel-resume")
async def cancel_blockly_resume():
    """Keep teleoperation stopped instead of automatically resuming it."""
    state.blockly_resume_requested = False
    state.blockly_resume_at = None
    state.blockly_resume_error = None

    if state.blockly_resume_task and not state.blockly_resume_task.done():
        state.blockly_resume_task.cancel()
    state.blockly_resume_task = None

    logger.info("Blockly automatic teleoperation resume cancelled by operator")
    return {
        "success": True,
        "message": "Teleoperation will remain stopped",
    }


@app.post("/api/blockly/execute")
async def execute_code(execution: BlocklyExecute):
    """Execute Blockly-generated Python code."""
    if not state.blockly_enabled or not state.blockly_manager:
        raise HTTPException(status_code=503, detail="Blockly not available")

    # Preserve an already pending handover if a second Blockly program is
    # started during the countdown.
    resume_teleop_afterwards = state.is_running() or state.blockly_resume_requested

    if state.blockly_resume_task and not state.blockly_resume_task.done():
        state.blockly_resume_task.cancel()
    state.blockly_resume_task = None
    state.blockly_resume_requested = False
    state.blockly_resume_at = None
    state.blockly_resume_error = None

    # Blockly needs exclusive access to the follower serial port.
    if state.is_running():
        logger.info("Stopping teleoperation for Blockly execution...")
        await stop_teleoperation()

        logger.info("Waiting for serial port to be released...")
        await asyncio.sleep(5.0)
        logger.info("Port should now be available")

    resume_delay_s = 5.0 if resume_teleop_afterwards else 0.0

    try:
        logger.info("Initializing robot for Blockly...")
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            state.blockly_manager.robot_api._initialize_robot()

            if state.blockly_manager.robot_api.robot:
                logger.info(f"✅ Robot connected successfully on attempt {attempt + 1}")
                break

            if attempt < max_retries - 1:
                logger.warning(
                    f"⚠️ Connection attempt {attempt + 1} failed, "
                    f"waiting {retry_delay}s before retry..."
                )
                await asyncio.sleep(retry_delay)
                retry_delay += 1.0

        if not state.blockly_manager.robot_api.robot:
            raise HTTPException(
                status_code=503,
                detail="Could not connect to robot after 3 attempts. Hardware may need more time to reset.",
            )

        result = await state.blockly_manager.execute_python_code(
            execution.code,
            execution.timeout,
        )
        result["teleop_will_resume"] = resume_teleop_afterwards
        result["teleop_resume_delay_s"] = resume_delay_s
        return result

    finally:
        logger.info("Disconnecting robot after Blockly execution...")
        state.blockly_manager.robot_api.disconnect()

        if resume_teleop_afterwards:
            # Return control to the browser immediately and perform the old
            # automatic handover after a visible, cancellable countdown.
            state.blockly_resume_requested = True
            state.blockly_resume_at = datetime.now() + timedelta(seconds=resume_delay_s)
            state.blockly_resume_task = asyncio.create_task(
                _resume_teleoperation_after_blockly(resume_delay_s)
            )
            logger.info(
                f"Teleoperation will resume in {int(resume_delay_s)} seconds "
                "unless cancelled by the operator"
            )


@app.post("/api/teleoperation/leader/command")
async def teleop_leader_command(request: Request):
    """Accept leader commands in degrees and forward them to the follower.

    Payload: { motor_names: [...], positions: [...] }
    All six motors, including the gripper, use degrees.
    """
    if not state.teleop_manager or not state.teleop_manager.is_running:
        return { "success": False, "error": "Teleoperation not running" }

    try:
        body = await request.json()
        motor_names = body.get('motor_names') or []
        positions = body.get('positions') or []
        if not isinstance(motor_names, list) or not isinstance(positions, list) or len(motor_names) != len(positions):
            return { "success": False, "error": "Invalid payload" }

        # Build a dict for the teleop manager, accept either base or `.pos` keys
        cmd = {}
        for i, name in enumerate(motor_names):
            base = str(name).replace('.pos', '')
            val = float(positions[i])
            cmd[base] = val
            cmd[f"{base}.pos"] = val

        # Forward to teleoperation manager if it supports a handler
        handler = None
        if hasattr(state.teleop_manager, 'apply_leader_positions'):
            handler = state.teleop_manager.apply_leader_positions
        elif hasattr(state.teleop_manager, 'set_target_positions'):
            handler = state.teleop_manager.set_target_positions
        elif hasattr(state.teleop_manager, 'update_positions'):
            handler = state.teleop_manager.update_positions

        if handler:
            handler(cmd)
            return { "success": True }
        else:
            # Fallback: store on teleop manager for polling loop to consume if implemented
            setattr(state.teleop_manager, 'leader_positions', cmd)
            return { "success": True, "message": "Stored leader positions (no direct handler)" }

    except Exception as e:
        logger.error(f"Leader command error: {e}")
        return { "success": False, "error": str(e) }


@app.get("/api/robot/positions")
async def get_robot_positions(request: Request):
    """Get current robot joint positions from teleoperation or Blockly"""
    
    # Rate limiting to prevent resource exhaustion
    client_ip = request.client.host if request.client else "unknown"
    if not position_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests - rate limited")
    
    try:
        # Check cache first to reduce resource usage
        cached_positions = state.get_cached_positions()
        if cached_positions is not None:
            return cached_positions
        
        # Try teleoperation manager first (if running)
        if state.is_running():
            try:
                teleop_manager = state.teleop_manager
                if teleop_manager is None:
                    raise HTTPException(status_code=503, detail="Teleoperation manager not initialized")
                    
                positions_dict = teleop_manager.get_current_positions()
                
                if positions_dict:
                    # Build motor_names and positions with consistent ordering
                    desired_order = [
                        'shoulder_pan',
                        'shoulder_lift',
                        'elbow_flex',
                        'wrist_flex',
                        'wrist_roll',
                        'gripper'
                    ]
                    motor_names = []
                    positions = []
                    for base in desired_order:
                        key = base if base in positions_dict else (f"{base}.pos" if f"{base}.pos" in positions_dict else None)
                        if key is not None:
                            motor_names.append(base)
                            positions.append(positions_dict[key])
                    # Append any remaining keys preserving original order
                    for k in positions_dict.keys():
                        base = k.replace('.pos', '')
                        if base not in motor_names:
                            motor_names.append(base)
                            positions.append(positions_dict[k])
                    
                    result = {
                        "success": True,
                        "positions": positions,
                        "motor_names": motor_names,
                        "source": "teleoperation",
                        "unit": "degrees"
                    }
                    state.cache_positions(result)
                    return result
            except Exception as e:
                logger.debug(f"Could not get positions from teleoperation: {e}")
        
        # Fallback to Blockly robot API
        if not state.blockly_enabled or not state.blockly_manager:
            raise HTTPException(status_code=503, detail="Robot not available")
        
        try:
            positions = state.blockly_manager.robot_api.read_all_positions()
            result = {
                "success": True,
                "positions": positions,
                "joint_names": [
                    "shoulder_pan",
                    "shoulder_lift", 
                    "elbow_flex",
                    "wrist_flex",
                    "wrist_roll",
                    "gripper"
                ],
                "source": "blockly",
                "unit": "degrees"
            }
            state.cache_positions(result)
            return result
        except Exception as e:
            logger.error(f"Error reading robot positions: {e}")
            return {
                "success": False,
                "error": str(e),
                "positions": [0.0] * 6
            }
    except Exception as e:
        logger.error(f"Unexpected error in get_robot_positions: {e}")
        return {
            "success": False,
            "error": "Internal server error",
            "positions": [0.0] * 6
        }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

def _web_ssh_client_allowed(websocket: WebSocket) -> bool:
    if os.environ.get("LEROBOT_WEB_SSH", "1") == "0":
        return False
    client_host = websocket.client.host if websocket.client else ""
    try:
        client_ip = ipaddress.ip_address(client_host)
        return client_ip.is_private or client_ip.is_loopback
    except ValueError:
        return False


@app.websocket("/ws/ssh")
async def ssh_websocket_endpoint(websocket: WebSocket):
    """LAN-only browser SSH session to this same host via its normal sshd authentication."""
    if not _web_ssh_client_allowed(websocket):
        await websocket.close(code=1008, reason="Web SSH is limited to LAN/localhost clients")
        return
    if shutil.which("ssh") is None:
        await websocket.close(code=1011, reason="ssh client not installed")
        return

    user = websocket.query_params.get("user", getpass.getuser()).strip()
    if not user or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in user):
        await websocket.close(code=1008, reason="Invalid SSH username")
        return

    await websocket.accept()
    pid = None
    master_fd = None

    try:
        pid, master_fd = os.forkpty()
        if pid == 0:
            os.execvp("ssh", [
                "ssh",
                "-tt",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ServerAliveInterval=30",
                "-o", "ConnectTimeout=10",
                f"{user}@127.0.0.1",
            ])

        os.set_blocking(master_fd, False)
        logger.info(f"💻 Web SSH session opened for {user} from {websocket.client.host}")

        while True:
            # Forward browser keystrokes to the PTY.
            try:
                incoming = await asyncio.wait_for(websocket.receive_text(), timeout=0.03)
                if incoming:
                    os.write(master_fd, incoming.encode("utf-8", errors="ignore"))
            except asyncio.TimeoutError:
                pass

            # Forward SSH output to the browser terminal.
            try:
                output = os.read(master_fd, 8192)
                if output:
                    await websocket.send_text(output.decode("utf-8", errors="replace"))
                else:
                    break
            except BlockingIOError:
                pass
            except OSError:
                break

            # Reap child when the SSH session exits.
            done_pid, _ = os.waitpid(pid, os.WNOHANG)
            if done_pid == pid:
                pid = None
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Web SSH session error: {e}")
    finally:
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass
        if pid:
            try:
                os.kill(pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
        logger.info("💻 Web SSH session closed")


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

        # Send buffered startup/runtime logs so a newly opened GUI still shows
        # what happened before the browser connected.
        initial_logs = get_gui_logs_since(after_seq=0, limit=200)
        last_log_seq = initial_logs[-1]["seq"] if initial_logs else 0
        if initial_logs:
            await websocket.send_json({"type": "logs", "data": initial_logs})

        async def stream_logs():
            """Push newly captured log records without blocking WebSocket input."""
            nonlocal last_log_seq
            while True:
                new_logs = get_gui_logs_since(after_seq=last_log_seq, limit=100)
                if new_logs:
                    await websocket.send_json({"type": "logs", "data": new_logs})
                    last_log_seq = new_logs[-1]["seq"]
                await asyncio.sleep(0.25)

        log_stream_task = asyncio.create_task(stream_logs())

        # Keep connection alive and handle incoming messages.
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    # Echo back for ping/pong
                    await websocket.send_json({"type": "pong", "timestamp": time.time()})
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
        finally:
            log_stream_task.cancel()
            try:
                await log_stream_task
            except asyncio.CancelledError:
                pass
                
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

    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000
        logging.getLogger(__name__).warning("Invalid PORT env var, falling back to 5000")
    
    # Add flushing handler to uvicorn loggers so their output also gets flushed
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        uv_logger = logging.getLogger(logger_name)
        uv_logger.addHandler(flushing_handler)
    
    # Run with standard uvicorn logging
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
