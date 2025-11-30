#!/usr/bin/env bash
set -euo pipefail

# Script om calibration files te synchroniseren tussen cache en repository
# Gebruikt mapping.csv om te bepalen welke calibration files nodig zijn

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALIBRATION_REPO="$SCRIPT_DIR/calibration"
CALIBRATION_CACHE="$HOME/.cache/huggingface/lerobot/calibration"
MAPPING_FILE="$SCRIPT_DIR/mapping.csv"

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
  
  if [[ ! -f "$MAPPING_FILE" ]]; then
    echo "❌ Mapping file niet gevonden: $MAPPING_FILE"
    exit 1
  fi
  
  mkdir -p "$CALIBRATION_REPO"
  
  local exported_count=0
  local not_found_count=0
  
  # Lees mapping.csv en export alleen de benodigde calibration files
  while IFS=',' read -r serial nice_name role robot_type rest; do
    # Skip header en lege regels
    [[ "$serial" == "SERIAL_SHORT" ]] && continue
    [[ -z "$serial" || -z "$nice_name" || -z "$role" || -z "$robot_type" ]] && continue
    
    # Bepaal category en type
    if [[ "$role" == "follower" ]]; then
      category="robots"
    elif [[ "$role" == "leader" ]]; then
      category="teleoperators"
    else
      continue
    fi
    
    # Verwijder whitespace
    nice_name="${nice_name// /}"
    robot_type="${robot_type// /}"
    
    # Bepaal paths
    type_dir="${robot_type}_${role}"
    cache_file="$CALIBRATION_CACHE/$category/$type_dir/${nice_name}.json"
    repo_dir="$CALIBRATION_REPO/$category/$type_dir"
    repo_file="$repo_dir/${nice_name}.json"
    
    # Check of calibration file bestaat in cache
    if [[ -f "$cache_file" ]]; then
      mkdir -p "$repo_dir"
      cp "$cache_file" "$repo_file"
      echo "   ✅ Exported: $category/$type_dir/${nice_name}.json"
      ((exported_count++)) || true
    else
      echo "   ⚠️  Niet gevonden: $category/$type_dir/${nice_name}.json"
      ((not_found_count++)) || true
    fi
  done < "$MAPPING_FILE"
  
  echo ""
  echo "✅ Export compleet: $exported_count file(s) naar $CALIBRATION_REPO"
  if [[ $not_found_count -gt 0 ]]; then
    echo "⚠️  $not_found_count file(s) niet gevonden in cache"
  fi
  echo "💡 Vergeet niet te committen en pushen naar GitHub!"
}

import_calibration() {
  echo "📥 Importeer calibration files van repository naar cache…"
  
  if [[ ! -d "$CALIBRATION_REPO" ]]; then
    echo "❌ Repository directory niet gevonden: $CALIBRATION_REPO"
    exit 1
  fi
  
  mkdir -p "$CALIBRATION_CACHE"
  
  local imported_count=0
  
  # Import alleen bestanden die in de repository aanwezig zijn
  for category in robots teleoperators; do
    repo_category_dir="$CALIBRATION_REPO/$category"
    
    if [[ ! -d "$repo_category_dir" ]]; then
      continue
    fi
    
    for robot_dir in "$repo_category_dir"/*; do
      if [[ -d "$robot_dir" ]]; then
        robot_type="$(basename "$robot_dir")"
        cache_dir="$CALIBRATION_CACHE/$category/$robot_type"
        
        mkdir -p "$cache_dir"
        
        # Kopieer alleen .json files
        if ls "$robot_dir"/*.json 1> /dev/null 2>&1; then
          for json_file in "$robot_dir"/*.json; do
            filename="$(basename "$json_file")"
            cp "$json_file" "$cache_dir/$filename"
            echo "   ✅ Imported: $category/$robot_type/$filename"
            ((imported_count++)) || true
          done
        fi
      fi
    done
  done
  
  echo ""
  echo "✅ Import compleet: $imported_count file(s) naar $CALIBRATION_CACHE"
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
