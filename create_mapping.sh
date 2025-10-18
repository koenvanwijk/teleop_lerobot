#!/usr/bin/env bash
set -euo pipefail

MAPFILE="./mapping.csv"

echo "📄 Mapping wordt geschreven naar: $MAPFILE"
if [[ ! -f "$MAPFILE" ]]; then
  echo "SERIAL_SHORT,NICE_NAME,ROLE" > "$MAPFILE"
fi

# --- Helpers ---
list_byid() {
  shopt -s nullglob
  for p in /dev/serial/by-id/*; do
    # alleen echte symlinks naar TTY's
    real="$(readlink -f "$p" || true)"
    [[ -n "$real" && -e "$real" && "$real" =~ ^/dev/tty ]] && echo "$p"
  done | sort -u
}

pick_new_device() {
  local before_file="$1"
  local role="$2"
  echo ""
  echo "👉 Sluit nu je ${role} aan (of herplug). Ik zoek naar een nieuw device onder /dev/serial/by-id/…"
  echo "   (Druk Ctrl-C om te stoppen.)"

  # baseline
  list_byid > "$before_file"

  # wacht op verandering
  for i in {1..60}; do
    sleep 1
    tmp="$(mktemp)"
    list_byid > "$tmp"
    # diff
    mapfile -t new < <(comm -13 "$before_file" "$tmp")
    rm -f "$tmp"
    if (( ${#new[@]} > 0 )); then
      if (( ${#new[@]} == 1 )); then
        echo "✅ Nieuw device gevonden: ${new[0]}"
        echo "${new[0]}"
        return 0
      else
        echo "⚠️ Meerdere nieuwe devices gevonden:"
        nl -w2 -s") " <(printf "%s\n" "${new[@]}")
        read -rp "Kies het nummer van je ${role}: " idx
        idx="${idx//[!0-9]/}"
        (( idx>=1 && idx<=${#new[@]} )) || { echo "Ongeldige keuze"; continue; }
        echo "${new[$((idx-1))]}"
        return 0
      fi
    fi
    printf "."
  done
  echo ""
  echo "❌ Geen nieuw device gedetecteerd. Probeer opnieuw en zorg dat udev symlink verschijnt."
  exit 1
}

serial_short_from_byid() {
  local byid="$1"
  local real
  real="$(readlink -f "$byid")"
  # haal ID_SERIAL_SHORT via udevadm
  udevadm info -q property -n "$real" 2>/dev/null | awk -F= '$1=="ID_SERIAL_SHORT"{print $2}'
}

append_mapping() {
  local serial="$1" nicename="$2" role="$3"
  # normaliseer
  serial="$(echo "$serial" | tr -cd '[:alnum:]')"
  nicename="$(echo "$nicename" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_]/_/g')"
  role="$(echo "$role" | tr '[:upper:]' '[:lower:]')"
  if grep -q "^${serial}," "$MAPFILE"; then
    echo "ℹ️  Waarschuwing: serial ${serial} staat al in $MAPFILE. Ik voeg desondanks nog een regel toe."
  fi
  echo "${serial},${nicename},${role}" | tee -a "$MAPFILE"
}

do_one_role() {
  local role="$1"
  local tmpb; tmpb="$(mktemp)"
  local byid sel serial nicename
  byid="$(pick_new_device "$tmpb" "$role")"
  rm -f "$tmpb"

  serial="$(serial_short_from_byid "$byid")"
  if [[ -z "$serial" ]]; then
    echo "❌ Kon ID_SERIAL_SHORT niet bepalen voor $byid"
    echo "   Tip: check 'udevadm info -q property -n $(readlink -f "$byid")'"
    exit 1
  fi
  echo "🔎 ID_SERIAL_SHORT = $serial"

  read -rp "Geef NICE NAME voor ${role} (bv. black): " nicename
  nicename="${nicename:-${role}}"
  append_mapping "$serial" "$nicename" "$role"
}

echo "=== Set 1 ==="
do_one_role "leader"
do_one_role "follower"

while true; do
  echo ""
  read -rp "Nog een extra set (leader + follower) toevoegen? [y/N]: " more
  more="${more:-N}"
  case "$more" in
    y|Y)
      echo "=== Volgende set ==="
      do_one_role "leader"
      do_one_role "follower"
      ;;
    n|N|*)
      break
      ;;
  esac
done

echo ""
echo "✅ Klaar. Mapping staat in: $MAPFILE"
echo "Inhoud:"
column -s, -t "$MAPFILE" || cat "$MAPFILE"
