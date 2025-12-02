"""
Camera Manager for LeRobot Teleoperation
Handles camera streaming and capture with MJPEG support
"""

import cv2
import asyncio
import logging
from typing import Dict, Any, Optional, List
import numpy as np
from threading import Thread, Lock
import time

logger = logging.getLogger(__name__)


class CameraStream:
    """Manages a single camera stream"""

    def __init__(self, index: int, name: str, resolution: tuple = (640, 480), fps: int = 30):
        self.index = index
        self.name = name
        self.resolution = resolution
        self.fps = fps
        self.capture: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[np.ndarray] = None
        self.is_running = False
        self.lock = Lock()
        self.thread: Optional[Thread] = None
        self.last_frame_time = 0
        self.frame_count = 0
        self.error_count = 0

    def start(self) -> bool:
        """Start camera capture"""
        try:
            logger.info(f"Starting camera {self.name} (index {self.index})")

            self.capture = cv2.VideoCapture(self.index)

            if not self.capture.isOpened():
                logger.error(f"Failed to open camera {self.index}")
                return False

            # Set resolution
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.capture.set(cv2.CAP_PROP_FPS, self.fps)

            # Verify settings
            actual_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self.capture.get(cv2.CAP_PROP_FPS))

            logger.info(f"Camera {self.name} configured: {actual_width}x{actual_height} @ {actual_fps} FPS")

            self.is_running = True
            self.thread = Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

            return True

        except Exception as e:
            logger.error(f"Error starting camera {self.name}: {e}")
            return False

    def stop(self):
        """Stop camera capture"""
        logger.info(f"Stopping camera {self.name}")
        self.is_running = False

        if self.thread:
            self.thread.join(timeout=2.0)

        if self.capture:
            self.capture.release()
            self.capture = None

        logger.info(f"Camera {self.name} stopped")

    def _capture_loop(self):
        """Main capture loop running in thread"""
        while self.is_running:
            try:
                ret, frame = self.capture.read()

                if ret:
                    with self.lock:
                        self.current_frame = frame
                        self.frame_count += 1
                        self.last_frame_time = time.time()
                    self.error_count = 0
                else:
                    self.error_count += 1
                    if self.error_count > 10:
                        logger.error(f"Camera {self.name} failed to read frame 10 times")
                        self.is_running = False
                        break

                # Control frame rate
                time.sleep(1.0 / self.fps)

            except Exception as e:
                logger.error(f"Error in capture loop for {self.name}: {e}")
                self.error_count += 1
                if self.error_count > 10:
                    self.is_running = False
                    break
                time.sleep(0.1)

    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame (thread-safe)"""
        with self.lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def get_jpeg_frame(self, quality: int = 85) -> Optional[bytes]:
        """Get current frame as JPEG bytes"""
        frame = self.get_frame()
        if frame is None:
            return None

        try:
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            return jpeg.tobytes()
        except Exception as e:
            logger.error(f"Error encoding JPEG for {self.name}: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get camera statistics"""
        return {
            'name': self.name,
            'index': self.index,
            'is_running': self.is_running,
            'resolution': self.resolution,
            'fps': self.fps,
            'frame_count': self.frame_count,
            'last_frame_time': self.last_frame_time,
            'error_count': self.error_count
        }


class CameraManager:
    """Manages multiple camera streams"""

    def __init__(self, camera_config: List[Dict[str, Any]]):
        """
        Initialize camera manager
        
        Args:
            camera_config: List of camera configurations
                [{'index': 0, 'name': 'Camera 0', 'resolution': [640, 480], 'fps': 30}, ...]
        """
        self.cameras: Dict[str, CameraStream] = {}
        self.camera_config = camera_config

    async def initialize(self) -> bool:
        """Initialize all cameras"""
        try:
            logger.info(f"Initializing {len(self.camera_config)} cameras...")

            for cam_config in self.camera_config:
                index = cam_config['index']
                name = cam_config.get('name', f'Camera {index}')
                resolution = tuple(cam_config.get('resolution', [640, 480]))
                fps = cam_config.get('fps', 30)

                camera = CameraStream(index, name, resolution, fps)
                
                # Start in separate task to avoid blocking
                if camera.start():
                    self.cameras[name] = camera
                    logger.info(f"✓ Camera {name} initialized")
                else:
                    logger.warning(f"✗ Failed to initialize camera {name}")

            logger.info(f"Camera initialization complete: {len(self.cameras)} cameras active")
            return len(self.cameras) > 0

        except Exception as e:
            logger.error(f"Error initializing cameras: {e}")
            return False

    async def shutdown(self):
        """Shutdown all cameras"""
        logger.info("Shutting down cameras...")
        for camera in self.cameras.values():
            camera.stop()
        self.cameras.clear()
        logger.info("All cameras stopped")

    def get_camera(self, name: str) -> Optional[CameraStream]:
        """Get camera by name"""
        return self.cameras.get(name)

    def get_camera_names(self) -> List[str]:
        """Get list of available camera names"""
        return list(self.cameras.keys())

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all cameras"""
        return {name: camera.get_stats() for name, camera in self.cameras.items()}


def generate_mjpeg_stream(camera: CameraStream, quality: int = 85):
    """
    Generate MJPEG stream for camera
    
    Args:
        camera: CameraStream instance
        quality: JPEG quality (0-100)
        
    Yields:
        MJPEG frame data
    """
    while camera.is_running:
        jpeg_data = camera.get_jpeg_frame(quality)
        
        if jpeg_data:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg_data + b'\r\n')
        else:
            # No frame available, wait a bit
            time.sleep(0.1)


async def detect_cameras(max_index: int = 10) -> List[int]:
    """
    Detect available cameras
    
    Args:
        max_index: Maximum camera index to check
        
    Returns:
        List of available camera indices
    """
    available = []
    
    logger.info(f"Detecting cameras (checking indices 0-{max_index})...")
    
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
                logger.info(f"✓ Camera found at index {i}")
            cap.release()
    
    logger.info(f"Camera detection complete: {len(available)} cameras found")
    return available
