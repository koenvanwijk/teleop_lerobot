# LeRobot Bluetooth & WiFi Setup

Gebruik de publieke setup-pagina om een LeRobot via Bluetooth te vinden, WiFi in te stellen en daarna de lokale robotinterface te openen.

## 🌐 Setup

**[Open LeRobot Setup](https://koenvanwijk.github.io/teleop_lerobot/)**

Dezelfde URL en QR-code werken op Android, desktop en iPhone/iPad.

## 📱 Gebruik

### Android / Chrome

1. Open de setup-pagina in **Chrome**.
2. Zorg dat Bluetooth aan staat.
3. Tik op **Scan voor LeRobot**.
4. Selecteer de robot.
5. Scan indien nodig de beschikbare WiFi-netwerken.
6. Kies het netwerk, vul het WiFi-wachtwoord in en verbind.
7. Zodra de robot een IP-adres heeft, open je de robotinterface.

### iPhone / iPad

Safari ondersteunt geen Web Bluetooth. De setup-pagina herkent dit en gebruikt **Bluefy** voor alleen de Bluetooth/WiFi-setup.

1. Scan de LeRobot QR-code met de Camera-app.
2. De setup-pagina opent in Safari.
3. Tik op **Open setup in Bluefy**.
4. Als Bluefy nog niet is geïnstalleerd, word je naar de App Store geleid.
5. Ga na installatie terug naar de setup-pagina en tik opnieuw op **Open setup in Bluefy**.
6. Tik in Bluefy op **Scan voor LeRobot** en configureer WiFi.
7. Open daarna de lokale **LeRobot Control Center**.
8. Als het Control Center nog in Bluefy staat, verschijnt een waarschuwing. Gebruik voor normale robotbediening bij voorkeur Safari; de pagina kan het adres voor je kopiëren.

Bluefy is dus alleen een tijdelijke Web-Bluetooth-brug voor commissioning. De normale robotinterface is bedoeld voor Safari/Chrome/Edge.

## 🖨️ QR-code

**[Open / print de QR-pagina](https://koenvanwijk.github.io/teleop_lerobot/qr.html)**

De hoofd-QR bevat deze universele setup-URL:

```
https://koenvanwijk.github.io/teleop_lerobot/
```

Gebruik dus **één QR-code op de robot**:

- Android → Chrome → Web Bluetooth.
- iPhone/iPad → Safari landing → Bluefy.
- Desktop → Chrome/Edge → Web Bluetooth.

Er is geen aparte iPhone-QR nodig.

## ✨ Functionaliteit

- ✅ Bluetooth discovery
- ✅ IP-adres uitlezen via BLE
- ✅ WiFi-netwerken laten scannen door de robot
- ✅ WiFi SSID/wachtwoord via BLE configureren
- ✅ Android Chrome / desktop Chrome & Edge
- ✅ iPhone/iPad via Bluefy
- ✅ Directe link naar de lokale robotinterface
- ✅ Responsive setup-pagina
- ✅ SoftAP blijft alleen beschikbaar als recovery

## Browserondersteuning

| Platform | Setup via BLE | Control Center |
|---|---|---|
| Android Chrome | ✅ Direct | ✅ Chrome |
| Desktop Chrome / Edge | ✅ Direct | ✅ |
| iPhone / iPad Safari | ❌ Web Bluetooth | ✅ Aanbevolen voor Control Center |
| iPhone / iPad Bluefy | ✅ Setup | ⚠️ Alleen voor setup aanbevolen |
| Firefox | ❌ Web Bluetooth | Niet primair ondersteund |

## 🔧 Robot

De robot gebruikt een custom BLE GATT service en adverteert als `LeRobot-...`. De setup-pagina leest het IP-adres en bevat characteristics voor WiFi-scan en WiFi-configuratie.

Start de webserver; de Bluetooth-service wordt normaal automatisch gestart. Handmatig controleren kan via **Advanced → System** in het Control Center.

## Recovery

Als Bluetooth/WiFi provisioning mislukt, blijft de bestaande **LeRobot-AP** route een recovery-optie. Dit is niet de normale onboarding-flow.

## 📚 Technische documentatie

Zie [BLUETOOTH_README.md](../BLUETOOTH_README.md) voor de GATT UUIDs, BlueZ-implementatie en troubleshooting.
