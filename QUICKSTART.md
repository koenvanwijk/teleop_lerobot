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

Voor Linux of SSH gebruik je:

```text
Loginnaam:  lerobot
Wachtwoord: lerobotlogin
```

Browser-SSH:

```text
http://<IP-adres>/ssh
```

Het **Setup WiFi-wachtwoord** (`robotics123`) en het **Linux/SSH-loginwachtwoord** (`lerobotlogin`) zijn twee onafhankelijke wachtwoorden.

## 4. Normale update / delivery-flow

Voor een geteste robot is de normale update simpel:

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
./install.sh
sudo reboot
```

Na reboot hoort dit automatisch te gebeuren:

```text
webserver start op poort 80
calibration is al door install.sh uit de repo naar de LeRobot-cache gezet
teleoperation start automatisch als leader en follower beschikbaar zijn
```

Web-teleoperation mag nooit wachten op een terminalprompt zoals **Press ENTER to use provided calibration file**. De webserver gebruikt bestaande repo-calibration non-interactive. Als calibration ontbreekt of niet matcht, moet teleop zichtbaar falen in de UI/logs; hij mag niet verborgen op Enter wachten.

## 5. Bluetooth kan IP lezen maar WiFi niet wijzigen

Symptoom: Bluetooth werkt, de robot is zichtbaar en het oude IP-adres wordt getoond, maar na het kiezen van een nieuw WiFi-netwerk verandert het IP-adres niet. Dan mist de service waarschijnlijk NetworkManager-rechten om WiFi-profielen te wijzigen of de WiFi-switch faalde zonder duidelijke status.

De normale oplossing is opnieuw de installer draaien:

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
./install.sh
sudo reboot
```

Daarna opnieuw testen via Bluetooth: WiFi scannen, netwerk kiezen, wachtwoord invullen, verbinden en daarna het IP-adres opnieuw uitlezen. Bij mislukken hoort de robot terug te vallen naar `LeRobot-AP` zodat hij headless bereikbaar blijft.

Logs bij problemen:

```bash
journalctl -u lerobot-webserver.service -b -n 200 --no-pager
nmcli general permissions
```

## 6. Installatiehulp

Voor installatiehulp, stappenplan en achtergrond:

https://sites.google.com/view/teleop-lerobot

De printable quick-start kaart staat in de repo als:

```text
docs/LeRobot-F686-Quick-Start.pdf
```

## Begrippen niet door elkaar halen

| Functie | Voorbeeld | Waarvoor |
| --- | --- | --- |
| Bluetooth-naam | `LeRobot-F686` | Robot herkennen en IP-adres opvragen |
| Setup WiFi | `LeRobot-AP` | Tijdelijk netwerk als normaal netwerk ontbreekt |
| Setup WiFi-wachtwoord | `robotics123` | Verbinden met `LeRobot-AP` |
| Linux / SSH loginnaam | `lerobot` | Gebruikersnaam om in te loggen |
| Linux / SSH wachtwoord | `lerobotlogin` | Wachtwoord om in te loggen |

Als de desktopbrowser niet automatisch opent, controleer:

```bash
cat ~/.local/state/lerobot-webui-autostart.log
sudo systemctl status lerobot-webserver.service
```
