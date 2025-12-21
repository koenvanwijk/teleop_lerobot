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


class LeRobotGattService(ServiceInterface):
    """
    GATT Service for LeRobot IP Broadcasting
    - Primary service with IP address characteristic
    """
    
    def __init__(self, service_path: str, char_path: str):
        super().__init__('org.bluez.GattService1')
        self.path = service_path
        self.char_path = char_path
        
    @dbus_property(PropertyAccess.READ)
    def UUID(self) -> 's':
        return LEROBOT_SERVICE_UUID
    
    @dbus_property(PropertyAccess.READ)
    def Primary(self) -> 'b':
        return True
    
    @dbus_property(PropertyAccess.READ)
    def Characteristics(self) -> 'ao':
        return [self.char_path]


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
        self.char_path = '/org/bluez/lerobot/service0/char0'
        self.adv_path = '/org/bluez/lerobot/advertisement0'
        
        # GATT and Advertisement objects
        self.application = None
        self.service = None
        self.characteristic = None
        self.advertisement = None
        
    def get_local_ip(self) -> str:
        """Get current local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"Error getting IP: {e}")
            return "No IP"
    
    async def register_gatt_service(self):
        """Register GATT service with BlueZ GATT Manager"""
        try:
            # Get GATT Manager interface
            introspection = await self.bus.introspect('org.bluez', self.adapter_path)
            adapter = self.bus.get_proxy_object('org.bluez', self.adapter_path, introspection)
            gatt_manager = adapter.get_interface('org.bluez.GattManager1')
            
            # Create and export GATT objects
            self.application = GattApplication(self.app_path, self.service_path)
            self.service = LeRobotGattService(self.service_path, self.char_path)
            self.characteristic = IPAddressCharacteristic(self.char_path, self.service_path)
            
            # Export to D-Bus
            self.bus.export(self.app_path, self.application)
            self.bus.export(self.service_path, self.service)
            self.bus.export(self.char_path, self.characteristic)
            
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
            ip = self.get_local_ip()
            adv_name = f"{self.device_name}-{ip}"
            
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
        """Set Bluetooth device name to include IP"""
        try:
            ip = self.get_local_ip()
            device_name = f"{self.device_name}-{ip}"
            
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
                    if self.characteristic:
                        self.characteristic.update_ip(current_ip)
                    
                    # Update advertisement name
                    if self.advertisement:
                        adv_name = f"{self.device_name}-{current_ip}"
                        self.advertisement.update_name(adv_name)
                    
                    # Also update adapter alias as fallback
                    await self.set_device_name()
                
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
