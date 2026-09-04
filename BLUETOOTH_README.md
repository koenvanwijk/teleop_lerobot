# Bluetooth IP Service voor LeRobot

Deze module biedt een Bluetooth Low Energy (BLE) GATT service die het IP-adres van de robot adverteert via BLE advertising en een GATT characteristic. Zo kun je de robot vinden via Bluetooth scanning en het IP-adres uitlezen.

**Functionaliteit:** 
- IP-adres in BLE device naam: `LeRobot-192.168.1.100`
- IP-adres via GATT characteristic: leesbaar via Web Bluetooth API
- Automatisch geüpdatet IP-adres elke 10 seconden

## Hoe het werkt

1. De BLE GATT service registreert een custom GATT service bij BlueZ
2. Een GATT characteristic bevat het IP-adres als UTF-8 bytes (read-only)
3. BLE advertising adverteert de service UUID en device naam met IP
4. Clients kunnen scannen naar "LeRobot-" apparaten
5. IP is zichtbaar in device naam én leesbaar via GATT characteristic
6. Web Bluetooth scanner kan direct het IP lezen en doorlinken

## Technische Architectuur

### BLE GATT Service
- **Service UUID**: `c5f50001-1234-5678-89ab-123456789abc`
- **IP Characteristic UUID**: `c5f50002-1234-5678-89ab-123456789abc` (read-only)
- **Advertising**: LocalName met IP, Service UUID list
- **Protocol**: BlueZ D-Bus API via `dbus-next`

### BlueZ GATT Manager API
De implementatie gebruikt de officiële BlueZ GATT Manager API:
- `org.bluez.GattManager1.RegisterApplication` - GATT service registratie
- `org.bluez.LEAdvertisingManager1.RegisterAdvertisement` - BLE advertising
- `org.bluez.GattCharacteristic1` - Read-only IP characteristic
- `org.freedesktop.DBus.ObjectManager` - GATT object hierarchy

## Installatie

### Dependencies Installeren

```bash
# Ubuntu/Raspberry Pi - BlueZ systeem packages
sudo apt-get update
sudo apt-get install -y bluetooth bluez

# Python packages
pip install dbus-next netifaces
```

### Verificatie

```bash
# Check BlueZ versie (minimaal 5.50 aanbevolen)
bluetoothctl --version

# Check of bluetooth service draait
sudo systemctl status bluetooth

# Start bluetooth als het niet draait
sudo systemctl start bluetooth

# Verifieer dbus-next import
python3 -c "import dbus_next; print('D-Bus OK')"

# Test GATT service (nadat webserver draait)
bluetoothctl
[bluetooth]# scan on
# Je zou "LeRobot-192.168.x.x" moeten zien
```

## Gebruik

### Automatische Start

De Bluetooth GATT service start automatisch wanneer de webserver opstart:

```python
# In webserver.py startup
bluetooth_mgr = BLEGattServer("LeRobot")
bluetooth_mgr.start()
```

De service:
- Registreert GATT service met IP characteristic
- Start BLE advertising met device naam "LeRobot-<IP>"
- Update IP-adres elke 10 seconden automatisch
- Draait in background thread

### Via Web Interface

1. Open de web interface: `http://<robot-ip>`
2. Ga naar **Advanced** tab → **System** sub-tab  
3. Scroll naar **📡 Bluetooth IP Service** sectie
4. Status toont of service actief is
5. Gebruik **Start/Stop Service** knoppen indien nodig

### Web Bluetooth Scanner (Aanbevolen)

De makkelijkste manier om robots te vinden is via de Web Bluetooth scanner:

**Optie 1: Vanaf de robot zelf**
```
http://localhost/bluetooth
```

**Optie 2: Vanaf andere computer op netwerk**
```
http://<bekende-ip>/bluetooth
```

**Optie 3: Via GitHub Pages (werkt overal)**
```
https://<username>.github.io/teleop_lerobot/bluetooth_scan.html
```

De scanner:
- Gebruikt Web Bluetooth API (Chrome/Edge vereist)
- Scant automatisch naar "LeRobot-" apparaten
- Leest IP via GATT characteristic (preferred)
- Fallback: parseert IP uit device naam
- Kopieert IP naar clipboard
- Link direct naar robot web interface

⚠️ **Let op**: Web Bluetooth werkt alleen op HTTPS of localhost (browser security)

### Vanaf Mobiel Apparaat

**Methode 1: Web Bluetooth Scanner via Browser (Aanbevolen)**

Open Chrome of Edge browser op je telefoon en ga naar:
```
http://<bekende-ip>/bluetooth
```

Of gebruik de GitHub Pages versie (werkt zonder lokaal netwerk):
```
https://<username>.github.io/teleop_lerobot/bluetooth_scan.html
```

De scanner:
1. Klikt op "🔍 Scan for Robots"
2. Browser toont lijst met BLE apparaten
3. Selecteer "LeRobot-<IP>" apparaat
4. Scanner leest GATT characteristic voor IP
5. IP wordt getoond en gekopieerd naar clipboard
6. Klik op link om naar robot interface te gaan

**Methode 2: Native BLE Scanner App**

Download een BLE scanner app (bijvoorbeeld "nRF Connect" of "BLE Scanner"):
1. Open de app en scan naar BLE apparaten
2. Zoek naar "LeRobot-192.168.x.x" in de lijst
3. Het IP-adres staat in de device naam
4. Optioneel: connect en lees GATT characteristic `c5f50002-...` voor IP
5. Open browser en ga naar `http://<IP>`

**Methode 3: Handmatig via Bluetooth Instellingen**

Let op: Standaard Bluetooth instellingen tonen meestal geen BLE advertising apparaten. Gebruik methode 1 of 2.

### Van Linux/Mac Terminal

```bash
# Scan voor BLE apparaten met bluetoothctl
bluetoothctl scan on

# Output toont:
# [NEW] Device XX:XX:XX:XX:XX:XX LeRobot-192.168.1.100
#                                  ^^^^^^^ Hier staat het IP!

# Of gebruik gatttool om GATT characteristic te lezen
gatttool -b XX:XX:XX:XX:XX:XX --char-read --uuid=c5f50002-1234-5678-89ab-123456789abc

# Gebruik het IP om te verbinden
curl http://192.168.1.100/api/status
```

### Bluetooth Permissies (Optioneel)

Voor non-root toegang tot Bluetooth D-Bus:

```bash
# Voeg gebruiker toe aan bluetooth groep
sudo usermod -a -G bluetooth $USER

# Log uit en weer in, of herstart sessie
# Verifieer groep membership
groups | grep bluetooth
```

## API Gebruik

### Via Python API

```python
import requests

# Get Bluetooth status
response = requests.get('http://<robot-ip>/api/bluetooth/status')
data = response.json()
print(f"Running: {data['running']}")
print(f"Device: {data['device_name']}")
print(f"IP: {data['ip_address']}")
# Output: 
# Running: True
# Device: LeRobot-192.168.1.100
# IP: 192.168.1.100

# Start GATT service (normaal auto-start)
response = requests.post('http://<robot-ip>/api/bluetooth/start')
print(response.json())

# Stop GATT service
response = requests.post('http://<robot-ip>/api/bluetooth/stop')
print(response.json())

# Get only IP address
response = requests.get('http://<robot-ip>/api/bluetooth/ip')
print(response.json())
# Output: {"ip": "192.168.1.100"}
```

### Via JavaScript (Web Bluetooth API)

```javascript
// GATT Service en Characteristic UUIDs
const SERVICE_UUID = 'c5f50001-1234-5678-89ab-123456789abc';
const IP_CHAR_UUID = 'c5f50002-1234-5678-89ab-123456789abc';

// Scan en connect naar robot
async function findRobot() {
    try {
        // Request BLE device met namePrefix filter
        const device = await navigator.bluetooth.requestDevice({
            filters: [{ namePrefix: 'LeRobot-' }],
            optionalServices: [SERVICE_UUID]
        });
        
        // Connect naar GATT server
        const server = await device.gatt.connect();
        
        // Get GATT service
        const service = await server.getPrimaryService(SERVICE_UUID);
        
        // Get IP characteristic
        const characteristic = await service.getCharacteristic(IP_CHAR_UUID);
        
        // Read IP value
        const value = await characteristic.readValue();
        const ip = new TextDecoder('utf-8').decode(value);
        
        console.log('Robot IP:', ip);
        return ip;
        
    } catch (error) {
        console.error('Error:', error);
    }
}

// Gebruik
findRobot().then(ip => {
    window.location.href = `http://${ip}`;
});
```

## Automatisch Starten

De Bluetooth GATT server start automatisch wanneer de webserver opstart. Dit gebeurt in de lifespan functie:

```python
# In webserver.py
async def lifespan(app: FastAPI):
    # ... andere initialisatie ...
    
    # Start Bluetooth GATT service
    logger.info("📡 Initializing Bluetooth GATT service...")
    bluetooth_mgr = BLEGattServer("LeRobot")
    bluetooth_mgr.start()
    state.bluetooth_manager = bluetooth_mgr
    logger.info("✅ Bluetooth GATT service started")
    
    yield
    
    # Cleanup bij shutdown
    logger.info("Shutting down Bluetooth service...")
    if state.bluetooth_manager:
        state.bluetooth_manager.stop()
```

Om auto-start uit te schakelen, comment de Bluetooth initialisatie uit in `webserver.py`.

## API Endpoints

- `GET /api/bluetooth/status` - Status van GATT service (running, device_name, ip_address)
- `GET /api/bluetooth/ip` - Huidig IP adres alleen
- `POST /api/bluetooth/start` - Start GATT service (indien gestopt)
- `POST /api/bluetooth/stop` - Stop GATT service
- `GET /bluetooth` - Web Bluetooth scanner pagina

## Troubleshooting

### D-Bus Property Errors

Als je errors ziet zoals "property TxPower does not exist":
```
ERROR - interface "org.bluez.LEAdvertisement1" does not have property "TxPower"
```

Dit zijn library-level D-Bus query errors die de functionaliteit niet blokkeren. De GATT service en advertising werken normaal. Deze errors komen door dbus-next library queries naar properties die niet altijd bestaan in BlueZ.

### BlueZ Service Issues

```bash
# Check BlueZ status
sudo systemctl status bluetooth

# Check BlueZ versie (>= 5.50 aanbevolen voor GATT Manager)
bluetoothctl --version

# Restart BlueZ service
sudo systemctl restart bluetooth

# Check adapter status
bluetoothctl show

# Manual GATT service test
bluetoothctl
[bluetooth]# scan on
[bluetooth]# devices  # Should show LeRobot-<IP>
```

### dbus-next Import Errors

```bash
# Install system D-Bus development packages
sudo apt-get install -y libdbus-1-dev python3-dev

# Install Python package
pip install dbus-next

# Verify import
python3 -c "import dbus_next; print('OK')"
```

### BLE Adapter Not Found

```bash
# Check if Bluetooth adapter exists
hciconfig

# If no adapter:
sudo apt-get install -y bluetooth bluez
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Check again
bluetoothctl list
```

### Web Bluetooth Not Working

Web Bluetooth API vereist:
- **Browser**: Chrome, Edge, of Opera (niet Firefox/Safari)
- **Context**: HTTPS of localhost (security requirement)
- **Permissions**: Sta Bluetooth toegang toe in browser

Als je deze error ziet:
```
Web Bluetooth API is not available
```

Oplossingen:
1. Gebruik HTTPS of localhost URL
2. Check browser compatibility (gebruik Chrome/Edge)
3. Sta Bluetooth permissions toe in browser settings

### GATT Characteristic Niet Leesbaar

Als Web Bluetooth de characteristic niet kan lezen:

```bash
# Check of GATT service geregistreerd is
gdbus introspect --system --dest org.bluez --object-path /org/bluez/hci0

# Check application path
gdbus introspect --system --dest org.bluez --object-path /org/freedesktop/lerobot

# Manual characteristic read via gatttool
# Eerst MAC address vinden met bluetoothctl scan
gatttool -b XX:XX:XX:XX:XX:XX --char-read --uuid=c5f50002-1234-5678-89ab-123456789abc
```

## Technische Details

### BLE GATT Architectuur

**GATT Service**
- UUID: `c5f50001-1234-5678-89ab-123456789abc`
- Type: Primary Service
- Characteristics: 1 (IP Address)

**GATT Characteristic**
- UUID: `c5f50002-1234-5678-89ab-123456789abc`
- Properties: Read-only
- Value: IP address als UTF-8 bytes (bijv. `b"192.168.1.100"`)
- D-Bus Signature: `'ay'` (array of bytes)

**BLE Advertising**
- Type: `peripheral`
- LocalName: `LeRobot-<IP>` (bijv. "LeRobot-192.168.1.100")
- ServiceUUIDs: `[c5f50001-1234-5678-89ab-123456789abc]`
- Update interval: 10 seconden

**BlueZ D-Bus Interfaces**
- `org.bluez.GattManager1.RegisterApplication` - GATT service registratie
- `org.bluez.LEAdvertisingManager1.RegisterAdvertisement` - BLE advertising
- `org.bluez.GattCharacteristic1` - GATT characteristic interface
- `org.freedesktop.DBus.ObjectManager` - Object hierarchy management

### Implementatie Details

De implementatie is gebaseerd op de Pybricks firmware GATT server implementatie en gebruikt:

1. **ServiceInterface** (dbus-next): D-Bus object interfaces
2. **MessageBus**: Async D-Bus connection
3. **Variant**: D-Bus type marshalling voor properties
4. **PropertyAccess.READ**: Read-only characteristic flag

Code structuur:
```
bluetooth_gatt_server.py
├── IPAddressCharacteristic - GATT characteristic met IP value
├── LeRobotGattService - Primary GATT service container  
├── LEAdvertisement - BLE advertising data
├── GattApplication - ObjectManager voor service hierarchy
└── BLEGattServer - Main server class
    ├── register_gatt_service() - Export + RegisterApplication
    ├── setup_advertising() - Export + RegisterAdvertisement  
    ├── make_discoverable() - Set Adapter Discoverable=True
    └── run() - Async event loop met IP updates
```

### Bestandsstructuur

```
/home/kwijk/localdata/teleop_lerobot/
├── bluetooth_gatt_server.py      # BLE GATT server implementatie
├── webserver.py                  # FastAPI server met Bluetooth integratie
├── static/
│   └── bluetooth_scan.html       # Web Bluetooth scanner
└── docs/                         # GitHub Pages
    ├── bluetooth_scan.html       # Scanner (publiek toegankelijk)
    ├── README.md                 # Documentatie
    └── _config.yml              # Jekyll config
```

## Security Overwegingen

⚠️ **Belangrijk voor productie gebruik:**

**BLE Security**
- GATT characteristic is read-only (geen writes mogelijk)
- Geen pairing of authentication vereist voor lezen
- IP-adres is publiek zichtbaar voor BLE scanners in range
- Dit is acceptabel voor local network discovery

**HTTP API Security**
- API endpoints zijn zonder authenticatie
- Alleen local network access (geen internet exposure)

**Voor productie omgevingen:**
1. Implementeer API token authenticatie
2. Gebruik HTTPS in plaats van HTTP  
3. Implementeer rate limiting op endpoints
4. Configureer firewall rules (alleen local network)
5. Overweeg BLE pairing voor GATT access

**Network Isolation**
- Robot moet op private/trusted network staan
- Gebruik VLAN segmentatie indien mogelijk
- Monitor BLE advertising range (fysieke beveiliging)

## Geavanceerd Gebruik

### Custom GATT Service UUID

Om conflicten te voorkomen met andere BLE apparaten, pas de service UUID aan:

```python
# In bluetooth_gatt_server.py
LEROBOT_SERVICE_UUID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Eigen UUID
IP_CHARACTERISTIC_UUID = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

# Update ook in bluetooth_scan.html
const LEROBOT_SERVICE_UUID = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx';
```

### Custom Device Name

Pas de device naam prefix aan:

```python
# In webserver.py startup
bluetooth_mgr = BLEGattServer("MyRobot")  # ipv "LeRobot"
bluetooth_mgr.start()

# Device naam wordt: MyRobot-192.168.1.100
```

### Multiple Robots

Voor meerdere robots op hetzelfde netwerk:

```python
# Gebruik unieke namen per robot
bluetooth_mgr = BLEGattServer(f"LeRobot-{ROBOT_ID}")

# Voorbeelden:
# LeRobot-Alpha-192.168.1.100
# LeRobot-Beta-192.168.1.101
```

Update scanner filter:
```javascript
// In bluetooth_scan.html
filters: [{ namePrefix: 'LeRobot-Alpha-' }]
```

### mDNS + BLE Combinatie

Voor robuuste discovery, combineer BLE met mDNS/Avahi:

```bash
# Installeer Avahi voor mDNS
sudo apt-get install -y avahi-daemon avahi-utils

# Configureer service in /etc/avahi/services/lerobot.service
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>LeRobot Web Interface</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>

# Restart Avahi
sudo systemctl restart avahi-daemon

# Vanaf client: zoek LeRobot
avahi-browse -r _http._tcp
```

Nu kunnen clients de robot vinden via:
- **BLE**: Voor mobiele apparaten zonder mDNS
- **mDNS**: Voor computers op netwerk

### Netwerk Interface Selectie

Standaard detecteert de server automatisch het primaire IP. Voor specifieke interface:

```python
# In bluetooth_gatt_server.py, pas get_local_ip() aan:
def get_local_ip(self) -> str:
    import netifaces
    # Forceer specifieke interface
    iface = 'wlan0'  # of 'eth0', 'wlp3s0', etc.
    try:
        addrs = netifaces.ifaddresses(iface)
        return addrs[netifaces.AF_INET][0]['addr']
    except:
        return "No IP"
```

### D-Bus Monitoring

Voor debugging van GATT registratie:

```bash
# Monitor alle D-Bus berichten
dbus-monitor --system "type='signal',interface='org.freedesktop.DBus.Properties'"

# Check geregistreerde GATT applications
gdbus call --system --dest org.bluez \
  --object-path /org/bluez/hci0 \
  --method org.freedesktop.DBus.Introspectable.Introspect

# Check advertising data
gdbus call --system --dest org.bluez \
  --object-path /org/bluez/hci0 \
  --method org.freedesktop.DBus.Properties.Get \
  org.bluez.LEAdvertisingManager1 SupportedIncludes
```

### Logging Configuratie

Voor meer gedetailleerde Bluetooth logs:

```python
# In bluetooth_gatt_server.py
import logging
logging.basicConfig(
    level=logging.DEBUG,  # ipv INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

Of via environment variable:
```bash
export LEROBOT_BLE_DEBUG=1
python webserver.py
```

## Licentie

Onderdeel van LeRobot Teleoperation System.
