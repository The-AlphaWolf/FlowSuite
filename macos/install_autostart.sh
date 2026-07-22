#!/usr/bin/env bash
# Register FlowSuite as a per-user LaunchAgent that starts at login (macOS).
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON3="$(command -v python3)"
DEST="$HOME/Library/LaunchAgents/com.flowsuite.agent.plist"

mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__PYTHON3__|$PYTHON3|" -e "s|__APPDIR__|$APP_DIR|g" \
    "$APP_DIR/macos/com.flowsuite.agent.plist" > "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "Installed and started: $DEST"
echo "Logs: $APP_DIR/flowsuite.log"
echo "To remove: launchctl unload \"$DEST\" && rm \"$DEST\""
echo
echo "NOTE: grant Accessibility + Microphone permission to your terminal (or to"
echo "python3) in System Settings > Privacy & Security the first time."
