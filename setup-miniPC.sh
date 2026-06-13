#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${OUTPUT:-DSI-1}"
TRANSFORM="${TRANSFORM:-3}"
IDLE_DELAY_SECONDS="${IDLE_DELAY_SECONDS:-120}"
DISPLAY_CONFIG_DEST="org.gnome.Mutter.DisplayConfig"
DISPLAY_CONFIG_PATH="/org/gnome/Mutter/DisplayConfig"
DISPLAY_CONFIG_IFACE="org.gnome.Mutter.DisplayConfig"
TOUCHSCREEN_SCHEMA="org.gnome.settings-daemon.peripherals.touchscreen"
TOUCHSCREEN_MAPPING_SCHEMA="org.gnome.desktop.peripherals.touchscreen"
MUTTER_KEYBINDINGS_SCHEMA="org.gnome.mutter.keybindings"
SESSION_SCHEMA="org.gnome.desktop.session"
SCREENSAVER_SCHEMA="org.gnome.desktop.screensaver"
POWER_SCHEMA="org.gnome.settings-daemon.plugins.power"
LOCKDOWN_SCHEMA="org.gnome.desktop.lockdown"

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this as the logged-in desktop user, not with sudo."
  echo "The script will ask for sudo only when it needs system-level changes."
  exit 1
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

schema_exists() {
  gsettings list-schemas | grep -Fxq "$1"
}

relocatable_schema_exists() {
  gsettings list-relocatable-schemas | grep -Fxq "$1"
}

key_exists() {
  gsettings list-keys "$1" | grep -Fxq "$2"
}

set_gsetting_if_available() {
  local schema="$1"
  local key="$2"
  local value="$3"
  local description="$4"

  if schema_exists "$schema" && key_exists "$schema" "$key"; then
    echo "$description"
    gsettings set "$schema" "$key" "$value"
  else
    echo "Warning: $schema $key is not available on this system." >&2
  fi
}

map_touchscreens_to_output() {
  local output="$1"
  local target_edid="$2"
  local found=0

  if ! relocatable_schema_exists "$TOUCHSCREEN_MAPPING_SCHEMA"; then
    echo "Warning: $TOUCHSCREEN_MAPPING_SCHEMA is not available on this system." >&2
    return
  fi

  echo "Mapping touchscreens to ${output} (${target_edid})..."
  for event in /dev/input/event*; do
    [[ -e "$event" ]] || continue
    if ! udevadm info --query=property --name="$event" 2>/dev/null | grep -Fxq "ID_INPUT_TOUCHSCREEN=1"; then
      continue
    fi

    local event_name input_dir name vendor product settings_path
    event_name="$(basename "$event")"
    input_dir="$(readlink -f "/sys/class/input/${event_name}/device")"
    name="$(cat "${input_dir}/name" 2>/dev/null || true)"
    vendor="$(cat "${input_dir}/id/vendor" 2>/dev/null || true)"
    product="$(cat "${input_dir}/id/product" 2>/dev/null || true)"

    if [[ -z "$vendor" || -z "$product" ]]; then
      echo "Warning: could not read touchscreen vendor/product for ${event}; skipped." >&2
      continue
    fi

    settings_path="/org/gnome/desktop/peripherals/touchscreens/${vendor}:${product}/"
    gsettings set "${TOUCHSCREEN_MAPPING_SCHEMA}:${settings_path}" output "$target_edid"
    echo "Mapped ${name:-$event} (${vendor}:${product}) to ${output}."
    found=1
  done

  if [[ "$found" -eq 0 ]]; then
    echo "Warning: no touchscreen input devices were detected." >&2
  fi
}

map_gdm_touchscreens_to_output() {
  local gdm_user="$1"
  local gdm_home="$2"
  local output="$3"
  local target_edid="$4"
  local found=0

  if ! relocatable_schema_exists "$TOUCHSCREEN_MAPPING_SCHEMA"; then
    echo "Warning: $TOUCHSCREEN_MAPPING_SCHEMA is not available on this system." >&2
    return
  fi

  echo "Mapping GDM login-screen touchscreens to ${output} (${target_edid})..."
  for event in /dev/input/event*; do
    [[ -e "$event" ]] || continue
    if ! udevadm info --query=property --name="$event" 2>/dev/null | grep -Fxq "ID_INPUT_TOUCHSCREEN=1"; then
      continue
    fi

    local event_name input_dir name vendor product settings_path
    event_name="$(basename "$event")"
    input_dir="$(readlink -f "/sys/class/input/${event_name}/device")"
    name="$(cat "${input_dir}/name" 2>/dev/null || true)"
    vendor="$(cat "${input_dir}/id/vendor" 2>/dev/null || true)"
    product="$(cat "${input_dir}/id/product" 2>/dev/null || true)"

    if [[ -z "$vendor" || -z "$product" ]]; then
      echo "Warning: could not read touchscreen vendor/product for ${event}; skipped GDM mapping." >&2
      continue
    fi

    settings_path="/org/gnome/desktop/peripherals/touchscreens/${vendor}:${product}/"
    sudo -u "$gdm_user" env HOME="$gdm_home" XDG_CONFIG_HOME="${gdm_home}/.config" \
      dbus-run-session gsettings set "${TOUCHSCREEN_MAPPING_SCHEMA}:${settings_path}" output "$target_edid"
    echo "Mapped GDM ${name:-$event} (${vendor}:${product}) to ${output}."
    found=1
  done

  if [[ "$found" -eq 0 ]]; then
    echo "Warning: no touchscreen input devices were detected for GDM mapping." >&2
  fi
}

require_command dbus-run-session
require_command gdbus
require_command gsettings
require_command python3
require_command readlink
require_command sudo
require_command udevadm

echo "Refreshing sudo credentials for system-level steps..."
sudo -v

echo "Reading current GNOME monitor state..."
state="$(
  gdbus call --session \
    --dest "$DISPLAY_CONFIG_DEST" \
    --object-path "$DISPLAY_CONFIG_PATH" \
    --method "$DISPLAY_CONFIG_IFACE.GetCurrentState"
)"

export MUTTER_STATE="$state"
mapfile -t display_config < <(
  python3 - "$OUTPUT" "$TRANSFORM" <<'PY'
import os
import re
import sys

output = sys.argv[1]
transform = int(sys.argv[2])
state = os.environ["MUTTER_STATE"]


def balanced_chunk(text: str, start: int) -> tuple[str, int]:
    pairs = {"[": "]", "(": ")", "{": "}"}
    opening = text[start]
    closing = pairs[opening]
    stack = [closing]
    i = start + 1
    quote = False
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "'":
                quote = False
        else:
            if ch == "'":
                quote = True
            elif ch in pairs:
                stack.append(pairs[ch])
            elif ch == stack[-1]:
                stack.pop()
                if not stack:
                    return text[start : i + 1], i + 1
        i += 1
    raise SystemExit("Could not parse Mutter display state.")


def split_top_level_list(list_text: str) -> list[str]:
    inner = list_text[1:-1].strip()
    if not inner:
        return []
    items = []
    start = 0
    stack = []
    quote = False
    pairs = {"[": "]", "(": ")", "{": "}"}
    for i, ch in enumerate(inner):
        if quote:
            if ch == "'":
                quote = False
            continue
        if ch == "'":
            quote = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
        elif ch == "," and not stack:
            items.append(inner[start:i].strip())
            start = i + 1
    items.append(inner[start:].strip())
    return items


def mode_for_output(monitor_item: str) -> tuple[str, str]:
    spec_match = re.match(r"\(\('([^']+)', '[^']*', '[^']*', '[^']*'\), ", monitor_item)
    if not spec_match:
        raise SystemExit(f"Could not parse monitor item: {monitor_item}")
    connector = spec_match.group(1)
    modes_start = monitor_item.find("[", spec_match.end())
    modes_text, _ = balanced_chunk(monitor_item, modes_start)
    first = preferred = current = None
    for mode_item in split_top_level_list(modes_text):
        mode_match = re.match(r"\('([^']+)'", mode_item)
        if not mode_match:
            continue
        mode = mode_match.group(1)
        first = first or mode
        if "'is-preferred': <true>" in mode_item:
            preferred = mode
        if "'is-current': <true>" in mode_item:
            current = mode
    mode = current or preferred or first
    if mode is None:
        raise SystemExit(f"Could not find a usable mode for output {connector!r}.")
    return connector, mode


serial_match = re.match(r"\(uint32 (\d+),", state)
if not serial_match:
    raise SystemExit("Could not read Mutter display serial.")
serial = serial_match.group(1)

first_list = state.find("[")
monitors_text, idx = balanced_chunk(state, first_list)
second_list = state.find("[", idx)
logical_text, _ = balanced_chunk(state, second_list)

modes = dict(mode_for_output(item) for item in split_top_level_list(monitors_text))
if output not in modes:
    raise SystemExit(f"Could not find output {output!r} in Mutter display state.")

logical_entries = []
output_found_in_active_layout = False
for item in split_top_level_list(logical_text):
    match = re.match(
        r"\((-?\d+), (-?\d+), ([0-9.]+), (?:uint32 )?(\d+), (true|false), ",
        item,
    )
    if not match:
        raise SystemExit(f"Could not parse logical monitor item: {item}")
    x, y, scale, current_transform, primary = match.groups()
    specs_start = item.find("[", match.end())
    specs_text, _ = balanced_chunk(item, specs_start)
    connectors = re.findall(r"\('([^']+)', '[^']*', '[^']*', '[^']*'\)", specs_text)
    if not connectors:
        raise SystemExit(f"Could not parse connectors from logical monitor item: {item}")
    if output in connectors:
        current_transform = str(transform)
        output_found_in_active_layout = True
    monitor_specs = ", ".join(f"('{conn}', '{modes[conn]}', {{}})" for conn in connectors)
    logical_entries.append(
        f"({x}, {y}, {scale}, uint32 {current_transform}, {primary}, [{monitor_specs}])"
    )

if not output_found_in_active_layout:
    logical_entries.append(
        f"(0, 0, 1.0, uint32 {transform}, true, [('{output}', '{modes[output]}', {{}})])"
    )

print(serial)
print("[" + ", ".join(logical_entries) + "]")
PY
)
serial="${display_config[0]}"
monitor_config="${display_config[1]}"
target_edid="$(
  python3 - "$OUTPUT" <<'PY'
import os
import re
import sys

output = sys.argv[1]
state = os.environ["MUTTER_STATE"]
match = re.search(
    r"\(\('%s', '([^']*)', '([^']*)', '([^']*)'\), " % re.escape(output),
    state,
)
if not match:
    raise SystemExit(f"Could not find EDID information for output {output!r}.")
print("[" + ", ".join(repr(part) for part in match.groups()) + "]")
PY
)"

echo "Applying ${OUTPUT} transform ${TRANSFORM} while preserving active monitors..."
gdbus call --session \
  --dest "$DISPLAY_CONFIG_DEST" \
  --object-path "$DISPLAY_CONFIG_PATH" \
  --method "$DISPLAY_CONFIG_IFACE.ApplyMonitorsConfig" \
  "$serial" 2 "$monitor_config" "{}" >/dev/null

map_touchscreens_to_output "$OUTPUT" "$target_edid"

set_gsetting_if_available "$TOUCHSCREEN_SCHEMA" orientation-lock true   "Locking GNOME touchscreen orientation..."

set_gsetting_if_available "$MUTTER_KEYBINDINGS_SCHEMA" rotate-monitor "[]"   "Disabling the GNOME rotate-monitor keyboard shortcut..."

set_gsetting_if_available "$SESSION_SCHEMA" idle-delay "$IDLE_DELAY_SECONDS"   "Setting screen blank timeout to ${IDLE_DELAY_SECONDS} seconds..."

set_gsetting_if_available "$SCREENSAVER_SCHEMA" lock-enabled false   "Disabling lock after screen blank..."

set_gsetting_if_available "$LOCKDOWN_SCHEMA" disable-lock-screen true   "Disabling the GNOME lock screen..."

set_gsetting_if_available "$POWER_SCHEMA" sleep-inactive-ac-type nothing   "Disabling automatic suspend while plugged in..."

set_gsetting_if_available "$POWER_SCHEMA" sleep-inactive-battery-type nothing   "Disabling automatic suspend while on battery..."

echo "Disabling the accelerometer auto-rotation service..."
sudo systemctl daemon-reload
sudo systemctl mask --now iio-sensor-proxy.service

monitors_xml="${HOME}/.config/monitors.xml"
if [[ -f "$monitors_xml" ]]; then
  gdm_user="${GDM_USER:-gdm}"
  gdm_group="${GDM_GROUP:-gdm}"
  if getent passwd "$gdm_user" >/dev/null && getent group "$gdm_group" >/dev/null; then
    gdm_home="$(getent passwd "$gdm_user" | cut -d: -f6)"
    if [[ -z "$gdm_home" || "$gdm_home" == "/" ]]; then
      gdm_home="/var/lib/gdm3"
    fi

    echo "Copying saved monitor layout to ${gdm_home}/.config for the login screen..."
    sudo install -d -o "$gdm_user" -g "$gdm_group" -m 0755 "${gdm_home}/.config"
    sudo install -o "$gdm_user" -g "$gdm_group" -m 0644 "$monitors_xml" "${gdm_home}/.config/monitors.xml"
    map_gdm_touchscreens_to_output "$gdm_user" "$gdm_home" "$OUTPUT" "$target_edid"
  else
    echo "Warning: GDM user/group not found; skipped login-screen monitor layout copy." >&2
  fi
else
  echo "Warning: $monitors_xml does not exist yet; skipped login-screen monitor layout copy." >&2
fi

echo "Done. ${OUTPUT} is set to transform ${TRANSFORM}, GNOME rotation is locked, and auto-rotation is disabled."
