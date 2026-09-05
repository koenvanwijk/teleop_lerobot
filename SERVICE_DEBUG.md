# LeRobot service/debug quick reference

## Waarom komt Python terug nadat je het killt?

De webserver draait als systemd-service:

```bash
lerobot-webserver.service
```

Die service luistert standaard op poort 80. Als `Restart=always` of `Restart=on-failure` actief is, start systemd de Python-webserver opnieuw wanneer je het proces killt. Daardoor lijkt het alsof Python vanzelf terugkomt en blijft poort 80 bezet.

## Webserver normaal herstarten

Gebruik systemd, niet `killall python`:

```bash
sudo systemctl restart lerobot-webserver.service
```

Status:

```bash
sudo systemctl status lerobot-webserver.service --no-pager
```

Logs:

```bash
journalctl -u lerobot-webserver.service -b -n 200 --no-pager
```

Live logs:

```bash
journalctl -u lerobot-webserver.service -f
```

## Tijdelijk stoppen om poort 80 vrij te maken

```bash
sudo systemctl stop lerobot-webserver.service
```

Controleer wie poort 80 gebruikt:

```bash
sudo ss -ltnp 'sport = :80'
```

Handmatig starten voor debug:

```bash
cd ~/teleop_lerobot
PORT=80 python -u webserver.py
```

Daarvoor moet je shell voldoende rechten hebben voor poort 80. Makkelijker tijdens debug is poort 5000 gebruiken:

```bash
cd ~/teleop_lerobot
PORT=5000 python -u webserver.py
```

Open dan:

```text
http://<IP-adres>:5000/
```

Na debug weer terug naar service:

```bash
sudo systemctl start lerobot-webserver.service
```

## Voorkomen dat de service automatisch terugkomt

Voor langdurige debug:

```bash
sudo systemctl disable --now lerobot-webserver.service
```

Terug aanzetten:

```bash
sudo systemctl enable --now lerobot-webserver.service
```

## Calibratieprompt bij teleop

Symptoom: teleop lijkt te openen maar hangt op een LeRobot-prompt waarin Enter voldoende is om bestaande calibratie te accepteren. Dat werkt met scherm/toetsenbord, maar niet headless.

Fix:

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
chmod +x fix_headless_delivery.sh
sudo ./fix_headless_delivery.sh
sudo reboot
```

De fix schakelt boot-auto-start van teleop uit en patcht web-teleop zodat hij bestaande calibratie zonder interactieve Enter-prompt probeert te gebruiken.

## Handmatig calibreren of bestaande calibratie accepteren

Via terminal/scherm kan het selectie-script gebruikt worden:

```bash
cd ~/teleop_lerobot
./select_teleop.py
```

Als LeRobot vraagt om bestaande calibratie te accepteren, is Enter voldoende. Na calibratie of acceptatie kun je de files synchroniseren:

```bash
./sync_calibration.sh export
```

Op een nieuwe of herstelde robot:

```bash
./sync_calibration.sh import
```

## Minimale delivery-check vóór weggeven

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only
./sync_calibration.sh import
sudo systemctl restart lerobot-webserver.service
sleep 5
sudo systemctl status lerobot-webserver.service --no-pager
sudo ss -ltnp 'sport = :80'
journalctl -u lerobot-webserver.service -b -n 80 --no-pager
```

Daarna testen:

```text
http://localhost/
http://<IP-adres>/
https://koenvanwijk.github.io/teleop_lerobot/  # Bluetooth IP scan
```
