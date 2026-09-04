# LeRobot Teleoperation System - Requirements & Specificaties Document

**Versie:** 2.0.0  
**Datum:** December 2024  
**Project:** LeRobot Teleoperation Web Interface  
**Repository:** https://github.com/koenvanwijk/teleop_lerobot

---

## 📋 Executive Summary

Het LeRobot Teleoperation System is een uitgebreide web-gebaseerde platform voor remote robot control, gebouwd op het LeRobot framework van Hugging Face. Het systeem biedt volledige teleoperation functionaliteit met camera streaming, network management, visual programming (Blockly), en Bluetooth device discovery.

**Belangrijkste kenmerken:**
- 🤖 Automatische opstart van teleoperation bij boot
- 🌐 Web-based control interface (FastAPI + WebSocket)
- 📹 Multi-camera MJPEG streaming
- 📡 Bluetooth Low Energy device discovery
- 🎨 Visual programming met Blockly
- 🔄 WiFi/Access Point mode switching
- ⚙️ USB device auto-mapping met udev rules

---

## 1. Functionele Requirements

### 1.1 Robot Teleoperation

#### FR-1.1.1: Device Detection & Mapping
**Prioriteit:** MUST  
**Beschrijving:** Het systeem moet automatisch USB serial devices detecteren en toewijzen aan specifieke robots.

**Requirements:**
- Detecteren van alle `/dev/tty*` devices met udev-gegenereerde symlinks
- Ondersteuning voor mapping.csv format: `SERIAL_SHORT,NICE_NAME,ROLE,TYPE`
- Automatische creatie van symlinks: `/dev/tty_{name}_{role}_{type}`
- Generieke fallback symlinks: `/dev/tty_follower` en `/dev/tty_leader`
- Real-time device scanning via API endpoint `/api/devices`

**Acceptatiecriteria:**
- Device lijst wordt binnen 1 seconde geladen
- Symlinks zijn stabiel na reboot
- Meerdere devices met verschillende roles worden correct geïdentificeerd

#### FR-1.1.2: Teleoperation Control
**Prioriteit:** MUST  
**Beschrijving:** Start, stop en monitor robot teleoperation in real-time.

**Requirements:**
- Start teleoperation met specifieke follower/leader combinatie
- Stop teleoperation zonder data loss
- Real-time positie monitoring (6 motoren: rotation, pitch, elbow, wrist_pitch, wrist_roll, jaw)
- Positie caching met 50ms expiry voor performance
- Thread-safe operaties (locks voor concurrent access)
- Graceful shutdown bij server stop

**API Endpoints:**
```
POST /api/teleoperation/start
POST /api/teleoperation/stop
GET /api/teleoperation/current-position
POST /api/teleoperation/save-current-position
POST /api/teleoperation/leader/command
```

**Acceptatiecriteria:**
- Teleoperation start binnen 3 seconden
- Positie updates met < 100ms latency
- Geen motor drift na stop
- Error handling voor disconnected devices

#### FR-1.1.3: Device Persistence
**Prioriteit:** SHOULD  
**Beschrijving:** Onthoud laatst gebruikte device configuratie.

**Requirements:**
- Opslaan van device defaults in `~/.lerobot_device_defaults.json`
- Automatisch laden van defaults bij startup
- Mogelijkheid tot reset naar factory defaults
- Ondersteuning voor meerdere robot configuraties

**Data format:**
```json
{
  "follower_port": "/dev/tty_white_12_follower_so101",
  "follower_type": "so101",
  "follower_id": "white_12",
  "leader_port": "/dev/tty_black_leader_so101",
  "leader_type": "so101",
  "leader_id": "black"
}
```

### 1.2 Camera Streaming

#### FR-1.2.1: Multi-Camera Detection
**Prioriteit:** MUST  
**Beschrijving:** Automatische detectie en configuratie van meerdere USB camera's.

**Requirements:**
- Scannen van camera indices 0-10 via OpenCV VideoCapture
- Automatische initialisatie bij server startup
- Support voor verschillende resoluties (640×480 default)
- Configureerbare FPS (30 default)
- Thread-safe frame capture met locks

**Acceptatiecriteria:**
- Detectie binnen 5 seconden
- Alle werkende cameras worden gevonden
- Geen resource leaks bij camera disconnect

#### FR-1.2.2: MJPEG Streaming
**Prioriteit:** MUST  
**Beschrijving:** Real-time video streaming via HTTP MJPEG.

**Requirements:**
- MJPEG encoding met JPEG kwaliteit 85%
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Individuele streams per camera via `/api/cameras/{name}/stream`
- Automatische cleanup bij client disconnect
- Support voor meerdere gelijktijdige viewers

**Performance targets:**
- Frame rate: 20-30 FPS
- Latency: < 200ms
- Bandwidth: ~500KB/s per camera @ 640×480

#### FR-1.2.3: Camera Management
**Prioriteit:** SHOULD  
**Beschrijving:** Start, stop en configure individuele camera's.

**API Endpoints:**
```
GET /api/cameras - Lijst alle cameras
GET /api/cameras/{name}/stream - MJPEG stream
POST /api/cameras/detect - Force re-detection
```

**Camera State:**
```python
{
  "name": "Camera 0",
  "index": 0,
  "active": true,
  "resolution": [640, 480],
  "fps": 30,
  "frame_count": 1234
}
```

### 1.3 Network Management

#### FR-1.3.1: WiFi Client Mode
**Prioriteit:** MUST  
**Beschrijving:** Verbinden met bestaande WiFi netwerken.

**Requirements:**
- WiFi netwerk scanning via `nmcli`
- Ondersteuning voor WPA/WPA2 authenticatie
- Automatische DHCP IP configuratie
- Signal strength monitoring
- Disconnect functionaliteit
- Verbindingsstatus monitoring

**API Endpoints:**
```
GET /api/network/wifi/scan - Scan netwerken
POST /api/network/wifi/connect - Connect met credentials
POST /api/network/disconnect - Disconnect
```

**Acceptatiecriteria:**
- Scan voltooid binnen 10 seconden
- Verbinding binnen 30 seconden
- Stabiele connectie met auto-reconnect

#### FR-1.3.2: Access Point Mode
**Prioriteit:** MUST  
**Beschrijving:** Raspberry Pi als WiFi hotspot configureren.

**Requirements:**
- SSID: `LeRobot-AP` (configureerbaar)
- Password: `robotics123` (min 8 chars)
- IP adres: `192.168.4.1/24`
- DHCP range: `192.168.4.50-150`
- DNS server: `8.8.8.8`
- Automatische start via `hostapd` + `dnsmasq`
- Graceful shutdown zonder NetworkManager conflicts

**API Endpoints:**
```
POST /api/network/ap/start - Start Access Point
POST /api/network/ap/stop - Stop Access Point
GET /api/network/status - Current mode & IP
```

**Configuratie bestanden:**
- `/tmp/hostapd.conf` - WiFi AP configuratie
- `/tmp/dnsmasq.conf` - DHCP server configuratie

**Acceptatiecriteria:**
- AP start binnen 10 seconden
- Clients kunnen verbinden en IP krijgen
- Web interface bereikbaar op 192.168.4.1
- Netwerk hersteld na stop

### 1.4 Bluetooth Discovery

#### FR-1.4.1: BLE GATT Server
**Prioriteit:** SHOULD  
**Beschrijving:** Adverteren van IP-adres via Bluetooth Low Energy.

**Requirements:**
- GATT Service UUID: `c5f50001-1234-5678-89ab-123456789abc`
- IP Characteristic UUID: `c5f50002-1234-5678-89ab-123456789abc`
- BLE Device name: `LeRobot-{IP}` (bijv. `LeRobot-192.168.1.100`)
- Read-only characteristic met UTF-8 encoded IP
- Automatische IP update elke 10 seconden
- Ondersteuning voor WiFi credential sharing (FR-1.4.2)

**Technology stack:**
- BlueZ D-Bus API via `dbus-next`
- GATT Manager API voor service registratie
- LE Advertising Manager voor BLE advertising

**Acceptatiecriteria:**
- Device zichtbaar binnen 5 seconden na scan
- IP correct leesbaar via Web Bluetooth API
- Service blijft actief na network change

#### FR-1.4.2: WiFi Credential Sharing
**Prioriteit:** COULD  
**Beschrijving:** Delen van WiFi credentials via BLE characteristic.

**Requirements:**
- Write characteristic voor SSID/password
- Automatische WiFi connect na credential receive
- Bevestiging via notification
- Timeout mechanisme (60 seconden)
- Security: credentials niet persistent opslaan

**Workflow:**
```
1. Client schrijft credentials naar characteristic
2. Server valideert format
3. Server connect naar WiFi
4. Server stuurt notification met status
5. BLE service stopt (optioneel)
```

#### FR-1.4.3: Web Bluetooth Scanner
**Prioriteit:** SHOULD  
**Beschrijving:** Browser-based BLE scanning voor robot discovery.

**Requirements:**
- Web Bluetooth API ondersteuning (Chrome/Edge)
- Automatisch scannen naar `LeRobot-*` devices
- IP parsing uit device name (fallback)
- GATT characteristic read voor betrouwbare IP
- Direct link naar web interface
- QR code generatie voor mobiele toegang

**Endpoints:**
```
GET /bluetooth - Scanner pagina
GET /qr - QR code generator
```

**Browser requirements:**
- Chrome 56+, Edge 79+, Opera 43+
- HTTPS of localhost context
- Bluetooth permissions granted

### 1.5 Visual Programming (Blockly)

#### FR-1.5.1: Custom Robot Blocks
**Prioriteit:** SHOULD  
**Beschrijving:** Blockly blocks voor robot control.

**Block types:**
- **Movement blocks:** `move_motor`, `move_all_motors`, `move_to_position`
- **Sensor blocks:** `get_motor_position`, `get_all_positions`
- **Control flow:** `wait`, `repeat`, `if_position_reached`
- **Recording:** `start_recording`, `stop_recording`, `playback`

**Code generation:**
- JavaScript → Python transpilatie
- Safety checks (motor limits, speed limits)
- Exception handling wrapper

#### FR-1.5.2: Program Management
**Prioriteit:** SHOULD  
**Beschrijving:** Opslaan, laden en uitvoeren van Blockly programma's.

**Requirements:**
- Opslag in `blockly_programs/` directory
- JSON format met workspace XML + Python code
- Lijst van beschikbare programma's
- Delete functionaliteit
- Execution sandbox met robot access

**API Endpoints:**
```
GET /api/blockly/programs - List programs
POST /api/blockly/programs/save - Save program
GET /api/blockly/programs/{name} - Load program
DELETE /api/blockly/programs/{name} - Delete
POST /api/blockly/execute - Execute code
```

**Program format:**
```json
{
  "name": "pick_and_place",
  "timestamp": "2024-12-02T10:30:00Z",
  "workspace": "<xml>...</xml>",
  "python_code": "robot.move_motor(...)",
  "description": "Pick and place demo"
}
```

#### FR-1.5.3: Safe Execution Environment
**Prioriteit:** MUST  
**Beschrijving:** Veilige Python code executie met robot toegang.

**Security requirements:**
- Beperkte namespace (geen `import`, `exec`, `eval`)
- Timeout mechanisme (30 seconden default)
- Exception handling
- Resource limits (geen infinite loops)
- Read-only file system access

**Exposed API:**
```python
class RobotAPI:
    def move_motor(motor_id, angle)
    def get_motor_position(motor_id)
    def wait(seconds)
    def move_to_position(positions)
```

### 1.6 Web Interface

#### FR-1.6.1: Responsive Design
**Prioriteit:** MUST  
**Beschrijving:** Modern, responsive web UI voor alle devices.

**Requirements:**
- Desktop, tablet en mobile ondersteuning
- Tab-based navigation: Teleoperation, Cameras, Network, Advanced
- Real-time status updates via WebSocket
- Gradient UI met smooth animations
- Toegankelijkheid: ARIA labels, keyboard navigation

**UI Components:**
- Status indicators (running/stopped)
- Device selection dropdowns
- Camera grid layout (1-4 cameras)
- Network scan results table
- Blockly workspace (drag & drop)
- Log viewer (real-time)

#### FR-1.6.2: Real-time Updates
**Prioriteit:** MUST  
**Beschrijving:** WebSocket-based live data streaming.

**Requirements:**
- WebSocket endpoint: `ws://host/ws`
- Automatische reconnect (5 seconden delay)
- Keepalive ping/pong (30 seconden)
- Broadcast naar meerdere clients
- JSON message format

**Message types:**
```json
{
  "type": "position_update",
  "data": {
    "rotation": 180,
    "pitch": 90,
    ...
  }
}

{
  "type": "status_update",
  "data": {
    "teleoperation_running": true,
    "cameras_active": 2
  }
}
```

#### FR-1.6.3: 3D Robot Viewer
**Prioriteit:** SHOULD  
**Beschrijving:** Real-time 3D visualisatie van robot pose.

**Requirements:**
- URDF-based rendering met Three.js
- urdf-loader voor mesh loading
- Real-time joint updates via WebSocket
- Interactive controls: orbit, pan, zoom
- Joint sliders voor manual control
- Reset naar home position (180° alle joints)
- Random pose generation

**Endpoints:**
```
GET /viewer - Robot viewer pagina
GET /static/URDFs/so101.urdf - Robot description
GET /static/URDFs/assets/*.stl - 3D meshes
```

**Camera setup:**
- Position: [-30, 10, 30]
- FOV: 12°
- Scale: 15x
- Lighting: ambient + 2× directional with shadows

---

## 2. Non-Functionele Requirements

### 2.1 Performance

#### NFR-2.1.1: Response Times
- API endpoints: < 100ms (p95)
- WebSocket messages: < 50ms latency
- Camera streams: 20-30 FPS
- Device detection: < 2 seconden
- Teleoperation startup: < 5 seconden
- Network scan: < 10 seconden

#### NFR-2.1.2: Resource Usage
- CPU: < 50% average (Raspberry Pi 4)
- Memory: < 1GB RAM voor webserver
- Disk: < 100MB voor applicatie (exclusief calibration)
- Bandwidth: ~500KB/s per camera stream

#### NFR-2.1.3: Concurrent Users
- Support voor 5 gelijktijdige web clients
- 10 WebSocket verbindingen
- 3 camera streams gelijktijdig
- Rate limiting: 6 requests/seconde per IP

### 2.2 Reliability

#### NFR-2.2.1: Uptime
- Target: 99% uptime per week
- Automatische herstart na crash
- Graceful degradation bij component failures
- Logging van alle errors naar `webserver.log`

#### NFR-2.2.2: Data Integrity
- Atomische device configuratie updates
- Transactionele program saves
- Backup van critical config files
- Calibration data version control

#### NFR-2.2.3: Error Handling
- Alle API endpoints met try/except
- User-friendly error messages
- HTTP status codes correct gebruikt
- Automatic recovery waar mogelijk

### 2.3 Security

#### NFR-2.3.1: API Security
**Current state:** Geen authenticatie (local network only)
**Recommendations:**
- Token-based authenticatie voor productie
- HTTPS support met TLS certificates
- CORS policy configuratie
- Rate limiting per IP (geïmplementeerd)
- Input validatie met Pydantic

#### NFR-2.3.2: Network Security
- Firewall configuratie (poort 80 local only)
- AP mode WPA2 encryption
- Geen credentials in plaintext logs
- Secure credential storage (WiFi passwords)

#### NFR-2.3.3: Code Execution Safety
- Blockly code sandbox
- Beperkte Python namespace
- Timeout mechanisme
- No shell command injection
- Input sanitization

### 2.4 Maintainability

#### NFR-2.4.1: Code Quality
- Type hints voor alle functies (Python 3.10+)
- Docstrings voor classes en functies
- Logging levels: DEBUG, INFO, WARNING, ERROR
- Error messages met context
- Modular architecture

#### NFR-2.4.2: Documentation
- README files per feature (FEATURES.md, BLUETOOTH_README.md, etc.)
- API documentatie via FastAPI `/docs` endpoint
- Inline comments voor complexe logica
- Architecture diagrams
- Installation guide (install.sh)

#### NFR-2.4.3: Testability
- Unit test support (pytest framework)
- Integration test endpoints
- Mock support voor hardware
- Test mode without physical robots
- CI/CD ready (GitHub Actions)

### 2.5 Compatibility

#### NFR-2.5.1: Hardware Platforms
**Supported:**
- Raspberry Pi 4/5 (primary)
- ARM64 Linux boards
- x86_64 Linux (development)

**Tested:**
- Raspberry Pi OS (Bullseye, Bookworm)
- Ubuntu 22.04 LTS

#### NFR-2.5.2: Robot Types
- SO-101 (default, fully tested)
- Koch hand
- RoArm
- Custom types via LeRobot plugin system

#### NFR-2.5.3: Browsers
**Full support:**
- Chrome 90+
- Edge 90+
- Opera 76+

**Partial support (no Web Bluetooth):**
- Firefox 88+ (WebSocket + camera streaming)
- Safari 14+ (limited WebSocket)

---

## 3. Hardware Requirements

### 3.1 Compute Platform

#### Minimum specifications:
- **CPU:** ARM Cortex-A72 (Raspberry Pi 4) or equivalent
- **RAM:** 2GB minimum, 4GB recommended
- **Storage:** 16GB SD card minimum
- **OS:** Linux with kernel 5.10+ (udev, NetworkManager support)
- **Network:** WiFi adapter (AP mode support)
- **Bluetooth:** BLE 4.0+ adapter (optional for discovery)

#### Recommended:
- Raspberry Pi 4B (4GB RAM) or Raspberry Pi 5
- 32GB SD card Class 10
- Active cooling (heatsink + fan)
- Stable 5V 3A power supply

### 3.2 Robot Hardware

#### Followers (robots die commando's uitvoeren):
- USB serial interface (115200 baud default)
- Feetech servo motors (SCS series)
- 5-6 DOF arm configuration
- Unique USB serial number voor device mapping

#### Leaders (teleoperators voor input):
- Identieke hardware als follower
- Backdriveable motors (voor manual control)
- Identical kinematic structure
- Calibration met follower gesynchroniseerd

### 3.3 Peripherals

#### Cameras:
- USB webcam (UVC compatible)
- Resolution: 640×480 minimum
- Frame rate: 30 FPS
- V4L2 driver support (Linux)
- Multiple cameras supported (USB hub)

#### Network devices:
- WiFi adapter: IEEE 802.11n minimum
- Bluetooth: BLE 4.0 adapter (optional)
- Ethernet: 100Mbps (optional)

---

## 4. Software Dependencies

### 4.1 Core Dependencies

```python
# Robot framework
lerobot[so101, koch, roarm]==1.0+

# Web framework
fastapi==0.100.0+
uvicorn[standard]==0.23.0+
pydantic==2.0+
websockets==11.0+
python-multipart==0.0.6+

# Camera & image processing
opencv-python==4.8.0+
numpy==1.24.0+

# Bluetooth (optional)
dbus-next==0.2.3+
netifaces==0.11.0+

# Utilities
draccus  # Configuration management
```

### 4.2 System Dependencies (Linux)

```bash
# Robot communication
python3.10+
miniconda3 (conda environment)

# Network management
network-manager
nmcli
hostapd
dnsmasq
iptables

# Bluetooth
bluez (5.50+)
bluetooth
libdbus-1-dev

# Device management
udev
systemd

# Build tools
gcc
make
python3-dev
```

### 4.3 Optional Dependencies

```python
# Development
pytest==7.4.0+
pytest-asyncio==0.21.0+
black  # Code formatting
mypy   # Type checking

# Production
gunicorn  # WSGI server alternative
nginx     # Reverse proxy
certbot   # HTTPS certificates
```

---

## 5. Installation Requirements

### 5.1 Installatie Process

#### Automated via install.sh:
```bash
./install.sh [--lerobot-src PATH] [--lerobot-git URL] [--lerobot-branch BRANCH]
```

**Steps uitgevoerd:**
1. Download en installeer Miniconda (architecture-aware)
2. Creëer conda environment `lerobot` met Python 3.12
3. Installeer lerobot package (PyPI, lokaal, of git)
4. Installeer alle dependencies (FastAPI, OpenCV, etc.)
5. Installeer system packages (Bluetooth, Network tools)
6. Download udev rules van GitHub release
7. Installeer udev rules naar `/etc/udev/rules.d/`
8. Import calibration files naar `~/.cache/huggingface/lerobot/`
9. Configureer crontab voor auto-start
10. Activeer conda environment

**Installation time:** ~10-15 minuten (afhankelijk van internet)

### 5.2 Post-Installation

#### Verificatie:
```bash
# Check conda environment
conda activate lerobot
python -c "import lerobot; print('OK')"

# Check device symlinks
ls -la /dev/tty_*

# Check webserver
python webserver.py  # Should start zonder errors

# Check web interface
curl http://localhost/health
```

#### Configuration:
```bash
# Device selection (interactive)
./select_teleop.py

# Reset naar defaults
./select_teleop.py --reset

# Export calibration
./sync_calibration.sh export

# Import calibration
./sync_calibration.sh import
```

### 5.3 Auto-Start Configuratie

#### Crontab entry (automatisch toegevoegd):
```cron
@reboot sleep 5 && cd /home/kwijk/localdata/teleop_lerobot && /home/kwijk/miniconda3/condabin/conda run -n lerobot python webserver.py >> /home/kwijk/webserver.log 2>&1
```

**Gedrag:**
- Wacht 5 seconden na boot (voor system services)
- Activeer conda environment
- Start webserver in background
- Redirect output naar `~/webserver.log`
- Detect devices automatisch
- Start teleoperation als devices aanwezig

---

## 6. Configuratie Requirements

### 6.1 Mapping Configuration (mapping.csv)

**Format:**
```csv
SERIAL_SHORT,NICE_NAME,ROLE,TYPE
58FA083461,white_12,follower,so101
8CAFC04501DAEF,black,leader,so101
```

**Fields:**
- **SERIAL_SHORT:** USB device serial (8-32 chars alfanumeriek)
- **NICE_NAME:** Unieke identifier (lowercase, letters/cijfers/underscores)
- **ROLE:** `follower` of `leader`
- **TYPE:** Robot model (`so101`, `roarm`, `koch`, etc.)

**Constraints:**
- NICE_NAME moet uniek zijn binnen role+type combinatie
- NICE_NAME moet matchen met calibration filename
- SERIAL_SHORT moet exact overeenkomen met USB device
- TYPE moet ondersteund worden door LeRobot

### 6.2 Udev Rules

**Location:** `/etc/udev/rules.d/99-usb-serial-aliases.rules`

**Format:**
```udev
SUBSYSTEM=="tty", ENV{ID_BUS}=="usb", ENV{ID_SERIAL_SHORT}=="58FA083461", SYMLINK+="tty_white_12_follower_so101", SYMLINK+="tty_follower"
```

**Generated by:** `gen_udev_rules.py mapping.csv`

**Reload command:**
```bash
sudo udevadm control --reload
sudo udevadm trigger
```

### 6.3 Calibration Files

**Location:** `~/.cache/huggingface/lerobot/calibration/`

**Structure:**
```
calibration/
├── robots/
│   └── so101_follower/
│       ├── white_12.json
│       └── blue.json
└── teleoperators/
    └── so101_leader/
        ├── black.json
        └── yellow.json
```

**Format (JSON):**
```json
{
  "homing_offset": [0, 0, 0, 0, 0, 0],
  "drive_mode": [1, 1, 1, 1, 1, 1],
  "motor_id": [1, 2, 3, 4, 5, 6],
  "start_pos": [2048, 2048, 2048, 2048, 2048, 2048],
  "end_pos": [2048, 2048, 2048, 2048, 2048, 2048]
}
```

**Sync command:**
```bash
./sync_calibration.sh export  # Git → cache
./sync_calibration.sh import  # Cache → git
```

### 6.4 Device Defaults

**Location:** `~/.lerobot_device_defaults.json`

**Format:**
```json
{
  "follower_port": "/dev/tty_white_12_follower_so101",
  "follower_type": "so101",
  "follower_id": "white_12",
  "leader_port": "/dev/tty_black_leader_so101",
  "leader_type": "so101",
  "leader_id": "black"
}
```

**Management:**
- Automatisch opgeslagen na device selectie
- Geladen bij webserver startup
- Reset via `rm ~/.lerobot_device_defaults.json`

### 6.5 Network Configuration

#### Access Point mode:
**Config:** `/tmp/hostapd.conf`
```ini
interface=wlan0
driver=nl80211
ssid=LeRobot-AP
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
wpa=2
wpa_passphrase=robotics123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
```

**DHCP:** `/tmp/dnsmasq.conf`
```ini
interface=wlan0
dhcp-range=192.168.4.50,192.168.4.150,255.255.255.0,24h
domain=local
address=/router.local/192.168.4.1
```

#### WiFi client mode:
**Managed by:** NetworkManager (nmcli)
```bash
nmcli dev wifi connect SSID password PASSWORD
```

---

## 7. API Requirements (Complete Specification)

### 7.1 RESTful Endpoints

#### 7.1.1 Core System
```
GET /                   - Web UI root
GET /health            - Health check (returns {"status": "ok"})
GET /api               - API info (version, features)
```

#### 7.1.2 Teleoperation
```
POST /api/teleoperation/start
  Body: {follower_port, follower_type, follower_id, leader_port, leader_type, leader_id}
  Response: {success, message}
  
POST /api/teleoperation/stop
  Response: {success, message}
  
GET /api/teleoperation/current-position
  Response: {rotation, pitch, elbow, wrist_pitch, wrist_roll, jaw, timestamp}
  Cache: 50ms
  
POST /api/teleoperation/save-current-position
  Body: {name}
  Response: {success, position}
  
POST /api/teleoperation/leader/command
  Body: {command, motor_id?, angle?, speed?}
  Response: {success, message}
```

#### 7.1.3 Devices
```
GET /api/devices
  Response: {followers: [...], leaders: [...]}
  
GET /api/devices/defaults
  Response: {follower_port, follower_type, ...}
  
POST /api/devices/defaults
  Body: {follower_port, follower_type, ...}
  Response: {success}
```

#### 7.1.4 Cameras
```
GET /api/cameras
  Response: {cameras: [{name, index, active, resolution, fps, frame_count}]}
  
GET /api/cameras/{name}/stream
  Response: multipart/x-mixed-replace MJPEG stream
  
POST /api/cameras/detect
  Response: {cameras_found, count}
```

#### 7.1.5 Network
```
GET /api/network/status
  Response: {mode, ip, ssid, signal_strength, interface}
  
POST /api/network/ap/start
  Body: {ssid?, password?}
  Response: {success, ip}
  
POST /api/network/ap/stop
  Response: {success}
  
POST /api/network/wifi/connect
  Body: {ssid, password}
  Response: {success, ip}
  
GET /api/network/wifi/scan
  Response: {networks: [{ssid, signal, security}]}
  
POST /api/network/disconnect
  Response: {success}
```

#### 7.1.6 Bluetooth
```
GET /api/bluetooth/status
  Response: {running, device_name, ip_address}
  
GET /api/bluetooth/ip
  Response: {ip}
  
POST /api/bluetooth/start
  Response: {success}
  
POST /api/bluetooth/stop
  Response: {success}
```

#### 7.1.7 Blockly
```
GET /api/blockly/blocks
  Response: JavaScript block definitions
  
GET /api/blockly/programs
  Response: {programs: [{name, timestamp}]}
  
POST /api/blockly/programs/save
  Body: {name, workspace_xml, python_code}
  Response: {success, filename}
  
GET /api/blockly/programs/{name}
  Response: {name, workspace_xml, python_code, timestamp}
  
DELETE /api/blockly/programs/{name}
  Response: {success}
  
POST /api/blockly/execute
  Body: {code}
  Response: {success, output, error?}
```

### 7.2 WebSocket Protocol

#### Connection:
```
ws://host/ws
```

#### Message format (JSON):
```json
{
  "type": "position_update" | "status_update" | "camera_update" | "network_update",
  "timestamp": "2024-12-02T10:30:00Z",
  "data": { ... }
}
```

#### Position update:
```json
{
  "type": "position_update",
  "data": {
    "rotation": 180.5,
    "pitch": 90.2,
    "elbow": 135.7,
    "wrist_pitch": 180.0,
    "wrist_roll": 225.3,
    "jaw": 170.1
  }
}
```

#### Status update:
```json
{
  "type": "status_update",
  "data": {
    "teleoperation_running": true,
    "cameras_active": 2,
    "network_mode": "ap",
    "bluetooth_active": true
  }
}
```

#### Keepalive:
- Interval: 30 seconden
- Server → Client: `{"type": "ping"}`
- Client → Server: `{"type": "pong"}`

---

## 8. Test Requirements

### 8.1 Unit Tests

**Coverage target:** 80% code coverage

**Test suites:**
- `test_camera_manager.py` - Camera detection, streaming
- `test_network_manager.py` - AP/WiFi mode switching
- `test_teleoperation_manager.py` - Robot control
- `test_bluetooth_gatt.py` - BLE advertising
- `test_blockly_manager.py` - Code execution

### 8.2 Integration Tests

**Scenarios:**
1. **Full startup flow:** Boot → device detection → teleoperation start
2. **Camera streaming:** Detect → start → stream → stop
3. **Network switching:** WiFi → AP mode → WiFi
4. **Blockly execution:** Load program → execute → verify position
5. **WebSocket:** Connect → subscribe → receive updates → disconnect

### 8.3 Hardware Tests

**Requirements:**
- Test met physical robot (follower + leader)
- Meerdere camera's testen
- WiFi connection op verschillende netwerken
- BLE advertising op verschillende devices
- USB disconnect/reconnect handling

### 8.4 Performance Tests

**Load testing:**
- 5 concurrent web clients
- 10 WebSocket connections
- 3 camera streams gelijktijdig
- Rate limiting verificatie

**Stress testing:**
- 24-hour uptime test
- Repeated start/stop cycles (100×)
- Network disconnect/reconnect loops
- Camera hot-plug testing

---

## 9. Deployment Requirements

### 9.1 Production Checklist

**Security:**
- [ ] Change default AP password
- [ ] Enable HTTPS (certbot + nginx)
- [ ] Implement API authentication
- [ ] Configure firewall (ufw)
- [ ] Disable SSH password auth
- [ ] Update all packages

**Performance:**
- [ ] Enable camera hardware acceleration
- [ ] Optimize JPEG encoding quality
- [ ] Configure swap size (2GB voor Pi)
- [ ] Disable desktop environment
- [ ] Use uvicorn with workers

**Monitoring:**
- [ ] Setup log rotation (logrotate)
- [ ] Configure systemd service
- [ ] Enable watchdog timer
- [ ] Setup remote monitoring
- [ ] Configure email alerts

### 9.2 Backup & Recovery

**Backup targets:**
- Configuration files: `mapping.csv`, device defaults, calibration
- Blockly programs: `blockly_programs/`
- Custom network configs: hostapd.conf, dnsmasq.conf
- Udev rules: `/etc/udev/rules.d/99-*`

**Backup frequency:**
- Daily: configuration files
- Weekly: full SD card image
- On change: calibration files (git commit)

**Recovery procedure:**
1. Flash fresh SD card met Raspberry Pi OS
2. Run `install.sh` vanaf repository
3. Restore configuration backups
4. Reload udev rules
5. Reboot
6. Verify all services running

### 9.3 Update Process

**Update strategy:**
```bash
# 1. Backup huidige configuratie
tar czf backup-$(date +%Y%m%d).tar.gz \
  mapping.csv calibration/ ~/.lerobot*

# 2. Pull nieuwe code
git pull origin main

# 3. Update dependencies
conda activate lerobot
pip install -r requirements.txt --upgrade

# 4. Update udev rules (indien gewijzigd)
python gen_udev_rules.py mapping.csv
sudo mv 99-usb-serial-aliases.rules /etc/udev/rules.d/
sudo udevadm control --reload

# 5. Restart service
sudo systemctl restart lerobot-webserver

# 6. Verify
curl http://localhost/health
```

---

## 10. Compliance & Standards

### 10.1 Code Standards

**Python:**
- PEP 8 code style
- Type hints (Python 3.10+)
- Docstrings (Google style)
- Black formatting
- MyPy type checking

**JavaScript:**
- ES6+ syntax
- JSDoc comments
- Prettier formatting
- ESLint rules

### 10.2 API Standards

- RESTful principles
- HTTP status codes correct gebruikt
- JSON responses only
- Consistent naming (snake_case)
- Versioning via URL path (v1, v2)

### 10.3 Documentation Standards

- Markdown format (*.md files)
- Code examples voor alle features
- API endpoint documentation
- Troubleshooting guides
- Architecture diagrams (ASCII art)

### 10.4 Security Standards

- OWASP Top 10 compliance
- Input validation (Pydantic)
- Output encoding
- Secure defaults
- Rate limiting
- HTTPS ready

---

## 11. Future Requirements (Roadmap)

### 11.1 Short-term (v2.1 - Q1 2025)

**Geplande features:**
- [ ] **Authentication system** - Token-based API auth
- [ ] **HTTPS support** - SSL certificates met certbot
- [ ] **Multi-robot support** - Control meerdere robots tegelijk
- [ ] **Recording & playback** - Save teleoperation sessions
- [ ] **Mobile app** - React Native companion app
- [ ] **Data logging** - Joint positions, forces, timestamps

### 11.2 Mid-term (v2.5 - Q2 2025)

**Geplande features:**
- [ ] **Inverse kinematics** - Click-to-move end-effector
- [ ] **Trajectory optimization** - Smooth path planning
- [ ] **Force feedback** - Haptic feedback via leader
- [ ] **Vision-based control** - Camera-guided movements
- [ ] **Multi-user collaboration** - Meerdere operators
- [ ] **Cloud sync** - Backup naar cloud storage

### 11.3 Long-term (v3.0 - Q3 2025)

**Geplande features:**
- [ ] **AI co-pilot** - LLM-assisted robot control
- [ ] **VR/AR support** - Immersive teleoperation
- [ ] **Simulation mode** - Test zonder hardware
- [ ] **Fleet management** - Manage 10+ robots
- [ ] **Custom robot plugins** - Third-party robot support
- [ ] **Advanced analytics** - Performance metrics dashboard

---

## 12. Referenties & Links

### 12.1 Externe Dependencies

- **LeRobot:** https://github.com/huggingface/lerobot
- **FastAPI:** https://fastapi.tiangolo.com
- **OpenCV:** https://opencv.org
- **Three.js:** https://threejs.org
- **Blockly:** https://developers.google.com/blockly
- **BlueZ:** http://www.bluez.org

### 12.2 Documentation

- **Web Bluetooth API:** https://webbluetoothcg.github.io/web-bluetooth/
- **URDF Specification:** http://wiki.ros.org/urdf
- **NetworkManager:** https://networkmanager.dev
- **D-Bus API:** https://dbus.freedesktop.org

### 12.3 Internal Docs

- `README_TELEOP.md` - Teleoperation guide
- `FEATURES.md` - Feature overview
- `BLUETOOTH_README.md` - Bluetooth setup
- `ROBOT_VIEWER_README.md` - 3D viewer guide
- `MAPPING.md` - Device mapping documentation
- `UPGRADE_SUMMARY.md` - Version changelog

---

## 13. Contact & Support

**Repository:** https://github.com/koenvanwijk/teleop_lerobot

**Issues:** Open een GitHub issue voor bugs of feature requests

**Logs:**
- Webserver: `~/webserver.log`
- Teleoperation: `~/teleoperation.log`
- System: `journalctl -u lerobot-webserver`

**Debug mode:**
```bash
export DEBUG=1
python webserver.py
```

---

**Document versie:** 1.0.0  
**Laatste update:** December 2024  
**Status:** Complete Requirements Specification ✅
