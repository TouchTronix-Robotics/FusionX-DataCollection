# FusionX-DataCollection Standalone App

Use the standalone app releases when you want a ready-to-run recording GUI or offline post-processing utility.

Download pre-built assets from the [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases) page.

## Release assets

- **Linux desktop**: `touchtronix-fusionX-PC-*-linux-x86_64.AppImage` — full desktop GUI
- **Linux miniPC / touchscreen**: `touchtronix-fusionX-miniPC-*-linux-x86_64.AppImage` — fullscreen touch GUI
- **Linux CLI recorder**: `touchtronix-fusionX-cli-*-linux-x86_64.AppImage` — terminal recording
- **Windows desktop**: `touchtronix-fusionX-PC-*-windows-x86_64.zip` — full desktop GUI
- **Windows miniPC / touchscreen**: `touchtronix-fusionX-miniPC-*-windows-x86_64.zip` — fullscreen touch GUI
- **Windows CLI recorder**: `touchtronix-fusionX-cli-*-windows-x86_64.zip` — terminal recording

A valid license key is required on first launch.

## Linux setup

### OAK camera USB permissions

The OAK camera requires udev rules to access USB devices without root. Run the following **once** after first install:

```bash
sudo wget -qO- https://raw.githubusercontent.com/luxonis/depthai-python/main/docs/install_depthai.sh | sudo bash
```

Then replug the OAK camera. No reboot required.

### Glove serial port access

Tactile gloves appear as `/dev/ttyUSB*` with the wireless dongle or `/dev/ttyACM*` with wired USB. Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Then fully log out of Ubuntu and log back in so the permission change applies to GUI apps. Rebooting also works.

### AppImage layout

Recommended folder layout:

```bash
mkdir -p ~/Touchtronix
mv ~/Downloads/touchtronix-*.AppImage ~/Touchtronix/
cd ~/Touchtronix
chmod +x touchtronix-*.AppImage
./touchtronix-fusionX-PC-*-linux-x86_64.AppImage
```

The app stores data next to the AppImage:

- `~/Touchtronix/calibrations/` — glove/user calibration JSON files
- `~/Touchtronix/dataset/` — recordings

Keep the AppImage in `~/Touchtronix` so calibration files and recordings stay in one easy-to-find folder.

If the app doesn't launch, your system may need FUSE2:

```bash
# Ubuntu 24.04+
sudo apt install libfuse2t64

# Ubuntu 22.04 or older
sudo apt install libfuse2
```

## Windows setup

Extract `touchtronix-fusionX-PC-*-windows-x86_64.zip` and run `touchtronix-fusionX-PC.exe`. For the fullscreen touch GUI, extract `touchtronix-fusionX-miniPC-*-windows-x86_64.zip` and run `touchtronix-fusionX-miniPC.exe`. OAK drivers are bundled.

If the wireless glove dongle is not detected, install the [CH340 USB-serial driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html).

## Using the app

1. **Calibration tab** — select LH/RH glove serial ports, enter a username, click **Start Calibration**, and follow the on-screen prompts. The profile is saved under `~/Touchtronix/calibrations/<user>.json` when using the recommended AppImage layout.
2. **Recording tab** — select serial ports, pick an output directory and episode name, optionally load a calibration file, click **Start Preview** → **Start Recording**, then press **Stop Recording** to save. If an external keyboard is connected, you can also press the space bar to start and stop recording.

Recordings are written as segmented MCAP raw capture files. Use the standalone
MCAP exporter below to reconstruct per-frame image folders and Parquet sensor
logs on an offline workstation.

## Headless CLI recording

The CLI release asset records directly from a terminal and writes the same dataset format as the GUI. A valid license must already be installed; launch the GUI once to enter the license key before using the CLI.

Linux:

```bash
chmod +x touchtronix-fusionX-cli-*-linux-x86_64.AppImage
./touchtronix-fusionX-cli-*-linux-x86_64.AppImage test1 --headless \
  --glove-port-lh /dev/ttyACM1 \
  --glove-port-rh /dev/ttyACM0 \
  --calibration ~/Touchtronix/calibrations/user.json \
  --show-metrics
```

Windows:

```powershell
.\touchtronix-fusionX-cli.exe test1 --headless `
  --glove-port-lh COM4 `
  --glove-port-rh COM5 `
  --calibration C:\Users\you\Touchtronix\calibrations\user.json `
  --show-metrics
```

Use `Ctrl+C` to stop and save the recording.

Common options:

- `episode` — optional episode folder name. If omitted, the app uses `recording_YYYYMMDD_HHMMSS`.
- `-o`, `--output-dir` — parent dataset directory. The default is `dataset`.
- `--headless` — start recording immediately without a preview window.
- `--glove-port-lh`, `--glove-port-rh` — left and right glove serial ports. Pass the ports you want recorded.
- `--calibrate USER` — run glove user calibration and save `calibrations/USER.json`.
- `--calibration FILE` — load an existing user calibration JSON.
- `--force-calibration FILE` — load glove force or per-pixel pressure calibration.
- `--jpeg-quality N` — RGB JPEG quality. The default is `95`.
- `--show-metrics` — print FPS and latency metrics about once per second.

If no OAK camera is detected, the CLI runs in glove-only mode. If `--headless` is omitted, the CLI opens the legacy preview window; press `s` to start recording and `q` to stop.

## Standalone post-processing

Recorded episodes contain one or more `recording_*.mcap` files. First export
those MCAP segments into image folders and Parquet logs, then convert the
exported episode into MP4 preview videos.

```bash
cd FusionX-DataCollection
python3 -m venv .venv
source .venv/bin/activate
pip install -r post_processing/requirements.txt
sudo apt install ffmpeg  # Linux, if ffmpeg/ffprobe are not already installed
python post_processing/mcap_exporter.py /path/to/dataset/recording_xxx/recording_*.mcap \
  -o /path/to/dataset/recording_xxx_exported
python post_processing/convert_to_video.py /path/to/dataset/recording_xxx_exported
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
python post_processing\mcap_exporter.py C:\path\to\recording_xxx\recording_*.mcap `
  -o C:\path\to\recording_xxx_exported
python post_processing\convert_to_video.py C:\path\to\recording_xxx_exported
```

The MCAP exporter reconstructs:

- `rgb/`, `mono_left/`, `mono_right/` - per-frame image folders
- `frames.parquet` - camera-frame table with aligned glove and OAK IMU columns
- `gloves.parquet` - full-rate glove samples
- `oak_imu.parquet` - full-rate OAK IMU samples
- `user_calibration.json`, `force_calibration.json`, `camera_calibration.json` when present

The video converter writes these outputs next to `frames.parquet`:

- `rgb.mp4` — RGB image sequence encoded as H.264
- `preview_glove.mp4` — tactile pressure/bend visualization
- `preview_all.mp4` — RGB + mono stereo + glove composite preview
- `video_meta.json` — timestamps, FPS, stream metadata

Dependencies: Python 3.10+, `mcap`, `numpy`, `opencv-python`, `pyarrow`, `tqdm`,
plus system `ffmpeg` and `ffprobe` on `PATH` with H.264/libx264 support. No OAK
camera, DepthAI, PySide, serial, or license dependencies are required for
offline export or video conversion.

## One-time miniPC configuration

The repository includes `setup-miniPC.sh` for Ubuntu/GNOME miniPC touchscreen deployments. Run it once as the logged-in desktop user after the touchscreen is connected:

```bash
cd FusionX-DataCollection
chmod +x setup-miniPC.sh
./setup-miniPC.sh
```

Do not run the script with `sudo`; it asks for sudo only for the system-level steps. By default it targets display output `DSI-1`, applies transform `3`, and sets the screen blank timeout to `120` seconds. Override those defaults when needed:

```bash
OUTPUT=HDMI-1 TRANSFORM=1 IDLE_DELAY_SECONDS=300 ./setup-miniPC.sh
```

The script configures the miniPC for kiosk-style recording:

- Rotates the target display while preserving the active monitor layout.
- Maps detected touchscreens to the target display.
- Locks GNOME touchscreen orientation and disables the rotate-monitor shortcut.
- Sets the screen blank timeout, disables the lock screen, and disables automatic suspend.
- Masks the accelerometer auto-rotation service.
- Copies the saved monitor layout and touchscreen mapping to the GDM login screen when available.
