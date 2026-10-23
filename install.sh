#!/bin/sh
# Installs the beachball launch cursor for the current user. ./install.sh --uninstall removes it.
set -e
cd "$(dirname "$0")"
DEST="$HOME/.local/share/pibeachball"
AUTOSTART="$HOME/.config/autostart/pibeachball.desktop"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

pkill -f "$DEST/pibeachball.py" || true
if [ "$1" = "--uninstall" ]; then
    rm -rf "$DEST" "$AUTOSTART"
    echo "Beachball removed."
    exit
fi

python3 -c 'import gi; gi.require_version("GtkLayerShell", "0.1")' 2>/dev/null ||
    sudo apt-get install -y gir1.2-gtklayershell-0.1

rm -rf "$DEST/frames"
mkdir -p "$DEST/frames" "$(dirname "$AUTOSTART")"
cp pibeachball.py "$DEST/"
cp blender/frames/*.png "$DEST/frames/"
cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Beachball launch cursor
Exec=python3 $DEST/pibeachball.py
NoDisplay=true
EOF

setsid python3 "$DEST/pibeachball.py" >/dev/null 2>&1 &
echo "Beachball installed and running."
