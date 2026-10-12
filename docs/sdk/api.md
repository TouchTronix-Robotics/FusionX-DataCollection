# Glove SDK Python API

[SDK guide](README.md) · [Sensor indexing](sensors.md) · [Troubleshooting](troubleshooting.md)

SDK **0.5.0** exports four classes:

```python
from tactile_glove import GloveReader, GloveFrame, TactileData, IMUData
```

## GloveReader

Replace the port and hand with your physical assignment. Use one reader per port and one consumer per reader.

```python
PORT = "COM3"  # Linux example: "/dev/ttyUSB0"
# force, baseline_adc, and pixel_area_mm2 are keyword-only arguments.

with GloveReader(PORT, hand="lh") as glove:
    frame = next(glove.stream())  # Wait for a complete valid sample.
# The context manager stops streaming and closes the port, including on errors.
# Field examples below use this frame; every frame contains tactile and IMU data.
```

| Argument | Default | Meaning |
|---|---|---|
| `port` | Required | Serial port. Packets do not identify the hand. |
| `hand` | `"lh"` | `"lh"` or `"rh"`. |
| `baudrate` | `1_000_000` | Wired V01.12, 8N1. |
| `force` | `None` | Supplier per-pixel pressure JSON for this glove pair. |
| `baseline_adc` | `None` | Five finger names → 16 resting ADC values each, within 0–4096; requires `force`. Otherwise call `tare()`. |
| `pixel_area_mm2` | `22.5` | Positive uniform area or five named 16-area lists; `None` disables newtons. |

For polling instead of an iterator:

```python
with GloveReader(PORT, hand="lh") as glove:
    while True:
        frame = glove.read_frame()
        if frame is not None:  # None means no complete sample yet.
            print(frame.device_timestamp_ms)
            break
```

## GloveFrame

| Field | Type | Meaning |
|---|---|---|
| `hand` | `str` | Your LH/RH assignment. |
| `tactile` | `TactileData` | Pressure and bend readings. |
| `imu` | `IMUData` | Euler angles and raw motion readings. |
| `host_timestamp_ns` | `int` | Unix host decode time; includes buffering/processing delays. |
| `device_timestamp_ms` | `int` | Glove elapsed stream time; restarts at zero on stream start/reconnect. |

```python
sample: GloveFrame = frame
print(sample.hand)
print(sample.host_timestamp_ns / 1_000_000_000)  # Unix seconds.
print(sample.device_timestamp_ms)              # Elapsed milliseconds, not Unix time.
# Counter: uint32, 0–4,294,967,295 ms (~49.71 days); overflow behavior unverified.
# Observed healthy output: 8 ms spacing (~125 Hz). The SDK does not resample.
```

## TactileData

| Field | Shape | Values / order |
|---|---|---|
| `finger_pressure` | `dict[str, list[int]]` | Five 4×4 patches, 16 row-major ADC values each; `(0, 0)` is top-left. |
| `finger_bend` | `dict[str, int]` | One raw ADC value per finger. |
| `finger_pressure_kPa_pixels` | `dict[str, list[float]]` or `None` | One pressure reading in kPa for each of the 16 pixels; requires calibration and tare/baseline. |
| `finger_pressure_N_pixels` | `dict[str, list[float]]` or `None` | One force reading in N for each of the 16 pixels; `None` without calibration or with `pixel_area_mm2=None`. |
| `finger_pressure_saturated` | `dict[str, list[bool]]` or `None` | Raw ADC `>=4000`; requires calibration. |

```python
tactile: TactileData = frame.tactile
print(list(tactile.finger_pressure))  # thumb, index, middle, ring, little
pixels = tactile.finger_pressure["index"]  # 16 integers, 0–4096.
patch = [pixels[i:i + 4] for i in range(0, 16, 4)]
print(patch[0][0])                         # Top-left; no flip needed.
print(tactile.finger_pressure["index"][9]) # Row 2, column 1: 4 * row + column.
print(tactile.finger_bend["index"])        # Raw ADC, not a bend angle.
```

[Physical pixel maps](sensors.md) show all 80 pressure and five bend channels.

## IMUData

| Field | Tuple | Units |
|---|---|---|
| `euler_deg` | `(pitch, roll, yaw)` | Device degrees; no hand-dependent sign changes. |
| `gyro_raw` | `(x, y, z)` | Signed int16; physical scaling unverified. |
| `accel_raw` | `(x, y, z)` | Signed int16; physical scaling unverified. |

```python
imu: IMUData = frame.imu
pitch, roll, yaw = imu.euler_deg
print(pitch, roll, yaw, imu.gyro_raw, imu.accel_raw)
# Inspected gyro/accel values were zero. No quaternion or magnetometer is transmitted.
```

## Per-pixel calibration

Use the matching glove-pair file. `calibrations/example_perpixel_pressure.json` belongs to **LH_1/RH_1**.

```python
CALIBRATION = "calibrations/example_perpixel_pressure.json"

with GloveReader(PORT, hand="lh", force=CALIBRATION) as glove:
    resting_adc = glove.tare(duration_s=1.0)  # Worn glove, no tactile contact.
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure_kPa_pixels["thumb"])  # Pressure per pixel, in kPa.
    print(frame.tactile.finger_pressure_N_pixels["thumb"])    # Force per pixel, in N.
    print(frame.tactile.finger_pressure_saturated["thumb"])   # Saturation flag per pixel.
# N = kPa * area_mm2 * 0.001; default area is 22.5 mm².
# Saturated/table-top values are lower bounds, even when tared pressure is zero.
```

Reuse a recent resting measurement for the same glove and wearing session:

```python
reader = GloveReader(
    PORT, hand="lh", force=CALIBRATION, baseline_adc=resting_adc,
    pixel_area_mm2=22.5,  # Override with measured areas; None gives pressure only.
)
with reader as glove:
    frame = next(glove.stream())  # Baseline is already prepared.
# Retare after changing wearer/session or putting the glove on again.
# Tare clears buffered input without restarting the device counter.
# The same reader retains its prepared baseline across reconnects.
```

See [calibration format and conversion](../gui/calibration.md#supplier-per-pixel-pressure) for LUT validation, mapping, and pressure-domain tare.

## Reconnect after errors

```python
import time
from serial import SerialException

reader = GloveReader(PORT, hand="lh")
try:
    while True:
        try:
            reader.connect()
            for frame in reader.stream():  # New iterator after each reconnect.
                print(frame.device_timestamp_ms)
        except (TimeoutError, SerialException) as error:
            print(error)
        finally:
            reader.disconnect()
        time.sleep(1)  # Retry the same physical port.
except KeyboardInterrupt:
    pass  # The finally block has closed the port.
```

| Error | Check |
|---|---|
| `TimeoutError` | No valid sample for two seconds. Metadata/malformed packets do not reset the timeout. |
| `SerialException` | Connection, permissions, or another reader using the port. |
| `RuntimeError` | Connect before reading; with calibration, provide a baseline or call `tare()`. `tare()` requires `force`. |
| `ValueError` | Hand, calibration, baseline, area, or tare duration. |

## Example behavior

```bash
# Run from the repository root; replace COM3/COM4 with your ports.
python examples/stream_glove.py --left COM3 --right COM4 --viewer --seconds 30
python examples/read_one_frame.py COM3 --hand lh --force calibrations/example_perpixel_pressure.json
python examples/test_glove.py COM3 --hand lh --raw-output glove_raw_bytes.txt
```

| Example | Behavior |
|---|---|
| `stream_glove.py` | One worker per port; prints counts/rate/frame age. `--force FILE` adds startup tare and peak kPa/N; timed streaming begins after tare. |
| `--viewer` | Raw ADC display at 25 FPS; latest frame only, stale data dims. Keep `glove_viewer.py` beside the script. |
| `--seconds` / Ctrl+C / window close | Stops workers and closes ports; reader/render errors propagate after cleanup. |
| `read_one_frame.py` | Prints one frame, including calibrated arrays with `--force FILE`. |
| `test_glove.py` | Counts bytes/frames and saves a hex dump; close other readers first. |

[Save frames in your pipeline](README.md#build-your-own-data-collection-pipeline).
