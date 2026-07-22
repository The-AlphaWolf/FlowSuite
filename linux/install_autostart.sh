#!/usr/bin/env bash
# Registers WhisperFlow to start at login via XDG autostart (works across
# GNOME/KDE/XFCE desktop sessions).
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON3="$(command -v python3)"
DEST_DIR="$HOME/.config/autostart"
DEST="$DEST_DIR/whisperflow.desktop"

mkdir -p "$DEST_DIR"
sed -e "s|__PYTHON3__|$PYTHON3|" -e "s|__APPDIR__|$APP_DIR|g" \
    "$APP_DIR/linux/whisperflow.desktop" > "$DEST"

echo "Installed: $DEST (takes effect on next login)"
echo "To start it right now: $PYTHON3 $APP_DIR/whisperflow.py &"
echo "To remove: rm \"$DEST\""
echo
echo "Prefer systemd (headless/server, no desktop session)? Instead run:"
echo "  mkdir -p ~/.config/systemd/user"
echo "  sed -e \"s|__PYTHON3__|$PYTHON3|\" -e \"s|__APPDIR__|$APP_DIR|g\" \\"
echo "    \"$APP_DIR/linux/whisperflow.service\" > ~/.config/systemd/user/whisperflow.service"
echo "  systemctl --user enable --now whisperflow.service"
