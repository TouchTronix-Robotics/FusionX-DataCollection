# FusionX-DataCollection Standalone App

Use the standalone app releases when you want a ready-to-run recording GUI, Foxglove playback workspace, or offline post-processing utility.

Download pre-built assets from the [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases) page.

## Release assets

- **Linux GUI**: `touchtronix-fusionX-VERSION-linux-x86_64.AppImage` — unified fullscreen touch GUI; pass `--windowed` for desktop use
- **Linux CLI recorder**: `touchtronix-fusionX-cli-VERSION-linux-x86_64.AppImage` — terminal recording
- **Windows GUI**: `touchtronix-fusionX-VERSION-windows-x86_64.exe` — unified fullscreen touch GUI; pass `--windowed` for desktop use
- **Windows CLI recorder**: `touchtronix-fusionX-cli-VERSION-windows-x86_64.exe` — terminal recording

Replace `VERSION` with the downloaded release version.

A valid license key is required on first launch.

## Foxglove viewer downloads

Current viewer files are tracked directly in this repository rather than bundled into the application release archives:

- [`touchtronixrobotics.fusionx-tactile-panel-0.2.2.foxe`](touchtronixrobotics.fusionx-tactile-panel-0.2.2.foxe) — self-contained **FusionX Tactile** panel extension.
- [`fusionx_foxglove_layout.json`](fusionx_foxglove_layout.json) — canonical camera, tactile, OAK IMU, and separate LH/RH glove IMU workspace.

To view a current `touchtronix.raw.v2` recording:

1. Install [Foxglove Desktop](https://foxglove.dev/download).
2. Download both files above. On each GitHub file page, select **Download raw file**.
3. Open or drag the `.foxe` file into Foxglove Desktop, then reload Foxglove. Local extension installation may require a Foxglove developer seat.
4. Import `fusionx_foxglove_layout.json` from the Foxglove layout menu. Install the extension first so the custom tactile panel resolves correctly.
5. Open any `recording_*.mcap` segment.

The tactile panel displays both gloves simultaneously from `/glove/lh/tactile` and `/glove/rh/tactile`. It supports raw tactile, raw bend, total finger force, and per-pixel force views when corresponding fields exist in the recording. The package needs no source checkout, Node.js, or npm.

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
./touchtronix-fusionX-VERSION-linux-x86_64.AppImage --windowed
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

Run `touchtronix-fusionX-VERSION-windows-x86_64.exe` directly after replacing `VERSION` with the downloaded release version. It opens fullscreen by default; pass `--windowed` for desktop use. OAK runtime dependencies are bundled.

If the wireless glove dongle is not detected, install the [CH340 USB-serial driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html).

## Using the app

1. **Calibration tab** — select LH/RH glove serial ports, enter a username, click **Start Calibration**, and follow the on-screen prompts. The profile is saved under `~/Touchtronix/calibrations/<user>.json` when using the recommended AppImage layout.
2. **Recording tab** — select serial ports, pick an output directory and episode name, and optionally load user and glove force/pressure calibration files.
3. Choose **Live View** before starting preview. It defaults off to reduce processor load and remains locked for that preview/recording session; it affects visualization only, not recorded sensor rates.
4. Click **Start Preview** → **Start Recording**, then press **Stop Recording** to save. If an external keyboard is connected, the space bar also starts and stops recording.

Recordings are written as segmented MCAP raw capture files. Open them directly in Foxglove using the viewer files above. Use the standalone MCAP exporter below only when per-frame image folders, Parquet sensor logs, or calibration JSON files are needed for offline analysis.

## Headless CLI recording

The CLI release asset records directly from a terminal and writes the same dataset format as the GUI. A valid license must already be installed; launch the GUI once to enter the license key before using the CLI.

Linux:

```bash
chmod +x touchtronix-fusionX-cli-VERSION-linux-x86_64.AppImage
./touchtronix-fusionX-cli-VERSION-linux-x86_64.AppImage test1 \
  --glove-port-lh /dev/ttyACM1 \
  --glove-port-rh /dev/ttyACM0 \
  --calibration ~/Touchtronix/calibrations/user.json \
  --show-metrics
```

Windows:

```powershell
.\touchtronix-fusionX-cli-VERSION-windows-x86_64.exe test1 `
  --glove-port-lh COM4 `
  --glove-port-rh COM5 `
  --calibration C:\Users\you\Touchtronix\calibrations\user.json `
  --show-metrics
```

Use `Ctrl+C` to stop and save the recording.

Common options:

- `episode` — optional episode folder name. If omitted, the app uses `recording_YYYYMMDD_HHMMSS`.
- `-o`, `--output-dir` — parent dataset directory. The default is `dataset`.
- `--glove-port-lh`, `--glove-port-rh` — left and right glove serial ports. Pass the ports you want recorded.
- `--calibrate USER` — run glove user calibration and save `calibrations/USER.json`.
- `--calibration FILE` — load an existing user calibration JSON.
- `--force-calibration FILE` — load glove force or per-pixel pressure calibration.
- `--jpeg-quality N` — OAK hardware-MJPEG quality for RGB and both mono streams. The default is `90`.
- `--show-metrics` — print FPS and latency metrics about once per second.
- `--trace` — enable DepthAI trace logging for per-node timings.

The CLI is always headless and begins recording immediately. An OAK camera is required; startup stops with an error when no camera is detected. Use `Ctrl+C` to stop and save.

## Standalone post-processing

Recorded episodes contain one or more independently playable `recording_*.mcap` files. Foxglove opens these files directly, so no preview-video conversion step is needed. Install the tactile extension and layout from the [Foxglove viewer downloads](#foxglove-viewer-downloads) section before viewing recordings.

Use the exporter only when analysis tools need extracted images, Parquet tables, or calibration JSON:

```bash
cd FusionX-DataCollection
python3 -m venv .venv
source .venv/bin/activate
pip install -r post_processing/requirements.txt
python post_processing/mcap_exporter.py /path/to/dataset/recording_xxx/recording_*.mcap \
  -o /path/to/dataset/recording_xxx_exported
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
python post_processing\mcap_exporter.py C:\path\to\recording_xxx\recording_*.mcap `
  -o C:\path\to\recording_xxx_exported
```

The MCAP exporter reconstructs:

- `rgb/`, `mono_left/`, `mono_right/` — native camera JPEG folders
- `frames.parquet` — camera-frame table with nearest glove/OAK IMU samples and optional calibrated force columns
- `gloves.parquet` — full-rate raw glove, IMU, and optional `finger_force_N_total` or `finger_force_N_pixels` samples
- `oak_imu.parquet` — full-rate OAK IMU samples
- `user_calibration.json`, `force_calibration.json`, `camera_calibration.json` when present

Dependencies: Python 3.10+, `mcap`, `protobuf`, `numpy`, and `pyarrow`. No OAK camera, DepthAI, PySide, serial, FFmpeg, or license dependencies are required for offline export.

## One-time miniPC configuration

The repository includes `setup-miniPC-ubuntu.sh` for Ubuntu/GNOME miniPC touchscreen deployments. Run it once as the logged-in desktop user after the touchscreen is connected:

```bash
cd FusionX-DataCollection
chmod +x setup-miniPC-ubuntu.sh
./setup-miniPC-ubuntu.sh
```

Do not run the script with `sudo`; it asks for sudo only for the system-level steps. By default it targets display output `DSI-1`, applies transform `3`, and sets the screen blank timeout to `120` seconds. Override those defaults when needed:

```bash
OUTPUT=HDMI-1 TRANSFORM=1 IDLE_DELAY_SECONDS=300 ./setup-miniPC-ubuntu.sh
```

The script configures the miniPC for kiosk-style recording:

- Rotates the target display while preserving the active monitor layout.
- Maps detected touchscreens to the target display.
- Locks GNOME touchscreen orientation and disables the rotate-monitor shortcut.
- Sets the screen blank timeout, disables the lock screen, and disables automatic suspend.
- Masks the accelerometer auto-rotation service.
- Copies the saved monitor layout and touchscreen mapping to the GDM login screen when available.
