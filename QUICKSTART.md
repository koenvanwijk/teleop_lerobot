# LeRobot Quick Start

## 1. Bluetooth - snelste manier om het IP-adres te vinden

De robot adverteert via Bluetooth als `LeRobot-XXXX`, waarbij `XXXX` de laatste vier tekens van het Bluetooth MAC-adres zijn.

Open op Android, Chrome of Edge:

https://koenvanwijk.github.io/teleop_lerobot/

Selecteer de robot en lees het huidige IP-adres uit. Open daarna:

```text
http://<IP-adres>/
```

> iPhone/iPad: Safari ondersteunt Web Bluetooth niet. Gebruik daar het Setup Access Point of een reeds bekend IP-adres.

## 2. Geen netwerk? Gebruik het Setup Access Point

Als de robot tijdens het opstarten geen bruikbare netwerkverbinding vindt, start hij het setup-netwerk:

| Instelling | Waarde |
| --- | --- |
| WiFi SSID | `LeRobot-AP` |
| Setup WiFi-wachtwoord | `robotics123` |
| Setup IP | `192.168.4.1` |
| Webinterface | `http://192.168.4.1/` |

Verbind met `LeRobot-AP`, open `http://192.168.4.1/` en ga naar **Advanced -> Network** om de robot met het normale WiFi-netwerk te verbinden.

## 3. Robot login / SSH

Wanneer Linux of SSH om het loginwachtwoord vraagt, gebruik:

```text
lerobot
```

Browser-SSH:

```text
http://<IP-adres>/ssh
```

Het **Setup WiFi-wachtwoord** (`robotics123`) en het **Linux/SSH-loginwachtwoord** (`lerobot`) zijn twee onafhankelijke wachtwoorden.

## Begrippen niet door elkaar halen

| Functie | Voorbeeld | Waarvoor |
| --- | --- | --- |
| Bluetooth-naam | `LeRobot-F686` | Robot herkennen en IP-adres opvragen |
| Setup WiFi | `LeRobot-AP` | Tijdelijk netwerk als normaal netwerk ontbreekt |
| Setup WiFi-wachtwoord | `robotics123` | Verbinden met `LeRobot-AP` |
| Linux / SSH loginwachtwoord | `lerobot` | Inloggen op de robot |

## Update van een bestaande robot

Voor een update haal je de laatste versie van `main` op, voer je de installer opnieuw uit en reboot je de robot:

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
./install.sh
sudo reboot
```

Na de reboot wordt de lokale webinterface automatisch gestart. Als de desktopbrowser niet automatisch opent, controleer:

```bash
cat ~/.local/state/lerobot-webui-autostart.log
sudo systemctl status lerobot-webserver.service
```
