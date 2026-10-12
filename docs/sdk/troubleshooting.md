# Glove SDK troubleshooting

[SDK guide](README.md) · [Python API](api.md) · [Sensor maps](sensors.md) · [Home](../../README.md)

## Setup

| Requirement | Value |
|---|---|
| SDK / Python | [SDK 0.5.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0), 64-bit CPython 3.13. |
| Glove / serial | Wired V01.12; 1,000,000 baud, 8N1. |
| Hand | Assign `lh`/`rh` yourself; ports and packets do not identify it. |
| Viewer | Desktop, PySide6/pyqtgraph; Linux may also need `libegl1`. |

## Quick fixes

| Symptom | Action |
|---|---|
| Wheel will not install | Match CPython 3.13, OS, and x86_64. |
| Earlier 0.5.0 stays installed | `python -m pip install --force-reinstall PATH_TO_WHEEL` |
| Port unavailable | Close the GUI/other readers; check Device Manager or Linux permissions. |
| Wrong hand | Touch one glove; correct `--left`/`--right` or API `hand`. |
| `TimeoutError` | No valid sample for two seconds; inspect cable/power and reconnect. Examples do not retry automatically. |
| Calibrated fields are `None` | Supply the matching `--force FILE`; API callers also need `tare()` or `baseline_adc`. |
| Newton field is `None` | With calibration, use a positive `pixel_area_mm2`; `None` selects pressure only. |
| Saturation stays true after tare | Flag uses original raw ADC `>=4000`; treat it as a lower bound. |
| Raw gyro/accel are zero | Observed V01.12 behavior; physical scaling/output remain unverified. Euler angles are degrees. |
| Viewer fails | Keep `glove_viewer.py` beside `stream_glove.py`; try without `--viewer`. |

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

See [API examples](api.md) for calibration and reconnect handling.
