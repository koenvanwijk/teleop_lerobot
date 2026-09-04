# LeRobot Teleoperation - Installatie Handleiding

Complete installatie-instructies voor het opzetten van een frisse Raspberry Pi met LeRobot teleoperation.

## 📋 Benodigdheden

### Hardware
- **Raspberry Pi 4/5** (aanbevolen: 4GB+ RAM)
- MicroSD kaart (minimaal 16GB, aanbevolen: 32GB+)
- Voeding (officiële Raspberry Pi adapter aanbevolen)
- USB devices (SO-101 Leader/Follower of compatibele robots)
- Optioneel: Camera's voor video streaming

### Software vooraf
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (voor OS installatie)

---

## 🚀 Snelstart (Ervaren gebruikers)

```bash
# 1. Clone repository
git clone https://github.com/koenvanwijk/teleop_lerobot.git
cd teleop_lerobot

# 2. Run installatie script
./install.sh

# 3. Reboot
sudo reboot

# 4. Klaar! Web interface beschikbaar op http://[PI_IP]
```

---

## 📝 Gedetailleerde Installatie

### Stap 1: Raspberry Pi OS Installeren

#### 1.1 Download en Installeer Raspberry Pi Imager

Download van: https://www.raspberrypi.com/software/

#### 1.2 Flash OS naar SD-kaart

1. Start **Raspberry Pi Imager**
2. **Kies OS**: 
   - Aanbevolen: **Raspberry Pi OS (64-bit)** (Debian Bookworm-based)
   - Of: Raspberry Pi OS Lite (zonder desktop, voor headless gebruik)
3. **Kies Storage**: Selecteer je SD-kaart
4. **Klik op tandwiel** ⚙️ (Advanced Options):

   ```
   ✅ Enable SSH
      • Use password authentication (of SSH key)
   
   ✅ Set username and password
      • Username: pi (of eigen keuze)
      • Password: [kies sterk wachtwoord]
   
   ✅ Configure wireless LAN (optioneel)
      • SSID: [je WiFi naam]
      • Password: [je WiFi wachtwoord]
      • Country: NL
   
   ✅ Set locale settings
      • Timezone: Europe/Amsterdam
      • Keyboard: us (of nl)
   ```

5. Klik **SAVE** en dan **WRITE**
6. Wacht tot het proces klaar is

#### 1.3 Eerste Boot

1. Plaats SD-kaart in Raspberry Pi
2. Sluit voeding aan
3. Wacht ~60 seconden voor eerste boot

---

### Stap 2: Verbinden met Raspberry Pi

#### 2.1 Vind het IP-adres

**Optie A: Via Router**
- Log in op je router (vaak http://192.168.1.1)
- Zoek "raspberrypi" of je gekozen hostname in DHCP clients

**Optie B: Met nmap** (vanaf je computer):
```bash
# Installeer nmap (eenmalig)
# macOS: brew install nmap
# Linux: sudo apt install nmap
# Windows: download van nmap.org

# Scan netwerk
nmap -sn 192.168.1.0/24 | grep -B 2 "Raspberry"
```

**Optie C: Via Bluetooth Scanner** (na installatie):
- Gebruik: https://koenvanwijk.github.io/teleop_lerobot/

**Optie D: Met hostname** (als mDNS werkt):
```bash
ssh pi@raspberrypi.local
```

#### 2.2 SSH Verbinding

```bash
ssh pi@[IP_ADRES]
# Bijvoorbeeld: ssh pi@192.168.1.42

# Eerste keer: accepteer fingerprint met 'yes'
# Voer je wachtwoord in
```

---

### Stap 3: Systeem Updaten

```bash
# Update package lists en upgrade systeem
sudo apt-get update
sudo apt-get upgrade -y

# Installeer essentiële tools
sudo apt-get install -y git curl build-essential

# Optioneel: installeer handige tools
sudo apt-get install -y htop nano vim tmux
```

---

### Stap 4: Repository Clonen

```bash
# Ga naar home directory
cd ~

# Clone de repository
git clone https://github.com/koenvanwijk/teleop_lerobot.git

# Ga naar de directory
cd teleop_lerobot

# Check dat files aanwezig zijn
ls -la
```

---

### Stap 5: Installatie Script Uitvoeren

Het installatie script installeert automatisch:
- ✅ Miniconda/Miniforge (Python 3.12)
- ✅ LeRobot package met Feetech support
- ✅ FastAPI webserver met uvicorn
- ✅ Camera support (OpenCV)
- ✅ Bluetooth support
- ✅ USB device mapping (udev rules)
- ✅ Calibration files
- ✅ Auto-start bij reboot (crontab)

#### 5.1 Standaard Installatie

```bash
# Maak script executable
chmod +x install.sh

# Run installatie (duurt ~10-15 minuten)
./install.sh
```

Het script zal:
1. Miniconda downloaden en installeren
2. Python environment aanmaken (`lerobot`)
3. Dependencies installeren
4. Udev rules downloaden van GitHub releases
5. Webserver configureren voor auto-start

#### 5.2 Alternatieve Installatie Opties

**Met lokale LeRobot source:**
```bash
./install.sh --lerobot-src ~/path/to/lerobot
```

**Met custom Git repository:**
```bash
./install.sh --lerobot-git https://github.com/user/lerobot.git
```

**Met specifieke branch:**
```bash
./install.sh --lerobot-git https://github.com/huggingface/lerobot.git --lerobot-branch main
```

#### 5.3 Installatie Output

Je ziet output zoals:
```
🖥️  Detecteerde architectuur: aarch64 (ARM64/Raspberry Pi)
⬇️  Download Miniconda…
🛠  Installeren naar /home/pi/miniconda3…
🧪 Maak env lerobot (python=3.12)…
📦 pip install lerobot en dependencies…
📡 Installeer Bluetooth dependencies…
📋 Installeer calibration files…
⬇️  Download udev-regels van GitHub release…
🔧 Configureer crontab voor webserver.py…
✅ Installatie compleet!
```

---

### Stap 6: USB Devices Aansluiten

#### 6.1 Devices Verbinden

1. Sluit je USB devices aan (SO-101 Leader/Follower)
2. Controleer of ze gedetecteerd worden:

```bash
# Toon USB serial devices
ls -la /dev/tty* | grep -E "(USB|ACM)"

# Of gebruik lsusb
lsusb

# Check udev rules
ls -la /dev/tty_*
```

Je zou symlinks moeten zien:
```
/dev/tty_follower -> /dev/ttyACM0
/dev/tty_leader -> /dev/ttyUSB0
/dev/tty_white_12_follower_so101 -> /dev/ttyACM0
```

#### 6.2 Nieuwe Devices Toevoegen

Als je eigen devices wilt toevoegen (niet in mapping):

```bash
# 1. Vind serial numbers
./create_mapping.sh

# 2. Voeg toe aan mapping.csv
echo "SERIAL_NUMBER,naam,role,type" >> mapping.csv

# 3. Genereer nieuwe udev rules
python gen_udev_rules.py mapping.csv --output 99-usb-serial-aliases.rules
sudo mv 99-usb-serial-aliases.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

---

### Stap 7: Reboot en Testen

#### 7.1 Reboot

```bash
sudo reboot
```

Na reboot (wacht ~30 seconden):
- Webserver start automatisch
- Devices worden gedetecteerd
- Teleoperation start automatisch (als devices beschikbaar)

#### 7.2 Verificatie

**Check of webserver draait:**
```bash
# SSH terug in
ssh pi@[IP_ADRES]

# Check webserver log
tail -f ~/webserver.log

# Check of poort 80 open is
sudo netstat -tulpn | grep ':80 '
# Of:
sudo ss -tulpn | grep ':80 '
```

**Test web interface:**

Open browser op je computer/telefoon:
```
http://[PI_IP]
```

Je zou de web interface moeten zien met:
- ✅ System info
- ✅ Device status
- ✅ Teleoperation controls
- ✅ Camera feeds (indien aangesloten)

#### 7.3 Check Logs

```bash
# Webserver log
tail -f ~/webserver.log

# Teleoperation log
tail -f ~/teleoperation.log

# System log
journalctl -f
```

---

## 🔧 Configuratie

### Camera's Toevoegen

Camera's worden automatisch gedetecteerd als `/dev/video*`.

Test camera's:
```bash
# Activeer conda environment
conda activate lerobot

# Lijst camera's
ls -la /dev/video*

# Test camera met Python
python -c "import cv2; print('Camera 0:', cv2.VideoCapture(0).isOpened())"
```

Camera's zijn beschikbaar in web interface onder **Cameras** tab.

### Netwerk Configuratie

**Access Point (AP) Mode:**

De webserver ondersteunt het creëren van een WiFi hotspot:

1. Open web interface: http://[PI_IP]
2. Ga naar **Network** tab
3. Klik **Create AP**
4. Verbind met "LeRobot-AP" (wachtwoord: lerobot123)

**Terug naar WiFi Client:**

1. Web interface → **Network**
2. Klik **Connect to WiFi**
3. Selecteer netwerk en voer wachtwoord in

### Bluetooth IP Service

Activeer Bluetooth IP advertising (voor Bluetooth Scanner):

```bash
# Handmatig starten
conda activate lerobot
python bluetooth_gatt_server.py
```

Of via web interface:
1. Ga naar **Advanced** → **System**
2. Klik **Start Bluetooth Service**

Device advertiseert als: `LeRobot-xxxx` (xxxx = laatste 4 chars van MAC adres)

---

## 🛠️ Handmatig Gebruik

### Webserver Handmatig Starten

```bash
cd ~/teleop_lerobot
conda activate lerobot

# Optie 1: Direct python
python webserver.py

# Optie 2: Met uvicorn
uvicorn webserver:app --host 0.0.0.0 --port 80 --reload
```

### Interactieve Device Selectie

Als je meerdere robots hebt:

```bash
conda activate lerobot
./select_teleop.py
```

Dit laat je kiezen welke follower/leader combinatie je wilt gebruiken.

### Direct Teleoperation

```bash
conda activate lerobot

lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/tty_follower \
  --robot.id=default \
  --teleop.type=so101_leader \
  --teleop.port=/dev/tty_leader \
  --teleop.id=default
```

---

## 🐛 Troubleshooting

### Probleem: Webserver start niet

**Symptomen**: Geen web interface beschikbaar op poort 80

**Oplossing**:
```bash
# Check crontab
crontab -l | grep webserver

# Check log
tail -f ~/webserver.log

# Handmatig starten
cd ~/teleop_lerobot
conda activate lerobot
python webserver.py
```

### Probleem: Devices niet gevonden

**Symptomen**: `/dev/tty_follower` of `/dev/tty_leader` bestaat niet

**Oplossing**:
```bash
# Check USB devices
lsusb
ls -la /dev/tty* | grep -E "(USB|ACM)"

# Check udev rules
cat /etc/udev/rules.d/99-usb-serial-aliases.rules

# Reload udev
sudo udevadm control --reload
sudo udevadm trigger

# Herstart devices (unplug/replug)
```

### Probleem: Conda niet gevonden

**Symptomen**: `conda: command not found`

**Oplossing**:
```bash
# Herlaad bashrc
source ~/.bashrc

# Of handmatig laden
source ~/miniconda3/etc/profile.d/conda.sh

# Activeer environment
conda activate lerobot
```

### Probleem: Permission denied voor USB devices

**Symptomen**: `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`

**Oplossing**:
```bash
# Voeg user toe aan dialout groep
sudo usermod -a -G dialout $USER

# Log uit en weer in (of reboot)
sudo reboot
```

### Probleem: Camera niet gevonden

**Symptomen**: Camera stream niet beschikbaar in web interface

**Oplossing**:
```bash
# Check camera devices
ls -la /dev/video*

# Test camera
conda activate lerobot
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"

# Check permissions
sudo usermod -a -G video $USER
sudo reboot

# Debuggen
sudo apt-get install v4l-utils
v4l2-ctl --list-devices
```

### Probleem: Out of Memory

**Symptomen**: Process wordt gekilled, system hangt

**Oplossing**:
```bash
# Check memory
free -h

# Voeg swap toe (als < 2GB RAM)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Zet: CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Reboot
sudo reboot
```

### Probleem: Slow performance

**Oplossing**:
```bash
# Overclock Pi (op eigen risico)
sudo raspi-config
# Performance Options → Overclock

# Check temperatuur
vcgencmd measure_temp

# Ensure goede koeling/heatsink
```

---

## 🔄 Updates

### Repository Updaten

```bash
cd ~/teleop_lerobot
git pull origin main

# Herinstalleer (als er installatie wijzigingen zijn)
./install.sh
```

### LeRobot Package Updaten

```bash
conda activate lerobot
pip install --upgrade lerobot[feetech]
```

### Calibration Files Updaten

```bash
cd ~/teleop_lerobot
./sync_calibration.sh import
```

---

## 📖 Verdere Documentatie

- **[README_TELEOP.md](README_TELEOP.md)** - Teleoperation gebruik en features
- **[MAPPING.md](MAPPING.md)** - USB device mapping configuratie
- **[BLUETOOTH_README.md](BLUETOOTH_README.md)** - Bluetooth scanner gebruik
- **[ROBOT_VIEWER_README.md](ROBOT_VIEWER_README.md)** - 3D robot visualisatie
- **[FEATURES.md](FEATURES.md)** - Complete feature lijst

---

## 🌐 Remote Toegang (Optioneel)

### Via Tailscale (Aanbevolen)

Veilige remote toegang van overal:

```bash
# Installeer Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Activeer
sudo tailscale up

# Volg de link in terminal om te autoriseren
```

Nu kun je verbinden via het Tailscale IP (ook buiten je lokale netwerk).

### Via Port Forwarding (Minder veilig)

1. Log in op je router
2. Zoek "Port Forwarding" of "Virtual Server"
3. Forward externe poort 80 → Pi IP poort 80
4. Toegang via: http://[EXTERNE_IP]

⚠️ **Beveiligingsrisico**: Overweeg VPN of Tailscale voor productie gebruik.

---

## 💡 Tips

### Auto-login Zonder Wachtwoord (SSH Key)

```bash
# Op je computer (niet op Pi):
ssh-keygen -t ed25519 -C "your_email@example.com"

# Kopieer key naar Pi:
ssh-copy-id pi@[PI_IP]

# Nu kun je inloggen zonder wachtwoord:
ssh pi@[PI_IP]
```

### Alias voor Snelle Toegang

Voeg toe aan `~/.bashrc` op je computer:
```bash
alias lerobot="ssh pi@[PI_IP]"
alias lerobot-web="open http://[PI_IP]"  # macOS
# of
alias lerobot-web="xdg-open http://[PI_IP]"  # Linux
```

### Statisch IP Adres

```bash
# Edit dhcpcd.conf
sudo nano /etc/dhcpcd.conf

# Voeg toe (pas aan voor je netwerk):
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8

# Reboot
sudo reboot
```

---

## 📞 Support

- **GitHub Issues**: https://github.com/koenvanwijk/teleop_lerobot/issues
- **LeRobot Discord**: https://discord.gg/s3KuuzsPFb
- **LeRobot Docs**: https://github.com/huggingface/lerobot

---

## ✅ Checklist na Installatie

- [ ] Raspberry Pi OS geïnstalleerd en ge-update
- [ ] SSH toegang werkend
- [ ] Repository gecloned
- [ ] `install.sh` succesvol uitgevoerd
- [ ] Conda environment `lerobot` actief
- [ ] USB devices aangesloten en symlinks aanwezig
- [ ] Webserver bereikbaar op poort 80
- [ ] Camera's (optioneel) gedetecteerd
- [ ] Teleoperation test succesvol
- [ ] Auto-start bij reboot geverifieerd

**Gefeliciteerd! Je LeRobot teleoperation systeem is klaar voor gebruik! 🎉**
