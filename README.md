# FusionX-DataCollection

Multimodal data collection app — records synchronized OAK-D stereo video + tactile glove streams to disk.

## Download

Grab the latest release from the [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases) page:

- **Linux desktop**: `touchtronix-datacollection-*.AppImage` — full desktop GUI
- **Linux miniPC / touchscreen**: `touchtronix-touch-*.AppImage` — fullscreen touch GUI
- **Windows**: `.zip` — extract and run `touchtronix-datacollection.exe`

A valid license key is required on first launch.

## Linux Setup

### OAK Camera USB Permissions

The OAK camera requires udev rules to access USB devices without root.
Run the following **once** after first install:

```bash
sudo wget -qO- https://raw.githubusercontent.com/luxonis/depthai-python/main/docs/install_depthai.sh | sudo bash
```

Then replug the OAK camera. No reboot required.

### Glove Serial Port Access

tactile gloves appear as `/dev/ttyUSB*` (wireless dongle) or `/dev/ttyACM*` (wired).
Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Then fully log out of Ubuntu and log back in so the permission change applies to GUI apps. Rebooting also works.

### AppImage

Recommended folder layout:

```bash
mkdir -p ~/Touchtronix
mv ~/Downloads/touchtronix-*.AppImage ~/Touchtronix/
cd ~/Touchtronix
chmod +x touchtronix-*.AppImage
./touchtronix-datacollection-*.AppImage
```

To install the touch AppImage into the Ubuntu app menu and pin it to the GNOME dock, put `install_touch_app.sh` and `touchtronix-touch-*.AppImage` in `~/Touchtronix`, then run:

```bash
cd ~/Touchtronix
chmod +x install_touch_app.sh
./install_touch_app.sh
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

## Windows Setup

Extract the zip and run `touchtronix-datacollection.exe`. OAK drivers are bundled.

If the wireless glove dongle isn't detected, install the [CH340 USB-serial driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html).

## Using the App

1. **Calibration tab** — select LH/RH glove serial ports, enter a username, click **Start Calibration**. Follow the on-screen prompts. The profile is saved under `~/Touchtronix/calibrations/<user>.json` when using the recommended AppImage layout.
2. **Recording tab** — select serial ports, pick an output directory and episode name, (optional) load a calibration file, click **Start Preview** → **Start Recording**. Press **Stop Recording** to save.

Recordings are written as per-frame images plus a Parquet sensor log.

## Standalone Post-Processing

Use the bundled utility to convert one episode folder into MP4 videos:

```bash
cd FusionX-DataCollection
python3 -m venv .venv
source .venv/bin/activate
pip install -r post_processing/requirements.txt
sudo apt install ffmpeg  # Linux, if ffmpeg/ffprobe are not already installed
python post_processing/convert_to_video.py /path/to/dataset/recording_xxx
```

Outputs are written next to `frames.parquet`:

- `rgb.mp4` — RGB image sequence encoded as H.264
- `preview_glove.mp4` — tactile pressure/bend visualization
- `preview_all.mp4` — RGB + mono stereo + glove composite preview
- `video_meta.json` — timestamps, FPS, stream metadata

Dependencies: Python 3.10+, `numpy`, `opencv-python`, `pyarrow`, `tqdm`, plus system `ffmpeg` and `ffprobe` on `PATH` with H.264/libx264 support. No OAK camera, DepthAI, PySide, serial, or license dependencies are required for offline conversion.

## Data Transfer from miniPC

The touch AppImage starts a web download page automatically. Put your laptop/desktop and the miniPC on the same Wi-Fi or LAN, then open:

```text
http://touchtronix.local:8080
```

If that address does not load, use the miniPC IP address shown at the bottom of the touch GUI:

```text
http://<miniPC-ip>:8080
```

The page lists recorded episodes from `~/Touchtronix/dataset/` and lets you download each episode as a ZIP file.

Troubleshooting:

- Make sure both computers are on the same network.
- If using Wi-Fi, disable guest/client isolation on the router.
- If `touchtronix.local` fails, use the raw IP address.
- Allow port `8080` through any firewall on the miniPC.
