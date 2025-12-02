# LeRobot Teleoperation Server - Feature Overview

## 🚀 Version 2.0.0 - Extended Features

Deze versie bevat uitgebreide functionaliteit geïnspireerd op de teleop_local_robot server.

### ✨ Nieuwe Features

#### 1. 📹 Camera Streaming
- **Multi-camera support**: Automatische detectie van meerdere camera's
- **MJPEG streaming**: Real-time video streams via HTTP
- **Camera management**: Start/stop individuele camera's
- **Performance monitoring**: Frame rate, resolution en statistics
- **Web interface**: Live preview van alle camera's in grid layout

**API Endpoints:**
- `GET /api/cameras` - Lijst van beschikbare camera's
- `GET /api/cameras/{name}/stream` - MJPEG stream van camera
- `POST /api/cameras/detect` - Detecteer beschikbare camera's

**Gebruik:**
```python
# Camera manager wordt automatisch geïnitialiseerd bij startup
# Streams zijn beschikbaar via /api/cameras/{name}/stream
```

#### 2. 🌐 Network Management
- **Access Point mode**: Start Raspberry Pi als WiFi hotspot
- **WiFi client mode**: Verbind met bestaande WiFi netwerken
- **Network scanning**: Scan beschikbare WiFi netwerken
- **Status monitoring**: IP adres, signaalsterkte, verbindingsstatus
- **Naadloos switchen**: Tussen AP en WiFi mode

**API Endpoints:**
- `GET /api/network/status` - Huidige network status
- `POST /api/network/ap/start` - Start Access Point
- `POST /api/network/ap/stop` - Stop Access Point
- `POST /api/network/wifi/connect` - Verbind met WiFi
- `GET /api/network/wifi/scan` - Scan WiFi netwerken
- `POST /api/network/disconnect` - Disconnect van network

**Gebruik:**
```bash
# AP Mode configuratie
AP SSID: LeRobot-AP
AP Password: robotics123
AP IP: 192.168.4.1
```

#### 3. 🔌 WebSocket Support
- **Real-time updates**: Bidirectionele communicatie
- **Status broadcasts**: Automatische status updates naar alle clients
- **Keepalive**: Automatische verbinding health check
- **Multiple clients**: Support voor meerdere gelijktijdige verbindingen

**API Endpoint:**
- `WS /ws` - WebSocket endpoint voor real-time updates

**Gebruik:**
```javascript
const ws = new WebSocket('ws://localhost:5000/ws');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Status update:', data);
};
```

#### 4. 🎨 Moderne Web Interface
- **Tab-based navigation**: Teleoperation, Cameras, Network, System
- **Responsive design**: Werkt op desktop, tablet en mobile
- **Real-time updates**: Live status monitoring via WebSocket
- **Modern UI**: Gradient backgrounds, smooth animations
- **Status indicators**: Visual feedback voor alle componenten

**Features:**
- 🎮 **Teleoperation tab**: Start/stop control, device status
- 📹 **Cameras tab**: Live streams, detection, statistics
- 🌐 **Network tab**: AP/WiFi management, scanning, connection
- ⚙️ **System tab**: Server info, API endpoints, documentation

### 📦 Dependencies

Nieuwe packages toegevoegd:
- `opencv-python` - Camera capture en streaming
- `numpy` - Image processing
- `fastapi` - Modern async web framework
- `uvicorn[standard]` - ASGI server
- `pydantic` - Data validation
- `websockets` - WebSocket support
- `python-multipart` - Form data handling

### 🗂️ Project Structuur

```
teleop_lerobot/
├── webserver.py              # Hoofd FastAPI server (uitgebreid)
├── camera_manager.py         # Camera streaming management (NIEUW)
├── network_manager.py        # Network configuration (NIEUW)
├── templates/
│   └── index.html           # Web interface template (NIEUW)
├── install.sh               # Installatie script (updated)
├── select_teleop.py         # Device selectie
├── gen_udev_rules.py        # Udev rules generator
├── mapping.csv              # Device mappings
└── calibration/             # Calibratie bestanden
    ├── robots/
    └── teleoperators/
```

### 🚀 Gebruik

#### Basis Teleoperation (ongewijzigd)
```bash
# Auto-start bij boot via crontab
# OF handmatig:
uvicorn webserver:app --host 0.0.0.0 --port 5000
```

#### Camera Streaming
```bash
# Cameras worden automatisch gedetecteerd bij startup
# Bekijk streams op: http://localhost:5000
# Tab: Cameras → Live camera feeds
```

#### Network Management
```bash
# Via web interface:
# Tab: Network → Start Access Point / Scan WiFi
```

#### API Documentatie
```bash
# Interactive API docs:
http://localhost:5000/docs
http://localhost:5000/redoc

# API info:
http://localhost:5000/api

# Health check:
http://localhost:5000/health
```

### 🔧 Configuratie

#### Camera Configuratie
Cameras worden automatisch gedetecteerd. Handmatige configuratie via code:
```python
camera_configs = [
    {'index': 0, 'name': 'Camera 0', 'resolution': [640, 480], 'fps': 30},
    {'index': 1, 'name': 'Camera 1', 'resolution': [640, 480], 'fps': 30},
]
```

#### Network Configuratie
```python
network_manager = NetworkManager(
    ap_ssid="LeRobot-AP",
    ap_password="robotics123",  # Min 8 characters
    interface="wlan0"
)
```

### 📊 System Requirements

#### Hardware
- Raspberry Pi 4/5 (aanbevolen voor camera streaming)
- USB camera('s) voor video streaming
- WiFi interface voor network management

#### Software
- Raspbian/Ubuntu Linux
- Python 3.10+
- NetworkManager (voor WiFi management)
- hostapd + dnsmasq (voor Access Point mode)

### 🐛 Troubleshooting

#### Camera niet gevonden
```bash
# Check beschikbare cameras:
ls -la /dev/video*

# Test camera:
python -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL')"
```

#### Network management werkt niet
```bash
# Check NetworkManager:
systemctl status NetworkManager

# Installeer dependencies:
sudo apt-get install network-manager hostapd dnsmasq

# Check interface:
ip addr show wlan0
```

#### WebSocket disconnect
- WebSocket reconnect automatisch na 5 seconden
- Check firewall settings
- Verify port 5000 is not blocked

### 🔮 Toekomstige Features (Ready to Add)

De huidige architectuur is klaar voor:
- 🎯 **Blockly visual programming** - Drag & drop robot control
- 🎬 **Recording & playback** - Record teleoperation sessions
- 📈 **Data logging** - Joint positions, forces, trajectories
- 🌍 **Multi-robot support** - Control meerdere robots tegelijk
- 🎮 **3D simulation viewer** - Visualiseer robot in 3D
- 📱 **Mobile app integration** - Native iOS/Android apps
- 🔐 **Authentication** - User login en access control

### 📝 Changelog

**v2.0.0** (December 2024)
- ✅ FastAPI migration (was Flask)
- ✅ Camera streaming met MJPEG
- ✅ Network management (AP/WiFi)
- ✅ WebSocket real-time updates
- ✅ Moderne tab-based web interface
- ✅ Multi-camera support
- ✅ Async/await architecture
- ✅ Improved error handling
- ✅ System information page
- ✅ API documentation (Swagger/ReDoc)

**v1.0.0** (November 2024)
- ✅ Basic teleoperation control
- ✅ Device auto-detection
- ✅ Udev rules generation
- ✅ Calibration management
- ✅ Auto-start bij boot

### 📚 Documentation Links

- **Web Interface**: http://localhost:5000
- **API Docs (Swagger)**: http://localhost:5000/docs
- **API Docs (ReDoc)**: http://localhost:5000/redoc
- **Health Check**: http://localhost:5000/health
- **GitHub**: https://github.com/koenvanwijk/raspberry5_lerobot

### 🤝 Contributing

Gebaseerd op:
- [LeRobot](https://github.com/huggingface/lerobot) - Hugging Face robotics
- teleop_local_robot - Advanced teleoperation server reference

### 📧 Support

Voor vragen of problemen:
- Check logs: `~/webserver.log` en `~/teleoperation.log`
- Open een issue op GitHub
- Check de API documentatie op `/docs`

---

**🎉 Enjoy your enhanced teleoperation experience!**
