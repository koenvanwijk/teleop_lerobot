# Bluetooth IP Service voor LeRobot

Deze module biedt een Bluetooth Low Energy (BLE) dienst die het IP-adres van de robot adverteert in de device naam. Zo kun je de robot vinden via Bluetooth scanning en het IP-adres direct zien.

**Functionaliteit:** Het IP-adres wordt opgenomen in de BLE device naam, bijvoorbeeld: `LeRobot-IP-192.168.1.100`

## Hoe het werkt

1. De BLE service maakt het apparaat discoverable via Bluetooth
2. Het IP-adres wordt getoond in de device naam
3. Scan voor Bluetooth apparaten met je telefoon/laptop
4. Zoek naar "LeRobot-IP-xxx.xxx.xxx.xxx"
5. Het IP-adres staat in de naam - gebruik dit om via HTTP te verbinden

## Installatie

### Dependencies Installeren

De Bluetooth service gebruikt `dbus-next` voor communicatie met BlueZ:

```bash
# Ubuntu/Raspberry Pi
sudo apt-get update
sudo apt-get install -y bluetooth bluez
pip install dbus-next netifaces
```

### Verificatie

```bash
# Check of bluetooth service draait
sudo systemctl status bluetooth

# Start bluetooth als het niet draait
sudo systemctl start bluetooth

# Verifieer dbus-next import
python3 -c "import dbus_next; print('D-Bus OK')"

# Test Bluetooth discovery
bluetoothctl scan on
# Je zou "LeRobot-IP-xxx.xxx.xxx.xxx" moeten zien
```

## Gebruik

### Via Web Interface

1. Open de web interface: `http://<robot-ip>:8000`
2. Ga naar **Advanced** tab → **System** sub-tab  
3. Scroll naar **📡 Bluetooth IP Service** sectie
4. Klik op **▶️ Start Service** om BLE advertising te starten
5. Het apparaat is nu discoverable als "LeRobot-IP-xxx.xxx.xxx.xxx"

### Vanaf Mobiel Apparaat

**Methode 1: Web Bluetooth Scanner (Aanbevolen)**

Open op je telefoon (Chrome browser vereist):
```
http://<bekende-ip>:8000/bluetooth
```

Of als je de robot nog niet hebt gevonden, ga naar een andere computer op hetzelfde netwerk en open:
```
http://localhost:8000/bluetooth
```

De webpagina gebruikt Web Bluetooth API om:
1. Automatisch te scannen naar LeRobot apparaten
2. Het IP-adres uit de device naam te halen
3. Direct door te linken naar de web interface

**Methode 2: Handmatig via Bluetooth Instellingen**

**Stap 1: Scan voor Bluetooth apparaten**
- Open Bluetooth instellingen op je telefoon
- Scan naar nieuwe apparaten
- Zoek naar "LeRobot-IP-xxx.xxx.xxx.xxx"
- Het IP-adres staat in de naam!

**Stap 2: Verbind via browser**
- Open browser op je telefoon
- Ga naar `http://xxx.xxx.xxx.xxx:8000` (gebruik IP uit device naam)
- Je bent nu verbonden met de robot!

### Van Linux/Mac Terminal

```bash
# Scan voor Bluetooth apparaten
bluetoothctl scan on

# Output toont:
# [NEW] Device XX:XX:XX:XX:XX:XX LeRobot-IP-192.168.1.100
#                                  ^^^^^^^^^ Hier staat het IP!

# Gebruik dit IP om te verbinden
curl http://192.168.1.100:8000/api/status
```

### Bluetooth Permissies (Optioneel)

Voor non-root toegang tot Bluetooth:

```bash
sudo usermod -a -G bluetooth $USER
# Log uit en weer in
```

## Gebruik

### Via Web Interface

1. Open de web interface: `http://<robot-ip>:8000`
2. Ga naar **Advanced** tab → **System** sub-tab
3. Scroll naar **Bluetooth IP Service** sectie
4. Klik op **▶️ Start Service** om de Bluetooth service te starten
5. De service is nu discoverable als "LeRobot IP Service"

### Via API

```python
import requests

# Start BLE advertising
response = requests.post('http://<robot-ip>:8000/api/bluetooth/start')
print(response.json())
# Output: {"success": True, "message": "Bluetooth service started"}

# Get status
response = requests.get('http://<robot-ip>:8000/api/bluetooth/status')
data = response.json()
print(f"BLE Device Name: {data['ble_device_name']}")
# Output: BLE Device Name: LeRobot-IP-192.168.1.100

# Get IP address (if you already know the IP)
response = requests.get('http://<robot-ip>:8000/api/bluetooth/ip')
print(response.json())
# Output: {"primary_ip": "192.168.1.100", "all_ips": {"wlan0": "192.168.1.100"}}
```

## Automatisch Starten

De Bluetooth manager initialiseert automatisch wanneer de webserver opstart (indien Bleak geïnstalleerd is). De service biedt IP query functionaliteit via HTTP API.

Om dit uit te schakelen, verwijder de Bluetooth initialisatie code in `webserver.py`:

```python
# In lifespan functie, verwijder:
if BLUETOOTH_AVAILABLE:
    logger.info("📡 Initializing Bluetooth service...")
    # ... rest van code
```

## Troubleshooting

### Bleak Import Errors

```bash
# Installeer bluetooth system packages
sudo apt-get install -y bluetooth bluez

# Herstart bluetooth service
sudo systemctl restart bluetooth

# Verificatie
python3 -c "import bleak; print('Bleak OK')"
```

### Bluetooth Service Draait Niet

```bash
# Check status
sudo systemctl status bluetooth

# Start service
sudo systemctl start bluetooth
sudo systemctl enable bluetooth

# Check bluetooth devices
hciconfig
bluetoothctl show
```

## API Endpoints

- `GET /api/bluetooth/status` - Status van Bluetooth service
- `GET /api/bluetooth/ip` - Huidig IP adres
- `POST /api/bluetooth/start` - Start Bluetooth service
- `POST /api/bluetooth/stop` - Stop Bluetooth service

## Technische Details

- **Library**: Bleak (Bluetooth Low Energy)
- **Protocol**: HTTP API voor IP queries
- **Service Name**: "LeRobot-IP"
- **Data Format**: JSON via HTTP endpoints

## Security Overwegingen

⚠️ **Let op**: De HTTP API endpoints zijn zonder authenticatie. Voor productie gebruik:

1. Implementeer API token authenticatie
2. Gebruik HTTPS in plaats van HTTP
3. Implementeer rate limiting
4. Firewall configuratie voor toegangscontrole

## Geavanceerd Gebruik

### mDNS Service Discovery

Voor automatische robot discovery op het netwerk, gebruik Avahi/Bonjour:

```bash
# Installeer Avahi voor mDNS
sudo apt-get install -y avahi-daemon avahi-utils

# Check service
avahi-browse -a

# Vanaf client: zoek LeRobot
avahi-browse -r _http._tcp
```

### Custom Device Name

Pas de device naam aan in `bluetooth_manager.py`:

```python
bluetooth_mgr = BluetoothManager(
    service_name="My-Robot-Name"
)
```

### Netwerk Interface Selectie

De service detecteert automatisch alle netwerk interfaces. Om een specifieke interface te gebruiken:

```python
# Direct IP query voor specifieke interface
import netifaces
ip = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
```

## Licentie

Onderdeel van LeRobot Teleoperation System.
