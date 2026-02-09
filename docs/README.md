# LeRobot Bluetooth Scanner

Vind je LeRobot via Bluetooth en ontdek automatisch het IP-adres!

## 🌐 Live Demo

**[Open Bluetooth Scanner](https://koenvanwijk.github.io/teleop_lerobot/)**

Scan voor je LeRobot en krijg direct het IP-adres!

## 📱 Gebruik

1. Open de scanner pagina in **Chrome, Edge of Opera** (Safari wordt niet ondersteund)
2. Zorg dat Bluetooth aan staat op je apparaat
3. Klik op "Scan voor LeRobot"
4. Selecteer je robot in de popup
5. Het IP-adres wordt automatisch getoond
6. Klik op "Open Web Interface" om te verbinden

## ✨ Features

- ✅ Web Bluetooth API integratie
- ✅ Automatische IP detectie uit device naam
- ✅ Direct link naar web interface
- ✅ Mobiel-vriendelijk responsive design
- ✅ Werkt volledig standalone (geen server nodig)

## 🔧 Lokaal gebruiken

Je kunt de pagina ook lokaal openen:

```bash
# Download de pagina
wget https://raw.githubusercontent.com/koenvanwijk/teleop_lerobot/main/static/bluetooth_scan.html

# Open in browser
open bluetooth_scan.html  # macOS
xdg-open bluetooth_scan.html  # Linux
start bluetooth_scan.html  # Windows
```

Of integreer in je eigen webserver:
```bash
# Als onderdeel van LeRobot webserver
http://localhost:8000/bluetooth
```

## 🖨️ QR Code

Print een QR code voor snelle toegang:

**[Genereer QR Code](https://koenvanwijk.github.io/teleop_lerobot/qr.html)**

## 🤖 Setup Robot

De robot moet BLE advertising ingeschakeld hebben met IP in device naam:

1. Start de LeRobot webserver
2. Ga naar Advanced → System
3. Start de Bluetooth IP Service
4. De robot is nu discoverable als "LeRobot-xxxx" (xxxx = MAC suffix). Het IP adres wordt via GATT characteristic uitgelezen.

## Browser Ondersteuning

| Browser | Ondersteuning |
|---------|---------------|
| Chrome  | ✅ Ja         |
| Edge    | ✅ Ja         |
| Opera   | ✅ Ja         |
| Safari  | ❌ Nee        |
| Firefox | ❌ Nee        |

Web Bluetooth API is alleen beschikbaar in Chromium-based browsers.

## 📚 Documentatie

Zie [BLUETOOTH_README.md](BLUETOOTH_README.md) voor volledige documentatie over de Bluetooth service.
