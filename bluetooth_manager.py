#!/usr/bin/env python3
"""
Bluetooth Manager for LeRobot
Provides BLE GATT service to advertise device IP address via Bluetooth
"""

import asyncio
import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Check if dependencies are available
try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, dbus_property
    from dbus_next import Variant
    from dbus_next.constants import BusType
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.info("dbus-next not available - Install with: pip install dbus-next")

try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False
    logger.info("netifaces not available (optional)")


class BluetoothManager:
    """Manages BLE GATT service to advertise IP address"""
    
    def __init__(self, service_name: str = "LeRobot-IP"):
        """
        Initialize Bluetooth Manager
        
        Args:
            service_name: Name for the BLE advertised device name
        """
        self.service_name = service_name
        self.running = False
        self.loop = None
        self.thread = None
        
        if not DBUS_AVAILABLE:
            logger.warning("D-Bus not available. BLE advertising disabled.")
            logger.info("Install with: pip install dbus-next")
    
    def get_local_ip(self) -> str:
        """
        Get the local IP address of the device
        
        Returns:
            str: Local IP address or 'No IP' if not connected
        """
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public DNS server (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"Error getting local IP: {e}")
            # Fallback: try to get IP from hostname
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip.startswith("127."):
                    return "No IP"
                return ip
            except:
                return "No IP"
    
    def get_all_ips(self) -> dict:
        """
        Get all network interfaces and their IP addresses
        
        Returns:
            dict: Dictionary of interface names and IP addresses
        """
        ips = {}
        if NETIFACES_AVAILABLE:
            try:
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            if not ip.startswith('127.'):
                                ips[interface] = ip
            except Exception as e:
                logger.error(f"Error getting all IPs: {e}")
                ips['default'] = self.get_local_ip()
        else:
            # Fallback if netifaces not available
            ips['default'] = self.get_local_ip()
        
        return ips
    
    async def run_ble_advertiser(self):
        """Run BLE advertiser with IP address in device name"""
        if not DBUS_AVAILABLE:
            logger.error("Cannot start BLE advertiser: dbus-next not available")
            return
        
        try:
            # Get current IP
            ip = self.get_local_ip()
            device_name = f"{self.service_name}-{ip}"
            
            logger.info(f"Starting BLE advertiser: {device_name}")
            logger.info("Note: Requires bluetoothd running with --experimental flag")
            
            # Connect to system bus
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            
            # Simple approach: Use bluetoothctl to set device name
            # The IP will be visible in the device name when scanning
            import subprocess
            try:
                # Set discoverable name
                subprocess.run(['bluetoothctl', 'system-alias', device_name], 
                             check=False, capture_output=True)
                subprocess.run(['bluetoothctl', 'discoverable', 'on'], 
                             check=False, capture_output=True)
                
                logger.info(f"✅ BLE device discoverable as: {device_name}")
                logger.info("Scan for Bluetooth devices to see IP address in device name")
                
            except Exception as e:
                logger.error(f"Error configuring Bluetooth: {e}")
            
            # Keep running
            self.running = True
            while self.running:
                await asyncio.sleep(10)
                # Update IP if changed
                new_ip = self.get_local_ip()
                if new_ip != ip:
                    ip = new_ip
                    device_name = f"{self.service_name}-{ip}"
                    try:
                        subprocess.run(['bluetoothctl', 'system-alias', device_name],
                                     check=False, capture_output=True)
                        logger.info(f"Updated BLE device name: {device_name}")
                    except:
                        pass
            
            # Cleanup
            try:
                subprocess.run(['bluetoothctl', 'discoverable', 'off'],
                             check=False, capture_output=True)
            except:
                pass
                
        except Exception as e:
            logger.error(f"BLE advertiser error: {e}")
            self.running = False
    
    def _run_async_loop(self):
        """Run async event loop in background thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.run_ble_advertiser())
        except Exception as e:
            logger.error(f"Error in BLE loop: {e}")
        finally:
            self.loop.close()
    
    def start(self):
        """Start the BLE advertising service"""
        if self.running:
            logger.warning("BLE service already running")
            return True
        
        if not DBUS_AVAILABLE:
            logger.warning("BLE service not started: dbus-next not available")
            logger.info("IP address still available via HTTP API")
            self.running = True  # Mark as "running" for HTTP API
            return False
        
        # Start async loop in background thread
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        
        logger.info("BLE advertising service started")
        logger.info(f"Device will be discoverable as: {self.service_name}-<IP>")
        return True
    
    def stop(self):
        """Stop the BLE advertising service"""
        logger.info("Stopping BLE service...")
        self.running = False
        
        if self.loop and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except:
                pass
        
        # Turn off discoverable
        try:
            import subprocess
            subprocess.run(['bluetoothctl', 'discoverable', 'off'],
                         check=False, capture_output=True)
        except:
            pass
        
        logger.info("BLE service stopped")
    
    def is_running(self) -> bool:
        """Check if the Bluetooth service is running"""
        return self.running
    
    def get_status(self) -> dict:
        """Get service status"""
        return {
            "running": self.running,
            "available": DBUS_AVAILABLE,
            "dbus_available": DBUS_AVAILABLE,
            "service_name": self.service_name,
            "current_ip": self.get_local_ip(),
            "all_ips": self.get_all_ips(),
            "ble_device_name": f"{self.service_name}-{self.get_local_ip()}",
            "note": "Scan for Bluetooth devices to see IP in device name. HTTP API also available at /api/bluetooth/ip"
        }


# Singleton instance
_bluetooth_manager = None

def get_bluetooth_manager() -> Optional[BluetoothManager]:
    """Get or create the Bluetooth manager singleton"""
    global _bluetooth_manager
    if _bluetooth_manager is None:
        _bluetooth_manager = BluetoothManager()
    return _bluetooth_manager
