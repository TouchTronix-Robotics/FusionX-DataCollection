# FusionX GUI data collection

Use the FusionX desktop application to collect glove tactile/bend/IMU data, head stereo video and head IMU, and optional wrist video into MCAP recordings. The application manages sensor startup, wearer/glove calibration, recording, and recovery.

The GUI package includes its Python runtime. Start here if you want the complete FusionX recording workflow with the supported Arducam cameras.

- [Calibration reference](calibration.md)
- [MCAP recording format](recording-format.md)
- [GUI troubleshooting](troubleshooting.md)
- [Documentation home](../../README.md)

## Before you start

Obtain the **V3 thin-film GUI package**, license key, and matching glove-pair calibration from TouchTronix. Public application releases, when published, are listed under [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases); choose a package explicitly intended for this configuration. The V2 v2.2.0 application is for the older glove configuration. This documentation branch does not install the recording application.

- **Windows:** extract the entire ZIP, then open `touchtronix-fusionX.exe`. Keep `_internal/` beside it.
- **Linux:** use a desktop with FUSE 3, mark the AppImage executable, and launch it as your normal user. It includes its Python runtime and application dependencies.
- Connect the head stereo camera and the glove(s) to record. Close other programs using them.
- Connect optional wrist cameras before launching. Assign one wrist to LH or RH, or assign both; two wrists are not required.
- Create a destination folder on persistent storage with enough space for video.

Example Linux launch; replace `<version>` with the version of the package supplied to you:

```bash
chmod +x touchtronix-fusionX-<version>-linux-x86_64.AppImage
./touchtronix-fusionX-<version>-linux-x86_64.AppImage
```

The default `dataset/` and `calibrations/` folders live beside the application or AppImage. **Save Folder** and **Browse** select other locations. Enter your license key when prompted; activation is stored under `~/.config/touchtronix/license.json`.

The screenshots below are **illustrations rendered from the current GUI with example ports, filenames, and simulated readings**. They are not evidence of a physical recording session. Windows uses the same controls; native pickers and serial-port names differ.

## 1. Select the left and right glove ports

Choose the physical left glove in **LH** and the right glove in **RH**. Use the circular-arrow button to refresh the port list. Do not select the same port for both hands.

| Control | Linux example | Windows example |
|---|---|---|
| **LH** | `/dev/ttyUSB0` | `COM3` |
| **RH** | `/dev/ttyUSB1` | `COM4` |

Port numbering and USB adapter identifiers do not establish handedness. Touch one glove at a time and confirm that the correct **LH/RH raw heatmap** responds. These tactile/bend previews remain available while idle when camera preview is stopped.

![Current GUI with explicitly selected LH/RH glove ports and five-patch raw previews](01-glove-ports.png)

The head camera is detected automatically. Allow startup and head IMU preparation to finish. **Assign Wrists** uses live thumbnails to tag optional cameras, whose reported serial numbers can be identical. The app discovers camera identities once per launch: restart after adding a camera or moving one to a different physical port.

## 2. Run the user calibration

Click **Calibrate**, enter a username, and click **Start Calibration**. There are exactly two poses:

1. **Open palm / open hand:** wear the gloves, straighten all fingers, and avoid contact or pressure on the tactile pads. Hold through the collection cue. This records resting tactile values and open-hand bend readings.
2. **Closed fist:** close every finger, including the thumb, and hold through the collection cue. This records the closed-fist bend endpoint, not a pressure maximum.

Wait for completion, then click **Close**. Use a new username to preserve an existing file; selecting an existing wearer file intentionally replaces that wearer's calibration when rerun.

![Current user calibration screen with username and Start Calibration](02-calibration-start.png)

| Open hand | Closed fist |
|---|---|
| ![Open-hand calibration guide with five-patch preview](02b-calibration-open.png) | ![Closed-fist calibration guide with five-patch preview](02c-calibration-fist.png) |

The wearer calibration is saved as JSON in `calibrations/`. Renew it whenever the gloves are put on again or the wearer/session changes. The contact-free pressure baseline is a per-pixel median over the final second of the open pose. See the [calibration reference](calibration.md).

## 3. Select the user and glove calibrations

| Selector | Choose |
|---|---|
| **User Calibration** | The current wearer's V01.12 JSON created in step 2. |
| **Glove Calibration** | The supplied pressure or polynomial force JSON for this physical glove pair. |

![Current GUI with wearer and glove-pair calibration selectors](03-calibrations.png)

**Browse** beside either selector opens the native file picker. Files can live outside the application folder. V1/V2 and earlier four-finger calibrations are incompatible; regenerate wearer calibration for all five current finger patches.

Calibrated pressure/force requires both the wearer calibration and the matching glove-pair file. Raw tactile/bend readings are still preserved. The supplied `calibrations/example_perpixel_pressure.json` is specifically for **LH_1/RH_1** and contains pressure in **kPa**, not force in newtons. Do not swap those physical gloves or apply their tables to another pair.

## 4. Choose where recordings are saved

Click **Save Folder**, choose the final session directory, and confirm the operating system's picker. The status line and button tooltip show the destination.

![Current GUI after choosing a persistent session destination](04-save-folder.png)

For example, select the last folder in this structure:

```text
FusionX_Data/
  20261012/
    Tabletop_Task/
      Collector01_Pair01/
```

The app writes directly into the selected folder. **Save Folder chooses the destination; it does not start recording.**

## 5. Start and stop data collection

Check the hand assignments, calibrations, and destination, then click **Start Record**. Wait for **Recording** and increasing counters before starting the task. The head video, head IMU, and factory head calibration are required; selected wrist streams must also become ready. Startup failure leaves no recording files for that attempt.

Click **Stop Record** and wait for **Saved** before opening files or disconnecting devices. **Space** also starts/stops from the main window, except while typing or using child dialogs.

![Recording illustration with preview stopped, timer, and head/glove counters](05-recording-preview-off.png)

Camera preview starts automatically after preparation. **Stop Preview** reduces display/decoding work, while **Start Preview** restores it. Toggling preview does not stop recording or camera capture. The GUI keeps the familiar arrangement: mirrored hands beside the head stereo view, with LH/RH wrist views underneath. Four upper finger pads and a lower inner thumb use the current 4×4 geometry; the palm space remains blank. Bend bars align with the finger columns.

![Current camera/tactile layout with example imagery and blank palm space](06-camera-tactile-layout.png)

Finished files are numbered directly in the chosen folder:

```text
Collector01_Pair01/
  recording_000.mcap
  recording_001.mcap
  ...
```

Segments rotate after 9,000 head frames on the next head keyframe, approximately five minutes at 30 FPS. Each segment starts with independently playable camera data. Another recording uses the next unused index, preserving earlier files.

## Inspect recordings in Foxglove

Open finished `recording_###.mcap` files in [Foxglove Desktop](https://foxglove.dev/download). For the FusionX Tactile panel and full workspace, use the matching extension and layout supplied with the GUI package, or request them from TouchTronix. This branch focuses on glove documentation and SDK examples; standalone Foxglove assets are supplied separately.

Use [Data Source Info](https://docs.foxglove.dev/docs/visualization/panels/data-source-info) for topic counts/time range and Raw Messages for exact fields. See the [MCAP reference](recording-format.md) and [viewer setup guidance](troubleshooting.md#foxglove-panel-or-layout-is-missing).
