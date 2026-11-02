# FusionX-DataCollection Standalone App

Use the **v1.3.1 Windows GUI** for recording with v1 conductive-fabric gloves and Arducam AR0234 cameras. Download it from the [v1.3.1 release](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v1.3.1).

## Release assets

- **Windows GUI:** `touchtronix-fusionX-v1.3.1-windows-x86_64.zip`. Extract the entire ZIP and keep all files together.
- **Windows SDK:** `tactile_glove_sdk-0.1.0-cp312-cp312-win_amd64.whl`.
- **Linux SDK:** `tactile_glove_sdk-0.1.0-cp312-cp312-linux_x86_64.whl`.

The standalone GUI includes its own Python runtime. The separate SDK wheels require 64-bit CPython 3.12; see the [SDK README](README-sdk.md). The refreshed release includes a Windows GUI ZIP; the Linux AppImage and packaged headless CLI instructions below apply to older releases.

A valid license key is required on first launch. The Windows GUI requires an enabled Intel integrated GPU and current Intel graphics driver. It validates Quick Sync MJPEG decoding and H.264 encoding before camera preview or recording can start.

## Foxglove viewer downloads

Use the viewer files included in the extracted GUI folder's `foxglove/` subfolder:

- `touchtronixrobotics.fusionx-tactile-panel-0.2.4.foxe` — self-contained **FusionX Tactile** panel extension.
- `fusionx_foxglove_layout.json` — head/wrist camera, tactile, head-camera IMU, and LH/RH glove IMU workspace.

To view a current `touchtronix.raw.v4` recording:

1. Install [Foxglove Desktop](https://foxglove.dev/download).
2. Open or drag the bundled `.foxe` file into Foxglove Desktop, then reload Foxglove. Local extension installation may require a Foxglove developer seat.
3. Import the bundled `fusionx_foxglove_layout.json` from the Foxglove layout menu. Install the extension first so the custom tactile panel resolves correctly.
4. Open any `recording_*.mcap` segment.

The tactile panel displays both gloves simultaneously from `/glove/lh/tactile` and `/glove/rh/tactile`. It has **Raw ADC** and **Pixel Force** modes with aligned bend bars. Pixel Force requires calibrated per-pixel force fields in the recording. The package needs no source checkout, Node.js, or npm.

The older standalone [panel 0.2.3](touchtronixrobotics.fusionx-tactile-panel-0.2.3.foxe) and [layout](fusionx_foxglove_layout.json) remain in this branch for earlier recordings. Use the files bundled with the refreshed app for its current Arducam recordings.

## Legacy Linux setup

The following OAK/AppImage setup applies to earlier Linux releases. It is separate from the refreshed Windows v1.3.1 GUI.

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

Extract `touchtronix-fusionX-v1.3.1-windows-x86_64.zip` and open the extracted `touchtronix-fusionX-v1.3.1-windows-x86_64` folder. Run `touchtronix-fusionX.exe` from that folder. Keep `_internal/` beside the executable; the `foxglove/` folder contains the viewer files.

The app opens fullscreen by default. To use a desktop window, run this from the extracted folder in PowerShell:

```powershell
.\touchtronix-fusionX.exe --windowed
```

If the wireless glove dongle is not detected, install the [CH340 USB-serial driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html).

## Using the app

1. Connect the head stereo camera before launching. Wait for camera discovery, head-camera IMU/flash preparation, and QSV validation to finish. Head-IMU startup commonly takes 15–30 seconds. Camera preview then starts automatically while idle; it creates no recording files and keeps head-IMU polling paused.
2. Select **LH / RH** glove serial ports. Each selected glove appears in the idle tactile/bend preview so you can verify the hand assignment. If wrist cameras are connected, use **Assign Wrists** to select LEFT/RIGHT from live thumbnails. Only assigned wrist cameras appear in preview and recording. The current assignment dialog maps the two wrist cameras as a pair; leave wrists unassigned for head-only capture. Reuse the same physical USB ports, and restart the app after changing the connected camera set or ports.
3. Click **Calibrate**, enter the wearer name, and follow the OPEN/FIST instructions. User profiles are saved in the app's `calibrations/` directory. Use **Browse** beside the user/glove calibration selectors to load existing JSON files from another folder. Idle camera and glove readers release their devices for calibration, then resume afterward when preview is enabled.
4. Use **Save Folder** to select the exact pre-generated destination folder. The app writes numbered `recording_###.mcap` segments directly into it and starts at the first unused index on later recordings.
5. Click **Start Record / Stop Record**, or press **Space** to start and stop capture. Space does not trigger recording while editing text or working in a child dialog.
6. Use **Start Preview / Stop Preview** while idle or recording. The preview preference is retained across recordings, calibration, and wrist assignment. Visualization does not change recorded sensor rates.

The head camera records intact 3840×1200 side-by-side H.264; each assigned wrist records 1920×1080 H.264. Only the head camera supplies camera IMU samples. Recordings use segmented `touchtronix.raw.v4` MCAP files and open directly in Foxglove with the bundled viewer files.

## Voice cues and logs

Choose **Language → English / 中文** to switch interface text and voice prompts together. The app remembers the choice. Bundled English/Chinese WAVs play offline through miniaudio for calibration, recording announcements, and beeps. One shared output device handles the cues; decoding/playback runs separately from sensor acquisition. Audio failures are logged and recovered independently of recording.

Click **Open Logs / 打开日志** to open the diagnostics folder. If a cue goes silent, click **Open Logs before restarting** to mark the issue time, then stop recording and close the app normally. Share the newest `fusionx-*.jsonl` file and any matching `.jsonl.1`, `.2`, or `.3` backups. Logs normally live in `logs/` beside the app; an unwritable location falls back to the current user's local application-data or temporary directory.

Diagnostics include the build revision, audio backend/cue/recovery state, and read-only Windows endpoint/session checks. Digital peaks do not confirm acoustic speaker output. Microphone audio, sensor samples, typed text, and license keys are not intentionally collected.

## Legacy packaged headless CLI recording

The following commands refer to packaged CLI assets from earlier releases. The refreshed v1.3.1 release does not include a CLI executable.

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

## Legacy standalone post-processing

The retained exporter below targets earlier OAK `touchtronix.raw.v2` recordings. It is separate from the refreshed Arducam H.264 `touchtronix.raw.v4` pipeline; open current recordings directly in Foxglove with the bundled viewer files.

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

## Legacy one-time miniPC configuration

This Ubuntu/GNOME helper is retained for earlier Linux deployments and is separate from the current Windows GUI.

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
