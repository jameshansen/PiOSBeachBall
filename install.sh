#!/bin/bash
# PiOSBeachBall: installs the beachball launch cursor on Raspberry Pi OS.
#
# Run it from the Pi's desktop, from the folder it came in.
# The program goes into ~/.local/share/pibeachball and starts at every login.
# Run it again to reinstall or remove. ./install.sh --uninstall removes it without asking.
set -u
: "${HOME:?}"

TITLE="PiOSBeachBall"
HERE=$(dirname "$(readlink -f "$0")")
PROGRAM="$HERE/pibeachball.py"
FRAMES="$HERE/blender/frames"
ICON="$FRAMES/beachball_00.png"
PACKAGE=gir1.2-gtklayershell-0.1   # lets the beachball draw over every window
DEST="$HOME/.local/share/pibeachball"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/pibeachball.desktop"
# The defaults let the installer run over SSH and still reach the Pi's desktop.
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

remove() {
  pkill -f "$DEST/pibeachball.py"
  rm -rf "$DEST" "$AUTOSTART"
}

if [ "${1:-}" = "--uninstall" ]; then
  remove
  echo "The beachball has been removed."
  exit 0
fi

if [ ! -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then
  echo "Run this installer from the Raspberry Pi desktop. The beachball needs the standard Wayland desktop; the X11 session is not supported." >&2
  exit 1
fi
if ! command -v zenity >/dev/null; then
  echo "This installer needs zenity (sudo apt install zenity)." >&2
  exit 1
fi

# A page with up to three buttons, left to right: --cancel-label, --ok-label, --extra-button.
# OK returns 0. The extra button prints its label and returns 1, like Cancel.
page() { zenity --question --title="$TITLE" --width=560 --icon="$ICON" "$@" 2>/dev/null; }
note() { zenity --info --title="$TITLE" --width=560 --icon="$ICON" --text="$1" 2>/dev/null; }
fail() { zenity --error --title="$TITLE" --width=560 --no-markup --text="$1" 2>/dev/null; exit 1; }
busy() { zenity --progress --title="$TITLE" --width=560 --no-cancel --auto-close "$@" 2>/dev/null; }
as_root() { if sudo -n true 2>/dev/null; then sudo "$@"; else pkexec "$@"; fi; }
has_package() { python3 -c 'import gi; gi.require_version("GtkLayerShell", "0.1")' 2>/dev/null; }

# Prints progress for the bar on stdout (a number, or "# text"); errors go to stderr.
install_files() (
  set -e
  if ! has_package; then
    echo "# Adding a small system package the beachball needs..."
    as_root apt-get install -y "$PACKAGE" >&2
    has_package
  fi
  echo 70
  echo "# Copying the beachball..."
  pkill -f "$DEST/pibeachball.py" || true
  rm -rf "$DEST/frames"
  mkdir -p "$DEST/frames" "$(dirname "$AUTOSTART")"
  cp "$PROGRAM" "$DEST/"
  cp "$FRAMES"/*.png "$DEST/frames/"
  echo 90
  echo "# Setting it to start at login..."
  cat >"$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Beachball launch cursor
Exec=python3 $DEST/pibeachball.py
NoDisplay=true
EOF
  setsid python3 "$DEST/pibeachball.py" >/dev/null 2>&1 &
)

[ -f "$PROGRAM" ] && [ -f "$ICON" ] ||
  fail "A file that belongs next to install.sh is missing. Download the whole package again."

if [ -e "$DEST/pibeachball.py" ]; then
  choice=$(page --text="<b>The beachball is already installed on this Raspberry Pi.</b>\n\nReinstall sets it up again. Remove takes it away and restores the normal pointer for apps that are loading." \
    --cancel-label="Cancel" --ok-label="Reinstall" --extra-button="Remove")
  status=$?
  if [ "$choice" = "Remove" ]; then
    remove
    note "The beachball has been removed from this Raspberry Pi."
    exit 0
  fi
  [ "$status" -eq 0 ] || exit 0
else
  page --text="<b>Welcome to the $TITLE Installer</b>\n\nThis installer will set up a spinning beachball pointer on this Raspberry Pi. When you start an app from the menu or a desktop icon, the pointer turns into a beachball until the app's window opens, so you can see that it is loading.\n\nThe beachball starts by itself every time you log in." \
    --cancel-label="Cancel" --ok-label="Install" || exit 0
fi

log=$(mktemp)
{ install_files 2>"$log"; status=$?; echo 100; exit $status; } | busy --percentage=0 --text="Installing the beachball..."
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  fail "The install did not finish. The beachball needs Raspberry Pi OS 13 (trixie) with the desktop, and an internet connection the first time.

$(tail -5 "$log")"
fi
rm -f "$log"

note "<b>The beachball is installed and running.</b>\n\nOpen any app from the menu or the desktop to see it. To remove it, run this installer again."
