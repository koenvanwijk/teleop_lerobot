# LeRobot Quick Start

## 1. Bluetooth - snelste manier om het IP-adres te vinden

De robot adverteert via Bluetooth als `LeRobot-XXXX`, waarbij `XXXX` de laatste vier tekens van het Bluetooth MAC-adres zijn.

Open op Android, Chrome of Edge:

https://koenvanwijk.github.io/teleop_lerobot/

Selecteer de robot en lees het huidige IP-adres uit. Open daarna:

```text
http://<IP-adres>/
```

De webinterface gebruikt standaard **poort 80**, dus er is geen `:5000` meer nodig.

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

Het Linux/SSH-loginwachtwoord is:

```text
lerobot
```

Browser-SSH:

```text
http://<IP-adres>/ssh
```

Het **Setup WiFi-wachtwoord** en het **Linux/SSH-loginwachtwoord** zijn twee onafhankelijke wachtwoorden. Het wijzigen van het ene wijzigt het andere niet.

## Begrippen niet door elkaar halen

| Functie | Voorbeeld | Waarvoor |
| --- | --- | --- |
| Bluetooth-naam | `LeRobot-F686` | Robot herkennen en IP-adres opvragen |
| Setup WiFi | `LeRobot-AP` | Tijdelijk netwerk als normaal netwerk ontbreekt |
| Setup WiFi-wachtwoord | `robotics123` | Verbinden met `LeRobot-AP` |
| Robot login-wachtwoord | `lerobot` | Linux / SSH login |
| Webpoort | `80` | Web GUI, API en browser-SSH |

## Update van een bestaande robot naar poort 80

Na het ophalen van de laatste `main` moet `install.sh` opnieuw worden uitgevoerd. De installer configureert systemd met `CAP_NET_BIND_SERVICE`, zodat de webserver als gewone gebruiker veilig op poort 80 kan luisteren.

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
./install.sh
sudo reboot
```

Na reboot:

```text
http://localhost/
```

De desktopbrowser wordt na een grafische login automatisch geopend. Als dat niet gebeurt, controleer:

```bash
cat ~/.local/state/lerobot-webui-autostart.log
sudo systemctl status lerobot-webserver.service
```
