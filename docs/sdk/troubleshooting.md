# Glove SDK troubleshooting

[SDK guide](README.md) · [Python API](api.md) · [Sensor maps](sensors.md) · [Home](../../README.md)

## Setup

| Requirement | Value |
|---|---|
| SDK / Python | [SDK 0.6.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0), 64-bit CPython 3.13 on Windows x86_64 or Linux x86_64/ARM64. |
| Linux ARM64 | `aarch64`, glibc 2.28+; no 32-bit ARM, musl, or other Python-minor wheel. |
| Glove / serial | Wired V01.12; 1,000,000 baud, 8N1. |
| Hand | Assign `lh`/`rh` yourself; ports and packets do not identify it. |
| Viewer | Optional `viewer` extra, desktop, PySide6/pyqtgraph; Linux may also need `libegl1`. |
| Audio | Optional `audio` extra installs miniaudio. The English/Chinese calibration WAVs are included in every wheel. |

## Quick fixes

| Symptom | Action |
|---|---|
| Wheel will not install | Match CPython 3.13, OS, and x86_64 or Linux ARM64 architecture; ARM64 also needs glibc 2.28+. |
| Port unavailable | Close the GUI/other readers; check Device Manager or Linux permissions. |
| Wrong hand | Touch one glove; correct `--left`/`--right` or API `hand`. |
| `TimeoutError` | No valid sample for two seconds; inspect cable/power and reconnect. Examples do not retry automatically. |
| Calibrated fields are `None` | Supply the matching `--force FILE`; API callers also need `tare()` or `baseline_adc`. |
| Saturation stays true after tare | Flag uses original raw ADC `>=4000`; treat it as a lower bound. |
| No calibration sound | Install your wheel with the `audio` extra; check the selected system output and volume. Audio warnings do not stop valid text calibration. `--no-audio` requests silence. |
| Chinese audio needed | Use `--language cn`; printed terminal instructions remain English. |
| miniaudio installation needs a compiler | The optional binding may build from source on Linux ARM64; provide a C compiler and Python development headers, or use base installation/text calibration. |
| Wearer calibration fails | Read the reported error, reconnect if needed, then repeat both poses. Too few valid frames prevents saving; an existing output file is preserved. |

## Linux serial access

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
groups
# If the device's group is dialout:
sudo usermod -aG dialout "$USER"
# Log out/in, then retry. Some distributions use uucp instead.
```

Run as your normal user. On Windows, check the COM port and vendor driver in Device Manager.

## Diagnose one port

```bash
python examples/test_glove.py COM3 --hand lh --raw-output glove_raw_bytes.txt
```

Close other readers first. The script reports bytes/frames and saves a hex dump.

## Timing and shutdown

- `host_timestamp_ns`: Unix decode time, affected by buffering.
- `device_timestamp_ms`: elapsed stream counter; resets on start/reconnect. Uint32 (~49.71 days); overflow behavior unverified.
- Viewer refresh is 25 FPS; observed sensor output was ~125 Hz. Preserve both clocks and every frame in your storage pipeline.
- Duration expiry, Ctrl+C, window close, and reader/render errors close ports after worker cleanup.
- `calibrate()` owns its selected ports until it returns. Ctrl+C or `stop_event` cancels it and cleans up serial/audio resources; stop other readers before starting it.

See [API examples](api.md) for calibration and reconnect handling.
