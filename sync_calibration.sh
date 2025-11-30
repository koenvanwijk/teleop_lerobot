#!/usr/bin/env bash
set -euo pipefail

# Script om calibration files te synchroniseren tussen cache en repository

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALIBRATION_REPO="$SCRIPT_DIR/calibration"
CALIBRATION_CACHE="$HOME/.cache/huggingface/lerobot/calibration/robots"

usage() {
  cat <<'EOF'
Gebruik: ./sync_calibration.sh [OPTIE]

Opties:
  export    Exporteer calibration files van cache naar repository
  import    Importeer calibration files van repository naar cache
  -h        Toon deze help

Voorbeelden:
  ./sync_calibration.sh export   # Na het calibreren van robots
  ./sync_calibration.sh import   # Bij installatie op nieuwe machine
EOF
}

export_calibration() {
  echo "📤 Exporteer calibration files van cache naar repository…"
  
  if [[ ! -d "$CALIBRATION_CACHE" ]]; then
    echo "❌ Cache directory niet gevonden: $CALIBRATION_CACHE"
    exit 1
  fi
  
  mkdir -p "$CALIBRATION_REPO"
  
  for robot_dir in "$CALIBRATION_CACHE"/*; do
    if [[ -d "$robot_dir" ]]; then
      robot_type="$(basename "$robot_dir")"
      echo "   Exporteer $robot_type…"
      
      mkdir -p "$CALIBRATION_REPO/$robot_type"
      
      # Kopieer alleen .json files
      if ls "$robot_dir"/*.json 1> /dev/null 2>&1; then
        cp "$robot_dir"/*.json "$CALIBRATION_REPO/$robot_type/"
        file_count=$(ls "$robot_dir"/*.json | wc -l)
        echo "      ✅ $file_count file(s) gekopieerd"
      else
        echo "      ⚠️  Geen .json files gevonden"
      fi
    fi
  done
  
  echo "✅ Export compleet naar $CALIBRATION_REPO"
  echo "💡 Vergeet niet te committen en pushen naar GitHub!"
}

import_calibration() {
  echo "📥 Importeer calibration files van repository naar cache…"
  
  if [[ ! -d "$CALIBRATION_REPO" ]]; then
    echo "❌ Repository directory niet gevonden: $CALIBRATION_REPO"
    exit 1
  fi
  
  mkdir -p "$CALIBRATION_CACHE"
  
  for robot_dir in "$CALIBRATION_REPO"/*; do
    if [[ -d "$robot_dir" ]]; then
      robot_type="$(basename "$robot_dir")"
      
      # Skip README en andere niet-robot directories
      if [[ "$robot_type" == "README.md" ]] || [[ ! "$robot_type" =~ _(follower|leader)$ ]]; then
        continue
      fi
      
      echo "   Importeer $robot_type…"
      
      mkdir -p "$CALIBRATION_CACHE/$robot_type"
      
      # Kopieer alleen .json files
      if ls "$robot_dir"/*.json 1> /dev/null 2>&1; then
        cp "$robot_dir"/*.json "$CALIBRATION_CACHE/$robot_type/"
        file_count=$(ls "$robot_dir"/*.json | wc -l)
        echo "      ✅ $file_count file(s) gekopieerd"
      else
        echo "      ⚠️  Geen .json files gevonden"
      fi
    fi
  done
  
  echo "✅ Import compleet naar $CALIBRATION_CACHE"
}

# Parse argumenten
case "${1:-}" in
  export)
    export_calibration
    ;;
  import)
    import_calibration
    ;;
  -h|--help)
    usage
    ;;
  *)
    echo "❌ Ongeldige optie: ${1:-}"
    echo ""
    usage
    exit 1
    ;;
esac
