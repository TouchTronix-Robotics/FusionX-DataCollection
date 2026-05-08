#!/usr/bin/env bash
# Install the Touchtronix Touch AppImage as an Ubuntu/GNOME app launcher and dock shortcut.
# Usage:
#   mkdir -p ~/Touchtronix
#   # Put this script and touchtronix-touch-*.AppImage in ~/Touchtronix
#   cd ~/Touchtronix
#   chmod +x install_touch_app.sh
#   ./install_touch_app.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_ID="touchtronix-touch.desktop"
DESKTOP_FILE="$HOME/.local/share/applications/$DESKTOP_ID"
ICON_FILE="$APP_DIR/touchtronix-touch.svg"

APPIMAGE="$(find "$APP_DIR" -maxdepth 1 -type f -iname '*touch*.AppImage' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"

if [ -z "$APPIMAGE" ]; then
    echo "Error: no *touch*.AppImage found in $APP_DIR"
    echo "Download touchtronix-touch-*.AppImage and place it next to this script."
    exit 1
fi

chmod +x "$APPIMAGE"
mkdir -p "$APP_DIR/calibrations" "$APP_DIR/dataset" "$HOME/.local/share/applications"

# Lightweight fallback icon. Replace this file with your own PNG/SVG if desired.
if [ ! -f "$ICON_FILE" ]; then
    cat > "$ICON_FILE" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="48" fill="#111827"/>
  <circle cx="128" cy="128" r="82" fill="#0ea5e9" opacity="0.18"/>
  <path d="M64 128h128M128 64v128" stroke="#38bdf8" stroke-width="18" stroke-linecap="round"/>
  <circle cx="128" cy="128" r="32" fill="#22c55e"/>
  <text x="128" y="224" text-anchor="middle" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="#e5e7eb">TX</text>
</svg>
EOF
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Touchtronix Touch
Comment=Touchscreen data collection with OAK cameras and tactile gloves
Exec="$APPIMAGE"
Icon=$ICON_FILE
Terminal=false
Type=Application
Categories=Utility;Science;
Path=$APP_DIR
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null || true

if command -v gsettings >/dev/null 2>&1; then
    CURRENT="$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo '[]')"
    if echo "$CURRENT" | grep -q "$DESKTOP_ID"; then
        echo "Already pinned to GNOME dock."
    elif command -v python3 >/dev/null 2>&1; then
        NEW="$(python3 - "$CURRENT" "$DESKTOP_ID" <<'PY'
import ast
import sys
try:
    apps = ast.literal_eval(sys.argv[1])
except Exception:
    apps = []
app = sys.argv[2]
if app not in apps:
    apps.append(app)
print(repr(apps))
PY
)"
        gsettings set org.gnome.shell favorite-apps "$NEW" && echo "Pinned to GNOME dock."
    else
        NEW="$(echo "$CURRENT" | sed "s/]/, '$DESKTOP_ID']/;s/\[, /[/")"
        gsettings set org.gnome.shell favorite-apps "$NEW" && echo "Pinned to GNOME dock."
    fi
else
    echo "gsettings not found; launcher installed but not pinned automatically."
fi

echo "Installed launcher: $DESKTOP_FILE"
echo "AppImage: $APPIMAGE"
echo "Calibrations: $APP_DIR/calibrations"
echo "Recordings: $APP_DIR/dataset"
