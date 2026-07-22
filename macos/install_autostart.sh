#!/usr/bin/env bash
# Registers WhisperFlow as a per-user LaunchAgent that starts at login.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON3="$(command -v python3)"
DEST="$HOME/Library/LaunchAgents/com.whisperflow.agent.plist"

mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__PYTHON3__|$PYTHON3|" -e "s|__APPDIR__|$APP_DIR|g" \
    "$APP_DIR/macos/com.whisperflow.agent.plist" > "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "Installed and started: $DEST"
echo "Logs: $APP_DIR/whisperflow.log"
echo "To remove: launchctl unload \"$DEST\" && rm \"$DEST\""
