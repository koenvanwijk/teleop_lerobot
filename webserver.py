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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
        self.teleop_process: Optional[subprocess.Popen] = None
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
        
        # WebSocket clients
        self.websocket_clients: List[WebSocket] = []
    
    def is_running(self) -> bool:
        """Check of teleoperation proces draait."""
        if self.teleop_process is None:
            return False
        return self.teleop_process.poll() is None
    
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


# ============================================================================
# Teleoperation Functions
# ============================================================================

async def start_teleoperation() -> bool:
    """Start LeRobot teleoperation."""
    if state.is_running():
        logger.warning("Teleoperation draait al")
        return False
    
    logger.info("🎮 Start teleoperation...")
    
    if not state.follower_port or not state.leader_port:
        if not state.load_device_config():
            logger.error("Geen geldige device configuratie")
            return False
    
    # Copy config values
    follower_port = state.follower_port
    leader_port = state.leader_port
    follower_type = state.follower_type
    leader_type = state.leader_type
    follower_id = state.follower_id
    leader_id = state.leader_id
    
    # Build command - use conda run (works in subprocess)
    cmd = [
        "conda", "run", "-n", "lerobot", "--no-capture-output",
        "lerobot-teleoperate",
        f"--robot.type={follower_type}_follower",
        f"--robot.port={follower_port}",
        f"--robot.id={follower_id}",
        f"--teleop.type={leader_type}_leader",
        f"--teleop.port={leader_port}",
        f"--teleop.id={leader_id}"
    ]
    
    try:
        logger.info(f"   Follower: {follower_port} ({follower_type})")
        logger.info(f"   Leader: {leader_port} ({leader_type})")
        
        teleop_log_file = Path.home() / "teleoperation.log"
        logger.info(f"   Output → {teleop_log_file}")
        
        # Open log file in append mode (blijft open voor subprocess)
        log_file = open(teleop_log_file, 'a')
        log_file.write("\n" + "=" * 60 + "\n")
        log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting teleoperation\n")
        log_file.write(f"Follower: {follower_port} ({follower_type}/{follower_id})\n")
        log_file.write(f"Leader: {leader_port} ({leader_type}/{leader_id})\n")
        log_file.write("=" * 60 + "\n")
        log_file.flush()
        
        # Start subprocess
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Update state
        state.teleop_process = process
        state.teleop_mode = "teleoperation"
        
        logger.info(f"✅ Teleoperation gestart (PID: {process.pid})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Fout bij starten teleoperation: {e}", exc_info=True)
        state.teleop_process = None
        state.teleop_mode = "stopped"
        return False


async def stop_teleoperation() -> bool:
    """Stop het teleoperation proces."""
    if not state.is_running():
        logger.warning("Teleoperation draait niet")
        state.teleop_mode = "stopped"
        return False
    
    logger.info("🛑 Stop teleoperation...")
    
    try:
        state.teleop_process.terminate()
        
        for _ in range(50):
            if state.teleop_process.poll() is not None:
                break
            await asyncio.sleep(0.1)
        
        if state.teleop_process.poll() is None:
            logger.warning("Process reageert niet, force kill...")
            state.teleop_process.kill()
            state.teleop_process.wait()
        
        logger.info("✅ Teleoperation gestopt")
        state.teleop_process = None
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
        "pid": state.teleop_process.pid if state.is_running() else None,
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
