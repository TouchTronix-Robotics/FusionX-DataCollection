# FusionX-DataCollection

Multimodal data collection app — records synchronized OAK-D stereo video + tactile glove streams to disk.

## Download

Grab the latest release from the [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases) page:

- **Linux**: `.AppImage` — make it executable and run
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
Add your user to the `dialout` group, then log out and back in:

```bash
sudo usermod -aG dialout $USER
```

### AppImage

Make the AppImage executable:

```bash
chmod +x touchtronix-datacollection-*.AppImage
./touchtronix-datacollection-*.AppImage
```

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

1. **Calibration tab** — select LH/RH glove serial ports, enter a username, click **Start Calibration**. Follow the on-screen prompts. The profile is saved under `calibrations/<user>.json`.
2. **Recording tab** — select serial ports, pick an output directory and episode name, (optional) load a calibration file, click **Start Preview** → **Start Recording**. Press **Stop Recording** to save.

Recordings are written as per-frame images plus a Parquet sensor log. Convert to video with the post-processing tool bundled in the internal repo.
