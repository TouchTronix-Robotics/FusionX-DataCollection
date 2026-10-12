# FusionX GUI data collection

Record gloves, head stereo video/IMU, and optional wrist video to MCAP.

[Calibration](calibration.md) · [Recording format](recording-format.md) · [Troubleshooting](troubleshooting.md) · [Home](../../README.md)

## Before you start

Download the GUI from [v3.0.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0). Python is included.

| Needed | Setup |
|---|---|
| License | Obtain a key from TouchTronix. |
| Head camera | Supported Arducam B0578 stereo camera; video, head IMU, and factory calibration are required. |
| Gloves | Wired V01.12; close other serial readers. |
| Wrist cameras | Optional: zero, one, or two. Connect before launching. |
| Calibrated output | Current wearer calibration and matching glove-pair file. |

**Windows:** extract the whole ZIP and open `touchtronix-fusionX.exe`; keep `_internal/` beside it.

**Linux:** use a desktop with FUSE 3, then launch as your normal user:

```bash
chmod +x touchtronix-fusionX-v3.0.0-linux-x86_64.AppImage
./touchtronix-fusionX-v3.0.0-linux-x86_64.AppImage
```

Enter your license when prompted. The screenshots below use simulated readings.

## 1. Select the left and right glove ports

| Hand | Linux example | Windows example |
|---|---|---|
| LH | `/dev/ttyUSB0` | `COM3` |
| RH | `/dev/ttyUSB1` | `COM4` |

Touch each glove to confirm its heatmap. Ports/USB identities do not identify hands; choose distinct ports.

![Glove port selection](01-glove-ports.png)

Wait for camera preparation. **Assign Wrists** uses live thumbnails. Restart the app after adding cameras or changing their physical ports.

## 2. Run the user calibration

Click **Calibrate → Start Calibration** after entering a username.

| Pose | Action | Measures |
|---|---|---|
| Open hand | Straighten all fingers; keep pads contact-free. | Resting tactile baseline and open bend endpoint. |
| Closed fist | Close every finger, including thumb. | Closed bend endpoint. |

Hold each pose through its collection cue. Renew calibration after re-wearing gloves or changing wearer/session. Use a new username to preserve an existing file.

![Start wearer calibration](02-calibration-start.png)

| Open hand | Closed fist |
|---|---|
| ![Open-hand pose](02b-calibration-open.png) | ![Closed-fist pose](02c-calibration-fist.png) |

## 3. Select the user and glove calibrations

| Selector | File |
|---|---|
| **User Calibration** | Current wearer's file from step 2. |
| **Glove Calibration** | This physical pair's pressure or polynomial force file. |

**Browse** accepts files outside the app folder. The [example calibration](../../calibrations/example_perpixel_pressure.json) applies only to **LH_1/RH_1**. See [file requirements](calibration.md).

![Calibration selectors](03-calibrations.png)

## 4. Choose where recordings are saved

Click **Save Folder** and select the final session folder. Files are written directly there; existing recordings are preserved.

![Recording destination](04-save-folder.png)

## 5. Start and stop data collection

1. Click **Start Record**; wait for **Recording** and increasing counters.
2. Perform the task.
3. Click **Stop Record**; wait for **Saved** before opening files or disconnecting devices.

**Space** also starts/stops from the main window. Setup failure creates no recording files.

![Recording controls](05-recording-preview-off.png)

**Stop Preview / Start Preview** toggles display without stopping recording.

![Camera and tactile preview layout](06-camera-tactile-layout.png)

```text
Selected_folder/
  recording_000.mcap
  recording_001.mcap
```

Segments rotate after 9,000 head frames at the next keyframe (~5 minutes at 30 FPS). Each new recording starts at the next unused index.

## Inspect recordings in Foxglove

Open finished files in [Foxglove Desktop](https://foxglove.dev/download). Install the panel and layout included in the GUI package; see [viewer setup](troubleshooting.md#foxglove-panel-or-layout-is-missing). Use Data Source Info for counts and Raw Messages for exact fields.
