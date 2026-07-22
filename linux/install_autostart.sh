#!/usr/bin/env bash
# Register FlowSuite to start at login via XDG autostart (works across
# GNOME/KDE/XFCE desktop sessions). X11 sessions only (see README).
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON3="$(command -v python3)"
DEST_DIR="$HOME/.config/autostart"
DEST="$DEST_DIR/flowsuite.desktop"

mkdir -p "$DEST_DIR"
sed -e "s|__PYTHON3__|$PYTHON3|" -e "s|__APPDIR__|$APP_DIR|g" \
    "$APP_DIR/linux/flowsuite.desktop" > "$DEST"

echo "Installed: $DEST (takes effect on next login)"
echo "To start it right now: $PYTHON3 $APP_DIR/flowsuite.py &"
echo "To remove: rm \"$DEST\""
echo
echo "Prefer systemd (headless/server, no desktop session)? Instead run:"
echo "  mkdir -p ~/.config/systemd/user"
echo "  sed -e \"s|__PYTHON3__|$PYTHON3|\" -e \"s|__APPDIR__|$APP_DIR|g\" \\"
echo "    \"$APP_DIR/linux/flowsuite.service\" > ~/.config/systemd/user/flowsuite.service"
echo "  systemctl --user enable --now flowsuite.service"
