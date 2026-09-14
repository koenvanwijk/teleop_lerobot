# teleop_lerobot – reproduceerbaar Raspberry Pi image-recept

Dit maakt met **pi-gen** een flashbare `.img.xz` voor een Raspberry Pi 4/5.
De image bevat Raspberry Pi OS (Bookworm, 64-bit Lite) met:

- deze repo al gecloned in `/home/<user>/teleop_lerobot`
- SSH aan, user + wachtwoord, locale/timezone/keyboard ingesteld, optioneel WiFi
- een **one-shot first-boot service** die de bestaande, geteste `install.sh`
  één keer draait (conda + LeRobot + udev + systemd webserver op poort 80),
  zichzelf daarna uitschakelt en een eventueel meegegeven onboarding-secret wist

> Waarom `install.sh` op de Pi i.p.v. tijdens de build? `install.sh` doet dingen
> die alleen op een draaiend systeem kloppen (`systemctl`, `udevadm`,
> `hostnamectl`) en compileert LeRobot/torch native — op de Pi is dat snel en
> zonder QEMU-emulatie. Zo is er precies **één** installatiepad, geen drift.

## Benodigdheden op de build-machine

- `git` en **Docker** (verder niets — pi-gen draait volledig in een container)
- ~10 GB vrije schijf, en internet

## Bouwen

```bash
cd image
FIRST_USER_PASS='kies-een-sterk-wachtwoord' ./build.sh
```

Klaar → `image/.pi-gen/deploy/*.img.xz`. Flashen met Raspberry Pi Imager
("Use custom" → dit `.img.xz`) of `dd`/`bmaptool`.

De Pi heeft bij **eerste boot internet nodig** (kabel of voorgezette WiFi):
dan draait `install.sh` automatisch. Volgen kan met:

```bash
ssh <user>@<ip>
sudo journalctl -u lerobot-firstboot -f      # voortgang
tail -f /var/log/lerobot-firstboot.log
```

Als het klaar is staat de web-UI op `http://<ip>/`.

## Opties (env vars voor `build.sh`)

| Variabele | Default | Betekenis |
|---|---|---|
| `FIRST_USER_PASS` | *(verplicht)* | login-wachtwoord eerste user |
| `FIRST_USER_NAME` | `pi` | login-naam |
| `TARGET_HOSTNAME` | `lerobot` | hostname |
| `TELEOP_REPO_URL` | GitHub-URL | te clonen repo |
| `TELEOP_REPO_REF` | `main` | branch/tag/commit die gebakken wordt |
| `WPA_ESSID` / `WPA_PASSWORD` / `WPA_COUNTRY` | – / – / `NL` | WiFi voorzetten |
| `LEROBOT_ROBOT_NAME` | – | robotnaam/hostname zetten bij first boot |
| `TAILSCALE_AUTH_KEY` | – | Tailscale bij first boot koppelen (key wordt na gebruik gewist) |
| `PIGEN_REF` | `2025-11-24-raspios-bookworm-arm64` | gepinde pi-gen release |

Voorbeeld met alles:

```bash
FIRST_USER_PASS='...' \
WPA_ESSID='MijnWifi' WPA_PASSWORD='...' \
LEROBOT_ROBOT_NAME='lerobot-f686' \
TAILSCALE_AUTH_KEY='tskey-auth-...' \
TELEOP_REPO_REF='v1.0.0' \
./build.sh
```

## Desktop i.p.v. Lite (Chromium kiosk-autostart)

`install.sh` zet ook een browser-autostart klaar (`~/.config/autostart`). Die
werkt alleen op een desktop-image. Wil je dat: in `config`
`STAGE_LIST=... stage2 ...` → `... stage4 ...`. Build duurt dan langer en de
image is groter.

## Structuur

```
image/
  build.sh          # clone+pin pi-gen, injecteer config/secrets, docker-build
  config            # pi-gen basisconfig (geen secrets)
  stage-teleop/
    prerun.sh
    EXPORT_IMAGE
    00-install-teleop/
      00-packages           # apt: git curl bluetooth bluez openssh-server ...
      01-run.sh             # clone repo in image + zet first-boot service
      files/
        provision.sh          # draait install.sh 1x als user, disable-on-success
        lerobot-firstboot.service
```
