#!/usr/bin/env bash
# Disable GNOME Bluetooth GUI agents for headless Bluetooth pairing
# Run this if you still see "connection successful" pairing dialogs

set -e

echo "═══════════════════════════════════════════════════════"
echo "🔇 Uitschakelen Bluetooth GUI agents"
echo "═══════════════════════════════════════════════════════"
echo ""

# Stop all Bluetooth agent processes
echo "🛑 Stoppen Bluetooth agent processen..."
pkill -f gnome-bluetooth-agent 2>/dev/null && echo "   • gnome-bluetooth-agent gestopt" || echo "   • gnome-bluetooth-agent niet actief"
pkill -f bluetooth-agent 2>/dev/null && echo "   • bluetooth-agent gestopt" || echo "   • bluetooth-agent niet actief"
pkill -f blueman-agent 2>/dev/null && echo "   • blueman-agent gestopt" || echo "   • blueman-agent niet actief"
pkill -f /usr/lib/bluetooth/obexd 2>/dev/null && echo "   • obexd gestopt" || echo "   • obexd niet actief"

# Disable systemd user services
if command -v systemctl >/dev/null 2>&1; then
    echo ""
    echo "⚙️  Uitschakelen systemd services..."
    systemctl --user mask obex.service 2>/dev/null && echo "   • obex.service masked" || true
    systemctl --user stop obex.service 2>/dev/null && echo "   • obex.service stopped" || true
fi

# Disable autostart entries
echo ""
echo "🚫 Uitschakelen autostart entries..."
mkdir -p "$HOME/.config/autostart"

# Disable blueman
if [[ -f "/etc/xdg/autostart/blueman.desktop" ]]; then
    cat > "$HOME/.config/autostart/blueman.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Blueman
Hidden=true
EOF
    echo "   • blueman autostart disabled"
fi

# Disable GNOME Bluetooth applet (if exists)
for desktop in /etc/xdg/autostart/bluetooth-applet*.desktop; do
    if [[ -f "$desktop" ]]; then
        basename=$(basename "$desktop")
        cat > "$HOME/.config/autostart/$basename" <<'EOF'
[Desktop Entry]
Type=Application
Hidden=true
EOF
        echo "   • $basename disabled"
    fi
done

echo ""
echo "✅ Bluetooth GUI agents uitgeschakeld!"
echo ""
echo "🔍 Controleren actieve processen..."
if ps aux | grep -E "bluetooth.*agent|blueman|obex" | grep -v grep | grep -v "disable_bluetooth_gui"; then
    echo "⚠️  Let op: Er draaien nog steeds Bluetooth processes"
    echo "   Deze kunnen mogelijk nog dialogs tonen"
    echo ""
    echo "💡 Oplossing:"
    echo "   1. Log uit en weer in"
    echo "   2. Of herstart het systeem"
else
    echo "✅ Geen actieve Bluetooth GUI agents gevonden"
fi

echo ""
echo "📡 Bluetooth service status:"
sudo systemctl status bluetooth --no-pager | head -5 || true

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✨ Klaar!"
echo ""
echo "Nu zou de Bluetooth GATT server (bluetooth_gatt_server.py)"
echo "automatisch pairing moeten afhandelen zonder GUI prompts."
echo ""
echo "Test: verbind vanaf Android/laptop via Bluetooth scanner"
echo "       Er zou GEEN pairing dialog meer moeten verschijnen."
echo "═══════════════════════════════════════════════════════"
