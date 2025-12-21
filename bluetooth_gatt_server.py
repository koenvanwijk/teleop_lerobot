#!/usr/bin/env python3
"""
BLE GATT Server for LeRobot IP Broadcasting
Based on Pybricks implementation patterns - uses proper GATT service and characteristics
"""

import asyncio
import logging
import socket
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, dbus_property
    from dbus_next import Variant
    from dbus_next.constants import BusType, PropertyAccess
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.warning("dbus-next not available - install with: pip install dbus-next")


# LeRobot BLE Service UUID (custom 128-bit UUID)
LEROBOT_SERVICE_UUID = "c5f50001-1234-5678-89ab-123456789abc"
# IP Address Characteristic UUID (read-only)
IP_ADDRESS_CHAR_UUID = "c5f50002-1234-5678-89ab-123456789abc"
# WiFi SSID Characteristic UUID (write)
WIFI_SSID_CHAR_UUID = "c5f50003-1234-5678-89ab-123456789abc"
# WiFi Password Characteristic UUID (write)
WIFI_PASSWORD_CHAR_UUID = "c5f50004-1234-5678-89ab-123456789abc"
# WiFi Status Characteristic UUID (read)
WIFI_STATUS_CHAR_UUID = "c5f50005-1234-5678-89ab-123456789abc"
# WiFi Connect Characteristic UUID (write - triggers connection)
WIFI_CONNECT_CHAR_UUID = "c5f50006-1234-5678-89ab-123456789abc"
# WiFi Scan Characteristic UUID (write - triggers scan)
WIFI_SCAN_CHAR_UUID = "c5f50007-1234-5678-89ab-123456789abc"
# WiFi Networks Characteristic UUID (read - scan results)
WIFI_NETWORKS_CHAR_UUID = "c5f50008-1234-5678-89ab-123456789abc"


class IPAddressCharacteristic(ServiceInterface):
    """
    GATT Characteristic for IP Address
    - Read-only characteristic that provides current IP as UTF-8 string
    - Modeled after Pybricks hub capabilities characteristic
    """
    
    def __init__(self, char_path: str, service_path: str):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self._value = b"No IP"  # bytes object as required by D-Bus
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return IP_ADDRESS_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['read']
    
    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        """Called when client reads the characteristic"""
        logger.info(f"IP characteristic read: {self._value.decode('utf-8', errors='replace')}")
        return self._value
    
    def update_ip(self, ip_address: str):
        """Update the characteristic value with new IP"""
        self._value = ip_address.encode('utf-8')


class WiFiSSIDCharacteristic(ServiceInterface):
    """GATT Characteristic for WiFi SSID (write)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b""
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_SSID_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['write', 'write-without-response']
    
    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}'):
        """Called when client writes SSID"""
        ssid = bytes(value).decode('utf-8', errors='replace')
        self._value = bytes(value)
        self.server.wifi_ssid = ssid
        logger.info(f"WiFi SSID received: {ssid}")


class WiFiPasswordCharacteristic(ServiceInterface):
    """GATT Characteristic for WiFi Password (write)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b""
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_PASSWORD_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['write', 'write-without-response']
    
    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}'):
        """Called when client writes password"""
        password = bytes(value).decode('utf-8', errors='replace')
        self._value = bytes(value)
        self.server.wifi_password = password
        logger.info(f"WiFi password received (length: {len(password)})")


class WiFiStatusCharacteristic(ServiceInterface):
    """GATT Characteristic for WiFi Status (read)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b"disconnected"
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_STATUS_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['read', 'notify']
    
    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        """Called when client reads status"""
        status = self.server.get_wifi_status()
        self._value = status.encode('utf-8')
        logger.info(f"WiFi status read: {status}")
        return self._value
    
    def update_status(self, status: str):
        """Update status value"""
        self._value = status.encode('utf-8')


class WiFiConnectCharacteristic(ServiceInterface):
    """GATT Characteristic to trigger WiFi connection (write)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b"0"
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_CONNECT_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['write', 'write-without-response']
    
    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}'):
        """Called when client writes to trigger connection"""
        logger.info("WiFi connect triggered via BLE")
        # Trigger connection in background
        import asyncio
        asyncio.create_task(self.server.connect_wifi())


class WiFiScanCharacteristic(ServiceInterface):
    """GATT Characteristic to trigger WiFi scan (write)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b"0"
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_SCAN_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['write', 'write-without-response']
    
    @method()
    def WriteValue(self, value: 'ay', options: 'a{sv}'):
        """Called when client writes to trigger WiFi scan"""
        logger.info("WiFi scan triggered via BLE")
        # Trigger scan in background
        import asyncio
        asyncio.create_task(self.server.scan_wifi())


class WiFiNetworksCharacteristic(ServiceInterface):
    """GATT Characteristic for WiFi scan results (read)"""
    
    def __init__(self, char_path: str, service_path: str, server):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path = char_path
        self.service_path = service_path
        self.server = server
        self._value = b"[]"
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return WIFI_NETWORKS_CHAR_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Service(self) -> 'o':
        return self.service_path
    
    @dbus_property(PropertyAccess.READ)
    def Value(self) -> 'ay':
        return self._value
    
    @dbus_property(PropertyAccess.READ)
    def Flags(self) -> 'as':
        return ['read']
    
    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        """Called when client reads scan results"""
        logger.info(f"WiFi networks read ({len(self._value)} bytes)")
        return self._value
    
    def update_networks(self, networks_json: str):
        """Update networks list"""
        # Truncate if too large (BLE MTU limit ~512 bytes typical)
        if len(networks_json) > 512:
            logger.warning(f"Networks list truncated from {len(networks_json)} to 512 bytes")
            networks_json = networks_json[:512]
        self._value = networks_json.encode('utf-8')


class LeRobotGattService(ServiceInterface):
    """
    GATT Service for LeRobot IP Broadcasting and WiFi Provisioning
    - Primary service with IP address and WiFi characteristics
    """
    
    def __init__(self, service_path: str, char_paths: list):
        super().__init__('org.bluez.GattService1')
        self.path = service_path
        self.char_paths = char_paths
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return LEROBOT_SERVICE_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Primary(self) -> 'b':
        return True
    
    @dbus_property(PropertyAccess.READ)
    def Characteristics(self) -> 'ao':
        return self.char_paths


class GattApplication(ServiceInterface):
    """
    GATT Application - manages GATT services
    Required by BlueZ GATT Manager API
    """
    
    def __init__(self, app_path: str, service_path: str):
        super().__init__('org.freedesktop.DBus.ObjectManager')
        self.path = app_path
        self.service_path = service_path
        
    @method()
    def GetManagedObjects(self) -> 'a{oa{sa{sv}}}':
        """Return all managed GATT services and characteristics"""
        return {
            self.service_path: {
                'org.bluez.GattService1': {
                    'UUID': Variant('s', LEROBOT_SERVICE_UUID),
                    'Primary': Variant('b', True),
                }
            }
        }


class LEAdvertisement(ServiceInterface):
    """
    BLE Advertisement - controls what data is broadcast in BLE advertisements
    Only includes essential properties to avoid BlueZ compatibility issues
    """
    
    def __init__(self, adv_path: str, adv_type: str = 'peripheral'):
        super().__init__('org.bluez.LEAdvertisement1')
        self.path = adv_path
        self.adv_type = adv_type
        self.service_uuids = [LEROBOT_SERVICE_UUID]
        self.local_name = "LeRobot"
        
    @dbus_property(PropertyAccess.READ)
    def Type(self) -> 's':
        return self.adv_type
    
    @dbus_property(PropertyAccess.READ)
    def ServiceUUIDs(self) -> 'as':
        return self.service_uuids
    
    @dbus_property(PropertyAccess.READ)
    def LocalName(self) -> 's':
        return self.local_name
    
    def update_name(self, name: str):
        """Update the advertised local name"""
        self.local_name = name
        logger.info(f"Advertisement name updated to: {name}")


class BLEGattServer:
    """
    Complete BLE GATT Server for IP broadcasting
    Implements proper BlueZ GATT Manager pattern like Pybricks
    """
    
    def __init__(self, device_name: str = "LeRobot"):
        self.device_name = device_name
        self.running = False
        self.bus: Optional[MessageBus] = None
        self.adapter_path = '/org/bluez/hci0'
        
        # D-Bus paths for GATT hierarchy
        self.app_path = '/org/bluez/lerobot'
        self.service_path = '/org/bluez/lerobot/service0'
        self.char_ip_path = '/org/bluez/lerobot/service0/char0'
        self.char_wifi_ssid_path = '/org/bluez/lerobot/service0/char1'
        self.char_wifi_password_path = '/org/bluez/lerobot/service0/char2'
        self.char_wifi_status_path = '/org/bluez/lerobot/service0/char3'
        self.char_wifi_connect_path = '/org/bluez/lerobot/service0/char4'
        self.char_wifi_scan_path = '/org/bluez/lerobot/service0/char5'
        self.char_wifi_networks_path = '/org/bluez/lerobot/service0/char6'
        self.adv_path = '/org/bluez/lerobot/advertisement0'
        
        # GATT and Advertisement objects
        self.application = None
        self.service = None
        self.char_ip = None
        self.char_wifi_ssid = None
        self.char_wifi_password = None
        self.char_wifi_status = None
        self.char_wifi_connect = None
        self.char_wifi_scan = None
        self.char_wifi_networks = None
        self.advertisement = None
        
        # WiFi credentials storage
        self.wifi_ssid = ""
        self.wifi_password = ""
        
    def get_local_ip(self) -> str:
        """Get current local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.debug(f"No IP available: {e}")
            return "No IP"
    
    def get_bluetooth_mac_suffix(self) -> str:
        """Get last 4 digits of Bluetooth MAC address"""
        try:
            import subprocess
            result = subprocess.run(
                ['hciconfig', 'hci0'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Parse MAC address from output like "BD Address: XX:XX:XX:XX:YY:ZZ"
                for line in result.stdout.split('\n'):
                    if 'BD Address:' in line:
                        parts = line.split()
                        # Find index of "Address:" and get next element
                        for i, part in enumerate(parts):
                            if part == 'Address:' and i + 1 < len(parts):
                                mac = parts[i + 1]
                                # Get last 4 hex digits without colons
                                mac_clean = mac.replace(':', '')
                                return mac_clean[-4:].upper()
            return "0000"
        except Exception as e:
            logger.error(f"Could not get MAC address: {e}")
            return "0000"
    
    def get_wifi_status(self) -> str:
        """Get current WiFi connection status via nmcli"""
        try:
            import subprocess
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'STATE', 'general'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                state = result.stdout.strip()
                if 'connected' in state.lower():
                    # Get connected SSID
                    ssid_result = subprocess.run(
                        ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    for line in ssid_result.stdout.split('\n'):
                        if line.startswith('yes:'):
                            ssid = line.split(':', 1)[1]
                            return f"connected:{ssid}"
                    return "connected"
                else:
                    return "disconnected"
            return "unknown"
        except Exception as e:
            logger.error(f"Error getting WiFi status: {e}")
            return "error"
    
    async def connect_wifi(self):
        """Connect to WiFi using stored credentials via NetworkManager"""
        if not self.wifi_ssid:
            logger.error("No WiFi SSID provided")
            if self.char_wifi_status:
                self.char_wifi_status.update_status("error:no_ssid")
            return
        
        logger.info(f"Attempting to connect to WiFi: {self.wifi_ssid}")
        
        if self.char_wifi_status:
            self.char_wifi_status.update_status("connecting")
        
        try:
            import subprocess
            
            # Try to connect using nmcli
            cmd = [
                'nmcli', 'dev', 'wifi', 'connect',
                self.wifi_ssid
            ]
            
            if self.wifi_password:
                cmd.extend(['password', self.wifi_password])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully connected to {self.wifi_ssid}")
                if self.char_wifi_status:
                    self.char_wifi_status.update_status(f"connected:{self.wifi_ssid}")
                
                # Wait a bit for IP to be assigned
                await asyncio.sleep(3)
                
                # Update IP characteristic
                new_ip = self.get_local_ip()
                if self.char_ip and new_ip != "No IP":
                    self.char_ip.update_ip(new_ip)
                    logger.info(f"New IP after WiFi connect: {new_ip}")
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"Failed to connect to WiFi: {error_msg}")
                if self.char_wifi_status:
                    self.char_wifi_status.update_status(f"error:{error_msg[:30]}")
                    
        except subprocess.TimeoutExpired:
            logger.error("WiFi connection timeout")
            if self.char_wifi_status:
                self.char_wifi_status.update_status("error:timeout")
        except Exception as e:
            logger.error(f"WiFi connection error: {e}")
            if self.char_wifi_status:
                self.char_wifi_status.update_status(f"error:{str(e)[:30]}")
    
    async def scan_wifi(self):
        """Scan for available WiFi networks using NetworkManager"""
        logger.info("Starting WiFi scan...")
        
        try:
            import subprocess
            import json
            
            # Trigger fresh scan
            subprocess.run(
                ['nmcli', 'dev', 'wifi', 'rescan'],
                capture_output=True,
                timeout=10
            )
            
            # Wait for scan to complete
            await asyncio.sleep(2)
            
            # Get scan results
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                networks = []
                lines = result.stdout.strip().split('\n')
                
                for line in lines[:20]:  # Limit to 20 networks
                    if not line.strip():
                        continue
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        ssid = parts[0]
                        signal = parts[1]
                        security = parts[2]
                        
                        if ssid:  # Skip hidden networks
                            networks.append({
                                'ssid': ssid,
                                'signal': signal,
                                'security': security
                            })
                
                # Convert to compact JSON
                networks_json = json.dumps(networks, separators=(',', ':'))
                logger.info(f"Found {len(networks)} WiFi networks")
                
                # Update characteristic
                if self.char_wifi_networks:
                    self.char_wifi_networks.update_networks(networks_json)
                    
            else:
                logger.error(f"WiFi scan failed: {result.stderr}")
                if self.char_wifi_networks:
                    self.char_wifi_networks.update_networks('[]')
                    
        except subprocess.TimeoutExpired:
            logger.error("WiFi scan timeout")
            if self.char_wifi_networks:
                self.char_wifi_networks.update_networks('[]')
        except Exception as e:
            logger.error(f"WiFi scan error: {e}")
            if self.char_wifi_networks:
                self.char_wifi_networks.update_networks('[]')
    
    async def register_gatt_service(self):
        """Register GATT service with BlueZ GATT Manager"""
        try:
            # Get GATT Manager interface
            introspection = await self.bus.introspect('org.bluez', self.adapter_path)
            adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
            gatt_manager = adapter.get_interface('org.bluez.GattManager1')
            
            # Create and export GATT objects
            char_paths = [
                self.char_ip_path,
                self.char_wifi_ssid_path,
                self.char_wifi_password_path,
                self.char_wifi_status_path,
                self.char_wifi_connect_path,
                self.char_wifi_scan_path,
                self.char_wifi_networks_path
            ]
            
            self.application = GattApplication(self.app_path, self.service_path)
            self.service = LeRobotGattService(self.service_path, char_paths)
            self.char_ip = IPAddressCharacteristic(self.char_ip_path, self.service_path)
            self.char_wifi_ssid = WiFiSSIDCharacteristic(self.char_wifi_ssid_path, self.service_path, self)
            self.char_wifi_password = WiFiPasswordCharacteristic(self.char_wifi_password_path, self.service_path, self)
            self.char_wifi_status = WiFiStatusCharacteristic(self.char_wifi_status_path, self.service_path, self)
            self.char_wifi_connect = WiFiConnectCharacteristic(self.char_wifi_connect_path, self.service_path, self)
            self.char_wifi_scan = WiFiScanCharacteristic(self.char_wifi_scan_path, self.service_path, self)
            self.char_wifi_networks = WiFiNetworksCharacteristic(self.char_wifi_networks_path, self.service_path, self)
            
            # Export to D-Bus
            self.bus.export(self.app_path, self.application)
            self.bus.export(self.service_path, self.service)
            self.bus.export(self.char_ip_path, self.char_ip)
            self.bus.export(self.char_wifi_ssid_path, self.char_wifi_ssid)
            self.bus.export(self.char_wifi_password_path, self.char_wifi_password)
            self.bus.export(self.char_wifi_status_path, self.char_wifi_status)
            self.bus.export(self.char_wifi_connect_path, self.char_wifi_connect)
            self.bus.export(self.char_wifi_scan_path, self.char_wifi_scan)
            self.bus.export(self.char_wifi_networks_path, self.char_wifi_networks)
            
            # Register application with BlueZ
            await gatt_manager.call_register_application(self.app_path, {})
            
            logger.info("GATT service registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register GATT service: {e}")
            return False
    
    async def setup_advertising(self):
        """Setup BLE advertising with service UUID and device name"""
        try:
            # Get LE Advertising Manager
            introspection = await self.bus.introspect('org.bluez', self.adapter_path)
            adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
            le_adv_manager = adapter.get_interface('org.bluez.LEAdvertisingManager1')
            
            # Make sure we're powered on
            props = adapter.get_interface('org.freedesktop.DBus.Properties')
            await props.call_set('org.bluez.Adapter1', 'Powered', Variant('b', True))
            
            # Create and register advertisement
            mac_suffix = self.get_bluetooth_mac_suffix()
            adv_name = f"{self.device_name}-{mac_suffix}"
            
            self.advertisement = LEAdvertisement(self.adv_path)
            self.advertisement.update_name(adv_name)
            
            # Export advertisement to D-Bus
            self.bus.export(self.adv_path, self.advertisement)
            
            # Register advertisement with BlueZ
            await le_adv_manager.call_register_advertisement(self.adv_path, {})
            
            logger.info(f"Advertisement registered with name: {adv_name}")
            logger.info(f"Service UUID in advertisement: {LEROBOT_SERVICE_UUID}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup advertising: {e}", exc_info=True)
            # Try fallback method
            try:
                await self.set_device_name()
                return True
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                return False
    
    async def set_device_name(self):
        """Set Bluetooth device name to include MAC suffix"""
        try:
            mac_suffix = self.get_bluetooth_mac_suffix()
            device_name = f"{self.device_name}-{mac_suffix}"
            
            # Set via adapter properties
            introspection = await self.bus.introspect('org.bluez', self.adapter_path)
            adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
            props = adapter.get_interface('org.freedesktop.DBus.Properties')
            
            await props.call_set('org.bluez.Adapter1', 'Alias', Variant('s', device_name))
            logger.info(f"Set device name: {device_name}")
            
        except Exception as e:
            logger.error(f"Failed to set device name: {e}")
    
    async def make_discoverable(self):
        """Make adapter discoverable"""
        try:
            introspection = await self.bus.introspect('org.bluez', self.adapter_path)
            adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
            props = adapter.get_interface('org.freedesktop.DBus.Properties')
            
            await props.call_set('org.bluez.Adapter1', 'Discoverable', Variant('b', True))
            await props.call_set('org.bluez.Adapter1', 'DiscoverableTimeout', Variant('u', 0))
            
            logger.info("Adapter is now discoverable")
            
        except Exception as e:
            logger.error(f"Failed to make discoverable: {e}")
    
    async def run(self):
        """Main run loop for GATT server"""
        if not DBUS_AVAILABLE:
            logger.error("D-Bus not available")
            return
        
        try:
            # Connect to system bus
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            logger.info("Connected to D-Bus system bus")
            
            # Register GATT service
            if not await self.register_gatt_service():
                logger.error("Failed to register GATT service")
                return
            
            # Setup advertising
            await self.setup_advertising()
            
            # Make discoverable
            await self.make_discoverable()
            
            self.running = True
            logger.info("BLE GATT Server started successfully")
            
            # Update IP periodically
            last_ip = ""
            while self.running:
                current_ip = self.get_local_ip()
                
                if current_ip != last_ip:
                    logger.info(f"IP changed: {current_ip}")
                    last_ip = current_ip
                    
                    # Update characteristic value
                    if self.char_ip:
                        self.char_ip.update_ip(current_ip)
                
                await asyncio.sleep(10)
                
        except Exception as e:
            logger.error(f"GATT server error: {e}", exc_info=True)
        finally:
            self.running = False
            
            # Unregister advertisement
            if self.bus and self.advertisement:
                try:
                    introspection = await self.bus.introspect('org.bluez', self.adapter_path)
                    adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
                    le_adv_manager = adapter.get_interface('org.bluez.LEAdvertisingManager1')
                    await le_adv_manager.call_unregister_advertisement(self.adv_path)
                    logger.info("Advertisement unregistered")
                except Exception as e:
                    logger.warning(f"Failed to unregister advertisement: {e}")
            
            if self.bus:
                self.bus.disconnect()
    
    def start(self):
        """Start GATT server in background thread"""
        if self.running:
            logger.warning("GATT server already running")
            return
        
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run())
            finally:
                loop.close()
        
        import threading
        thread = threading.Thread(target=run_async_loop, daemon=True)
        thread.start()
        logger.info("GATT server thread started")
    
    def stop(self):
        """Stop GATT server"""
        self.running = False
        logger.info("GATT server stopping")


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = BLEGattServer()
    
    try:
        import threading
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.run())
    except KeyboardInterrupt:
        print("\nStopping...")
        server.stop()
