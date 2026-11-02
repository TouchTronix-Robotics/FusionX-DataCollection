# FusionX GUI troubleshooting

[GUI guide](README.md) · [Calibration](calibration.md) · [Recording format](recording-format.md) · [Home](../../README.md)

## Packages and compatibility

Use [v3.0.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0) for V01.12 gloves. Python is bundled; a TouchTronix license and supported Arducam head camera are required. AppImage startup is checked on Ubuntu 22.04/24.04; this does not establish physical recording throughput.

## Quick fixes

| Symptom | Action |
|---|---|
| Recording not ready | Connect the head camera before launch; allow 15–30 seconds for head IMU preparation. Close other sensor apps. |
| Camera added/moved | Restart; cameras are discovered once per launch. Assign optional wrists from live thumbnails. |
| Head IMU/calibration missing | Fix the reported setup error; both are required. |
| Linux head access denied | Obtain video **and** head USB control access to `/dev/bus/usb/...`; wrists need video only. Run as normal user. |
| AppImage will not start | Make executable; install FUSE 3. Use a writable folder or choose other data/calibration locations. |
| Encoder unavailable | Use FFmpeg with QSV or CPU `libx264` at native resolution; the app validates the selected executable. |
| Pressure unavailable | Select current wearer + matching glove-pair calibration; filename contains `pressure` or `force`. |
| Wrong glove hand | Touch each glove to verify its heatmap, then correct LH/RH ports. |
| Port access denied | Close other readers; check Linux serial group or Windows driver/COM port. |
| Slow preview | **Stop Preview** reduces display work while recording continues. |
| Reader still closing | Wait and retry; do not open the same port elsewhere. |
| Voice cue goes silent | Check system output/volume, then click **Open Logs / 打开日志 before restarting** to mark the issue; see [audio diagnostics](#audio-prompts-and-diagnostic-logs). |

## Audio prompts and diagnostic logs

Windows and Linux GUI packages include miniaudio and the original English/Chinese WAV cues and beeps. Choose **Language → English / 中文** in the app. No separate audio installation or speech service is needed for the GUI.

If a cue goes silent, click **Open Logs / 打开日志 before restarting**. This opens the automatic log directory and marks the issue time. If practical, try one mouse-controlled start/stop in the same session. Stop recording and close the app normally, then send the newest `fusionx-*.jsonl` file to TouchTronix. Include matching `.jsonl.1`, `.2`, or `.3` backups if present.

Logs normally live in `logs/` beside the application; an unwritable location falls back to the current user's local application-data or temporary directory. No terminal commands or administrator access are needed to collect them.

Diagnostics include build/device details, Space/media-key events, recording state, audio queue/recovery events, and Windows digital audio levels. They do not intentionally collect typed text, microphone/PCM audio, video, glove samples, or license keys. Digital levels cannot confirm physical speaker audibility.

## Foxglove panel or layout is missing

1. Find the packaged `.foxe` and layout JSON.
2. Install the extension in Foxglove Desktop and reload.
3. Import the layout, then open the MCAP.

| Package | Viewer assets |
|---|---|
| Windows ZIP | `foxglove/` beside the executable. |
| Extracted Linux AppImage | `squashfs-root/usr/bin/foxglove/`. |

```bash
./touchtronix-fusionX-v3.0.0-linux-x86_64.AppImage --appimage-extract
```

Use a Foxglove seat supporting [local files/extensions](https://docs.foxglove.dev/docs/security/seat-types).

## Stop and disconnects

Wait for **Saved**. Same-port recovery can leave gaps; inspect MCAP counts/timestamps. If the head IMU helper exits, the episode stops and captured data is preserved.

For Linux serial access, use the device's group (`dialout` on Ubuntu, often `uucp` elsewhere); log out/in after changes. On Windows, check Device Manager and the vendor driver.
