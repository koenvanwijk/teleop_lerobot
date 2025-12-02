"""
Network Manager for Raspberry Pi LeRobot
Handles Access Point and WiFi switching
"""

import subprocess
import logging
from typing import Dict, Any, Optional, List
import asyncio
import os
import json

logger = logging.getLogger(__name__)


class NetworkManager:
    """Manages network configuration for AP and WiFi modes"""

    def __init__(self, ap_ssid: str = "LeRobot-AP", ap_password: str = "robotics123", interface: str = "wlan0"):
        """
        Initialize network manager
        
        Args:
            ap_ssid: Access Point SSID
            ap_password: Access Point password (min 8 chars)
            interface: WiFi interface name (usually wlan0)
        """
        self.ap_ssid = ap_ssid
        self.ap_password = ap_password
        self.interface = interface
        self.current_mode = "unknown"

    async def initialize(self) -> bool:
        """Initialize network and detect current mode"""
        try:
            logger.info("Initializing network manager...")
            
            # Detect current mode
            self.current_mode = await self.get_current_mode()
            logger.info(f"Current network mode: {self.current_mode}")
            
            return True

        except Exception as e:
            logger.error(f"Error initializing network: {e}")
            return False

    async def _run_command(self, cmd: List[str]) -> tuple[int, str, str]:
        """
        Run shell command asynchronously
        
        Returns:
            (returncode, stdout, stderr)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            logger.error(f"Error running command {' '.join(cmd)}: {e}")
            return -1, "", str(e)

    async def get_current_mode(self) -> str:
        """
        Detect current network mode
        
        Returns:
            "ap", "wifi", or "unknown"
        """
        try:
            # Check if running hostapd (AP mode)
            returncode, stdout, _ = await self._run_command(['pgrep', '-f', 'hostapd'])
            if returncode == 0:
                return "ap"
            
            # Check if connected to WiFi
            returncode, stdout, _ = await self._run_command(['nmcli', '-t', '-f', 'DEVICE,STATE', 'device'])
            if self.interface in stdout and 'connected' in stdout:
                return "wifi"
            
            return "unknown"

        except Exception as e:
            logger.error(f"Error detecting network mode: {e}")
            return "unknown"

    async def get_status(self) -> Dict[str, Any]:
        """
        Get current network status
        
        Returns:
            Dictionary with network information
        """
        try:
            status = {
                'mode': await self.get_current_mode(),
                'interface': self.interface,
                'ip_address': None,
                'ssid': None,
                'signal_strength': None
            }

            # Get IP address
            returncode, stdout, _ = await self._run_command(['ip', 'addr', 'show', self.interface])
            if returncode == 0:
                for line in stdout.split('\n'):
                    if 'inet ' in line:
                        ip = line.strip().split()[1].split('/')[0]
                        status['ip_address'] = ip
                        break

            # Get WiFi info if in WiFi mode
            if status['mode'] == 'wifi':
                returncode, stdout, _ = await self._run_command(['nmcli', '-t', '-f', 'SSID,SIGNAL', 'device', 'wifi', 'list'])
                if returncode == 0 and stdout:
                    lines = stdout.strip().split('\n')
                    if lines:
                        parts = lines[0].split(':')
                        if len(parts) >= 2:
                            status['ssid'] = parts[0]
                            try:
                                status['signal_strength'] = int(parts[1])
                            except:
                                pass

            # Get AP info if in AP mode
            if status['mode'] == 'ap':
                status['ssid'] = self.ap_ssid

            return status

        except Exception as e:
            logger.error(f"Error getting network status: {e}")
            return {'mode': 'error', 'error': str(e)}

    async def start_access_point(self) -> bool:
        """
        Start Access Point mode
        
        Returns:
            True if successful
        """
        try:
            logger.info(f"Starting Access Point: {self.ap_ssid}")

            # Check if running on Linux
            if os.name != 'posix':
                logger.warning("Access Point mode only supported on Linux/Raspberry Pi")
                return False

            # Check if already in AP mode
            current_mode = await self.get_current_mode()
            if current_mode == 'ap':
                logger.info("Already in Access Point mode")
                return True

            # Stop WiFi connection if active
            if current_mode == 'wifi':
                logger.info("Disconnecting from WiFi...")
                await self._run_command(['sudo', 'nmcli', 'device', 'disconnect', self.interface])

            # Create hostapd configuration
            hostapd_conf = f"""interface={self.interface}
driver=nl80211
ssid={self.ap_ssid}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.ap_password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""

            # Write configuration
            with open('/tmp/hostapd_lerobot.conf', 'w') as f:
                f.write(hostapd_conf)

            # Stop NetworkManager management of interface
            await self._run_command(['sudo', 'nmcli', 'device', 'set', self.interface, 'managed', 'no'])

            # Configure IP address
            await self._run_command(['sudo', 'ip', 'addr', 'flush', 'dev', self.interface])
            await self._run_command(['sudo', 'ip', 'addr', 'add', '192.168.4.1/24', 'dev', self.interface])
            await self._run_command(['sudo', 'ip', 'link', 'set', self.interface, 'up'])

            # Start hostapd
            returncode, stdout, stderr = await self._run_command([
                'sudo', 'hostapd', '-B', '/tmp/hostapd_lerobot.conf'
            ])

            if returncode == 0:
                logger.info(f"✓ Access Point started: {self.ap_ssid}")
                self.current_mode = 'ap'
                
                # Optionally start dnsmasq for DHCP
                await self._start_dhcp_server()
                
                return True
            else:
                logger.error(f"Failed to start Access Point: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error starting Access Point: {e}")
            return False

    async def _start_dhcp_server(self):
        """Start DHCP server for AP mode"""
        try:
            # Check if dnsmasq is installed
            returncode, _, _ = await self._run_command(['which', 'dnsmasq'])
            if returncode != 0:
                logger.warning("dnsmasq not installed, DHCP server not started")
                return

            # Stop existing dnsmasq
            await self._run_command(['sudo', 'killall', 'dnsmasq'])

            # Start dnsmasq
            await self._run_command([
                'sudo', 'dnsmasq',
                '--interface=' + self.interface,
                '--bind-interfaces',
                '--dhcp-range=192.168.4.50,192.168.4.150,12h'
            ])
            
            logger.info("✓ DHCP server started")

        except Exception as e:
            logger.error(f"Error starting DHCP server: {e}")

    async def stop_access_point(self) -> bool:
        """
        Stop Access Point mode
        
        Returns:
            True if successful
        """
        try:
            logger.info("Stopping Access Point...")

            # Stop hostapd
            await self._run_command(['sudo', 'killall', 'hostapd'])

            # Stop dnsmasq
            await self._run_command(['sudo', 'killall', 'dnsmasq'])

            # Re-enable NetworkManager management
            await self._run_command(['sudo', 'nmcli', 'device', 'set', self.interface, 'managed', 'yes'])

            logger.info("✓ Access Point stopped")
            self.current_mode = 'unknown'
            return True

        except Exception as e:
            logger.error(f"Error stopping Access Point: {e}")
            return False

    async def connect_to_wifi(self, ssid: str, password: str) -> bool:
        """
        Connect to WiFi network
        
        Args:
            ssid: WiFi SSID
            password: WiFi password
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"Connecting to WiFi: {ssid}")

            # Stop AP if running
            current_mode = await self.get_current_mode()
            if current_mode == 'ap':
                await self.stop_access_point()

            # Connect using NetworkManager
            returncode, stdout, stderr = await self._run_command([
                'sudo', 'nmcli', 'device', 'wifi', 'connect', ssid, 'password', password
            ])

            if returncode == 0:
                logger.info(f"✓ Connected to WiFi: {ssid}")
                self.current_mode = 'wifi'
                
                # Wait for IP
                await asyncio.sleep(2)
                
                return True
            else:
                logger.error(f"Failed to connect to WiFi: {stderr}")
                return False

        except Exception as e:
            logger.error(f"Error connecting to WiFi: {e}")
            return False

    async def scan_wifi(self) -> List[Dict[str, Any]]:
        """
        Scan for available WiFi networks
        
        Returns:
            List of WiFi networks with SSID, signal strength, security
        """
        try:
            logger.info("Scanning for WiFi networks...")

            # Trigger scan
            await self._run_command(['sudo', 'nmcli', 'device', 'wifi', 'rescan'])
            await asyncio.sleep(2)

            # Get results
            returncode, stdout, _ = await self._run_command([
                'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list'
            ])

            if returncode != 0:
                return []

            networks = []
            for line in stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 3:
                    ssid = parts[0]
                    if ssid:  # Skip empty SSIDs
                        try:
                            signal = int(parts[1])
                        except:
                            signal = 0
                        
                        security = parts[2] if len(parts) > 2 else 'none'
                        
                        networks.append({
                            'ssid': ssid,
                            'signal': signal,
                            'security': security
                        })

            # Sort by signal strength
            networks.sort(key=lambda x: x['signal'], reverse=True)

            logger.info(f"Found {len(networks)} WiFi networks")
            return networks

        except Exception as e:
            logger.error(f"Error scanning WiFi: {e}")
            return []

    async def disconnect(self) -> bool:
        """
        Disconnect from current network
        
        Returns:
            True if successful
        """
        try:
            logger.info("Disconnecting from network...")

            current_mode = await self.get_current_mode()
            
            if current_mode == 'ap':
                return await self.stop_access_point()
            elif current_mode == 'wifi':
                await self._run_command(['sudo', 'nmcli', 'device', 'disconnect', self.interface])
                self.current_mode = 'unknown'
                return True
            
            return True

        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return False
