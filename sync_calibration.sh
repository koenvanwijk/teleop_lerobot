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
  list      Toon overzicht van cache vs repository calibration files
  -h        Toon deze help

Voorbeelden:
  ./sync_calibration.sh export   # Na het calibreren van robots
  ./sync_calibration.sh import   # Bij installatie op nieuwe machine
  ./sync_calibration.sh list     # Bekijk status van alle calibration files
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
  local skipped_count=0
  
  # Track processed files to avoid duplicates
  declare -A processed_files
  
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
    
    # Bepaal mogelijke type directories (voor backwards compatibility)
    # LeRobot 0.4.3+ gebruikt vereenvoudigde namen: so_follower ipv so101_follower
    type_dir_full="${robot_type}_${role}"  # Bijv: so101_follower (oude stijl)
    
    # Voor so101/so100 -> probeer ook so_ variant (nieuwe stijl 0.4.3+)
    if [[ "$robot_type" == "so101" || "$robot_type" == "so100" ]]; then
      type_dir_short="so_${role}"
    else
      type_dir_short="$type_dir_full"  # Andere robot types blijven hetzelfde
    fi
    
    # Probeer beide locaties (nieuw eerst, dan oud)
    cache_file_new="$CALIBRATION_CACHE/$category/$type_dir_short/${nice_name}.json"
    cache_file_old="$CALIBRATION_CACHE/$category/$type_dir_full/${nice_name}.json"
    
    # Detecteer welke versie bestaat
    if [[ -f "$cache_file_new" ]]; then
      cache_file="$cache_file_new"
      type_dir="$type_dir_short"
    elif [[ -f "$cache_file_old" ]]; then
      cache_file="$cache_file_old"
      type_dir="$type_dir_full"
    else
      # Niet gevonden in beide locaties
      cache_file="$cache_file_old"  # Use old path for error message
      type_dir="$type_dir_full"
    fi
    
    repo_dir="$CALIBRATION_REPO/$category/$type_dir"
    repo_file="$repo_dir/${nice_name}.json"
    
    # Skip if already processed (handles duplicates in mapping.csv)
    file_key="$category/$type_dir/${nice_name}.json"
    if [[ -n "${processed_files[$file_key]:-}" ]]; then
      ((skipped_count++)) || true
      continue
    fi
    processed_files[$file_key]=1
    
    # Check of calibration file bestaat in cache
    if [[ -f "$cache_file" ]]; then
      mkdir -p "$repo_dir"
      cp "$cache_file" "$repo_file"
      echo "   ✅ Exported: $category/$type_dir/${nice_name}.json"
      ((exported_count++)) || true
    else
      echo "   ⚠️  Niet gevonden in cache: $category/$type_dir/${nice_name}.json"
      ((not_found_count++)) || true
    fi
  done < "$MAPPING_FILE"
  
  echo ""
  echo "✅ Export compleet: $exported_count file(s) naar $CALIBRATION_REPO"
  if [[ $skipped_count -gt 0 ]]; then
    echo "ℹ️  $skipped_count duplicate(s) overgeslagen"
  fi
  if [[ $not_found_count -gt 0 ]]; then
    echo "⚠️  $not_found_count file(s) niet gevonden in cache (nog niet gecalibreerd?)"
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

list_calibration() {
  echo "📋 Calibration Files Overzicht"
  echo "═══════════════════════════════════════════════════════════="
  echo ""
  
  # Check beide directories
  for category in robots teleoperators; do
    echo "[$category]"
    
    # In cache
    cache_category_dir="$CALIBRATION_CACHE/$category"
    if [[ -d "$cache_category_dir" ]]; then
      for type_dir in "$cache_category_dir"/*; do
        if [[ -d "$type_dir" ]]; then
          type_name="$(basename "$type_dir")"
          repo_type_dir="$CALIBRATION_REPO/$category/$type_name"
          
          echo "  📁 $type_name/"
          
          # Files in cache
          if ls "$type_dir"/*.json 1> /dev/null 2>&1; then
            for json_file in "$type_dir"/*.json; do
              filename="$(basename "$json_file")"
              repo_file="$repo_type_dir/$filename"
              
              if [[ -f "$repo_file" ]]; then
                echo "    ✅ $filename (cache + repo)"
              else
                echo "    📦 $filename (alleen cache)"
              fi
            done
          fi
          
          # Files only in repo
          if [[ -d "$repo_type_dir" ]] && ls "$repo_type_dir"/*.json 1> /dev/null 2>&1; then
            for json_file in "$repo_type_dir"/*.json; do
              filename="$(basename "$json_file")"
              cache_file="$type_dir/$filename"
              
              if [[ ! -f "$cache_file" ]]; then
                echo "    📥 $filename (alleen repo)"
              fi
            done
          fi
        fi
      done
    fi
    
    # In repo but not in cache at all
    repo_category_dir="$CALIBRATION_REPO/$category"
    if [[ -d "$repo_category_dir" ]]; then
      for type_dir in "$repo_category_dir"/*; do
        if [[ -d "$type_dir" ]]; then
          type_name="$(basename "$type_dir")"
          cache_type_dir="$CALIBRATION_CACHE/$category/$type_name"
          
          if [[ ! -d "$cache_type_dir" ]]; then
            echo "  📁 $type_name/ (alleen repo)"
            if ls "$type_dir"/*.json 1> /dev/null 2>&1; then
              for json_file in "$type_dir"/*.json; do
                filename="$(basename "$json_file")"
                echo "    📥 $filename"
              done
            fi
          fi
        fi
      done
    fi
    
    echo ""
  done
  
  echo "═══════════════════════════════════════════════════════════="
  echo "Legenda:"
  echo "  ✅ = In cache EN repository (gesynchroniseerd)"
  echo "  📦 = Alleen in cache (run 'export' om te syncen)"
  echo "  📥 = Alleen in repository (run 'import' om te syncen)"
  echo ""
}

# Parse argumenten
case "${1:-}" in
  export)
    export_calibration
    ;;
  import)
    import_calibration
    ;;
  list)
    list_calibration
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
