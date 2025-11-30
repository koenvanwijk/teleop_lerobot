# Robot Calibration Files

Deze directory bevat calibration files voor verschillende robot types.

## Directory structuur

```
calibration/
├── so101_follower/        # SO-101 follower robots
│   ├── white.json
│   ├── white_12.json
│   ├── white_123.json
│   ├── white_12v.json
│   ├── white_3250.json
│   └── ...
├── so101_leader/          # SO-101 leader robots
│   └── ...
├── roarm_follower/        # RoArm follower robots
│   └── ...
└── roarm_leader/          # RoArm leader robots
    └── ...
```

## Calibration file naam

De calibration file naam moet overeenkomen met de `NICE_NAME` in `mapping.csv`.

**Voorbeeld:**
- Mapping entry: `5A68012756,white_12,follower,so101`
- Calibration file: `calibration/so101_follower/white_12.json`

## Installatie

De calibration files worden automatisch geïnstalleerd door `install.sh` naar:
```
~/.cache/huggingface/lerobot/calibration/robots/
```

## Nieuwe calibration toevoegen

1. Voeg het `.json` bestand toe aan de juiste directory (bijv. `so101_follower/`)
2. Zorg dat de bestandsnaam overeenkomt met de `NICE_NAME` in `mapping.csv`
3. Commit en push naar GitHub
4. Run `./install.sh` op de doelcomputer om de files te installeren

## Calibration genereren

Om een nieuwe calibration file te genereren:

```bash
# Activeer lerobot environment
conda activate lerobot

# Calibreer robot
python -m lerobot.calibrate \
    --robot-type so101_follower \
    --robot-port /dev/ttyACM0 \
    --robot-id white_12

# De calibration wordt opgeslagen in:
# ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/white_12.json
```

Kopieer het gegenereerde bestand naar deze repository:
```bash
cp ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/white_12.json \
   calibration/so101_follower/
```
