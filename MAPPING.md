# Mapping.csv Documentation

Dit bestand bevat de mapping tussen USB serial devices en robot configuraties.

## Kolommen

### 1. SERIAL_SHORT
**USB Serial Number (kort formaat)**

- **Format**: Alfanumerieke string (8-32 karakters)
- **Voorbeeld**: `58FA083461`, `8cafc04501daef11a209593dc8728757`
- **Bron**: USB device serial number
- **Gebruikt in**:
  - `gen_udev_rules.py`: Genereert udev rules voor device matching
  - Udev rules: `ENV{ID_SERIAL_SHORT}=="{serial}"`

**Hoe te vinden**:
```bash
# Lijst alle USB serial devices
udevadm info -a -p $(udevadm info -q path -n /dev/ttyUSB0) | grep ATTRS{serial}

# Of met lsusb
lsusb -v | grep iSerial
```

### 2. NICE_NAME
**Menselijke naam/identifier voor de robot**

- **Format**: Lowercase, letters/cijfers/underscores
- **Voorbeeld**: `pink`, `white_12`, `roarm`, `amazing_hand`
- **Gebruikt in**:
  - `gen_udev_rules.py`: Onderdeel van symbolic link naam
  - Udev rules: `/dev/tty_{nice_name}_{role}_{type}`
  - `startup.py`: Gebruikt als `--robot.id` en `--teleop.id`
  - Calibration files: Bestandsnaam is `{nice_name}.json`

**Belangrijk**: 
- Moet uniek zijn binnen een role+type combinatie
- Wordt gebruikt als robot ID in LeRobot commando's
- Moet exact overeenkomen met calibration file naam

### 3. ROLE
**Functie van de robot**

- **Waarden**: `leader` of `follower`
- **Gebruikt in**:
  - `gen_udev_rules.py`: 
    - Onderdeel van symbolic link naam
    - Bepaalt extra symlinks (`/dev/tty_follower` of `/dev/tty_leader`)
  - `startup.py`: Filtert op `*_follower_*` en `*_leader_*` patterns
  - Calibration: Bepaalt subdirectory (`robots/` voor follower, `teleoperators/` voor leader)

**Betekenis**:
- **follower**: Robot die acties uitvoert (wordt bestuurd)
- **leader**: Teleoperator die commando's geeft (wordt handmatig bewogen)

### 4. TYPE
**Type/model van de robot**

- **Format**: Lowercase alfanumeriek
- **Voorbeelden**: `so101`, `roarm`, `amazing_hand`
- **Gebruikt in**:
  - `gen_udev_rules.py`: Onderdeel van symbolic link naam
  - Udev rules: `/dev/tty_{nice_name}_{role}_{type}`
  - `startup.py`: 
    - Gebruikt als `--robot.type={type}_follower`
    - Gebruikt als `--teleop.type={type}_leader`
  - Calibration: Bepaalt subdirectory naam `{type}_{role}`

**Ondersteunde types**:
- `so101`: SO-101 robot arm
- `roarm`: RoArm robot arm
- Custom types zijn mogelijk

## Voorbeeld Entry

```csv
5A68013192,white_12,follower,so101
```

### Resulteert in:

**Udev rules**:
```
SUBSYSTEM=="tty", ENV{ID_BUS}=="usb", ENV{ID_SERIAL_SHORT}=="5A68013192", SYMLINK+="tty_white_12_follower_so101", SYMLINK+="tty_follower"
```

**Symbolic links**:
- `/dev/tty_white_12_follower_so101` → `/dev/ttyACM0` (specifieke link)
- `/dev/tty_follower` → `/dev/ttyACM0` (generieke link)

**Startup.py commando**:
```bash
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=white_12 \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyUSB0 \
    --teleop.id=black
```

**Calibration file pad**:
```
~/.cache/huggingface/lerobot/calibration/robots/so101_follower/white_12.json
```

## Workflow

### 1. Nieuwe robot toevoegen

1. **Vind serial number**:
   ```bash
   ./create_mapping.sh
   ```

2. **Voeg toe aan mapping.csv**:
   ```csv
   5A68013192,white_12,follower,so101
   ```

3. **Genereer udev rules**:
   ```bash
   python gen_udev_rules.py mapping.csv --output 99-usb-serial-aliases.rules
   sudo mv 99-usb-serial-aliases.rules /etc/udev/rules.d/
   sudo udevadm control --reload
   sudo udevadm trigger
   ```

4. **Calibreer robot** (optioneel):
   ```bash
   lerobot-calibrate \
       --robot-type so101_follower \
       --robot-port /dev/ttyACM0 \
       --robot-id white_12
   ```

5. **Export calibration**:
   ```bash
   ./sync_calibration.sh export
   ```

6. **Commit en push**:
   ```bash
   git add mapping.csv calibration/
   git commit -m "Add white_12 follower"
   git push
   ```

### 2. Installatie op andere machine

```bash
# Clone repository
git clone https://github.com/koenvanwijk/raspberry5_lerobot.git
cd raspberry5_lerobot

# Run install script (installeert alles automatisch)
./install.sh
```

Dit installeert:
- Miniconda + lerobot
- Udev rules (van GitHub release)
- Calibration files (van repository)
- Crontab entry voor auto-start

## Data Flow Diagram

```
mapping.csv
    ↓
    ├─→ gen_udev_rules.py → udev rules → /etc/udev/rules.d/
    │                                       ↓
    │                                   Symbolic links in /dev/
    │                                       ↓
    ├─→ startup.py → Leest symlinks → lerobot-teleoperate
    │                                       ↓
    │                                   LeRobot zoekt calibration
    │                                       ↓
    └─→ sync_calibration.sh → Kopieert → ~/.cache/huggingface/lerobot/calibration/
                                              ├─ robots/{type}_follower/{nice_name}.json
                                              └─ teleoperators/{type}_leader/{nice_name}.json
```

## Validatie

Controleer of alles correct werkt:

```bash
# 1. Check symbolic links
ls -la /dev/tty_*

# 2. Check welke devices actief zijn
./startup.py  # In test mode of check de logs

# 3. Check calibration files
ls -la ~/.cache/huggingface/lerobot/calibration/robots/
ls -la ~/.cache/huggingface/lerobot/calibration/teleoperators/

# 4. Test teleoperation
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/tty_white_12_follower_so101 \
    --robot.id=white_12 \
    --teleop.type=so101_leader \
    --teleop.port=/dev/tty_black_leader_so101 \
    --teleop.id=black
```

## Troubleshooting

### Symbolic links niet aanwezig
```bash
# Reload udev rules
sudo udevadm control --reload
sudo udevadm trigger

# Check udev rules
cat /etc/udev/rules.d/99-usb-serial-aliases.rules
```

### Calibration niet gevonden
```bash
# Import calibration files
./sync_calibration.sh import

# Of handmatig kopiëren
cp calibration/robots/so101_follower/*.json \
   ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/
```

### Startup script werkt niet
```bash
# Check logs
tail -f ~/startup.log

# Test handmatig
conda activate lerobot
python startup.py
```
