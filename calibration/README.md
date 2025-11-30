# Robot Calibration Files

Deze directory bevat calibration files voor robots (followers) en teleoperators (leaders).

## Directory structuur

```
calibration/
├── robots/                    # Follower robots
│   ├── so101_follower/       # SO-101 follower robots
│   │   ├── white.json
│   │   ├── white_12.json
│   │   ├── white_123.json
│   │   ├── white_12v.json
│   │   ├── white_3250.json
│   │   └── ...
│   └── roarm_follower/        # RoArm follower robots
│       └── ...
└── teleoperators/             # Leader/teleoperator robots
    ├── so101_leader/          # SO-101 leader robots
    │   ├── black.json
    │   ├── yellow.json
    │   ├── leader.json
    │   └── ...
    └── roarm_leader/          # RoArm leader robots
        └── ...
```

## Calibration file naam

De calibration file naam moet overeenkomen met de `NICE_NAME` in `mapping.csv`.

**Voorbeeld:**
- Mapping entry: `5A68012756,white_12,follower,so101`
- Calibration file: `calibration/robots/so101_follower/white_12.json`

- Mapping entry: `5A46082267,black,leader,so101`
- Calibration file: `calibration/teleoperators/so101_leader/black.json`

## Installatie

De calibration files worden automatisch geïnstalleerd door `install.sh` naar:
```
~/.cache/huggingface/lerobot/calibration/
├── robots/
│   ├── so101_follower/
│   └── roarm_follower/
└── teleoperators/
    ├── so101_leader/
    └── roarm_leader/
```

## Nieuwe calibration toevoegen

1. Voeg het `.json` bestand toe aan de juiste directory (bijv. `so101_follower/`)
2. Zorg dat de bestandsnaam overeenkomt met de `NICE_NAME` in `mapping.csv`
3. Commit en push naar GitHub
4. Run `./install.sh` op de doelcomputer om de files te installeren

## Calibration genereren

Om een nieuwe calibration file te genereren:

**Voor follower (robot):**
```bash
# Activeer lerobot environment
conda activate lerobot

# Calibreer robot
lerobot-calibrate \
    --robot-type so101_follower \
    --robot-port /dev/ttyACM0 \
    --robot-id white_12

# De calibration wordt opgeslagen in:
# ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/white_12.json
```

**Voor leader (teleoperator):**
```bash
# Calibreer teleoperator
lerobot-calibrate \
    --robot-type so101_leader \
    --robot-port /dev/ttyUSB0 \
    --robot-id black

# De calibration wordt opgeslagen in:
# ~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/black.json
```

Kopieer de gegenereerde bestanden naar deze repository:
```bash
# Export alle calibration files
./sync_calibration.sh export
```
