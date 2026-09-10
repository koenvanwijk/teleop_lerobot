# LeRobot remote support en support bundle

Deze flow is bedoeld voor robots die je weggeeft of op locatie zet. Doel:

- robot krijgt een vaste identiteit/hostname;
- Linux-login kan gecontroleerd gezet worden;
- Tailscale kan automatisch of interactief onboarden;
- support kan later via SSH/Tailscale een support-bundle ZIP ophalen.

## Aanbevolen Tailscale onboarding

Gebruik voor product/field robots geen persoonlijke interactieve login als standaardproces, maar een Tailscale auth key met een tag, bijvoorbeeld:

```text
tag:lerobot
```

Maak in Tailscale een auth key die deze tag mag gebruiken. Voor headless onboarding is een pre-authorized key het handigst. Gebruik een korte geldigheid voor de key en vervang hem wanneer hij gelekt kan zijn.

## Delivery install met identiteit, login en Tailscale

Voorbeeld voor robot `lerobot-f686`:

```bash
cd ~/teleop_lerobot
git switch main
git pull --ff-only

TAILSCALE_AUTH_KEY='tskey-auth-...' ./install.sh \
  --robot-name lerobot-f686 \
  --login-user lerobot \
  --set-login-password \
  --tailscale \
  --tailscale-tags tag:lerobot

sudo reboot
```

De installer:

- zet de hostname/robot-identiteit;
- schrijft `/etc/lerobot/identity.env`;
- zet het Linux-wachtwoord voor de opgegeven bestaande user;
- installeert `zip`, Tailscale en de normale LeRobot stack;
- voert `tailscale up` uit met hostname en tag;
- installeert de systemd webserver service.

## Zonder auth key, interactief

Dit kan als er een scherm/terminal beschikbaar is en iemand de Tailscale loginlink kan openen:

```bash
./install.sh \
  --robot-name lerobot-f686 \
  --login-user lerobot \
  --set-login-password \
  --tailscale \
  --tailscale-tags tag:lerobot
```

`tailscale up` toont dan een loginlink.

## Tailscale SSH

Standaard blijft Linux/OpenSSH leidend. Zet Tailscale SSH alleen aan als je dit ook in de tailnet policy beheert:

```bash
TAILSCALE_AUTH_KEY='tskey-auth-...' ./install.sh \
  --robot-name lerobot-f686 \
  --tailscale \
  --tailscale-tags tag:lerobot \
  --tailscale-ssh
```

## Support bundle ZIP maken

Op de robot:

```bash
cd ~/teleop_lerobot
./support_bundle.sh
```

Output is een ZIP in:

```text
~/lerobot-support-bundles/
```

De ZIP bevat onder meer:

- manifest met hostname, tijd, kernel en OS;
- systemd status en journal van `lerobot-webserver.service`;
- `webserver.log`, `teleoperation.log`, `startup.log` en browser-autostart log als aanwezig;
- netwerkstatus, poorten, NetworkManager en Tailscale status;
- USB/serial/video device-info;
- udev rules en `mapping.csv`;
- git status/SHA/log;
- calibratie-lijsten;
- conda/pip info.

Secrets worden best-effort geredact uit tekstbestanden, maar behandel de ZIP alsnog als intern supportmateriaal.

## Via Tailscale ophalen

Vanaf je eigen machine, zodra de robot in de tailnet zit:

```bash
ssh lerobot@lerobot-f686
cd ~/teleop_lerobot
./support_bundle.sh
ls -lh ~/lerobot-support-bundles/
```

Kopieer daarna de ZIP terug:

```bash
scp lerobot@lerobot-f686:~/lerobot-support-bundles/*.zip .
```

Met MagicDNS kun je de hostname gebruiken; anders gebruik je het Tailscale IP uit:

```bash
tailscale status
```
